from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from statistics import median
from typing import Iterable


REVIEW_GAMEWEEKS = (8, 12, 16, 20, 24, 28, 32, 36)
MIN_COMPLETED_GAMEWEEKS = 8
MIN_PAIRED_OBSERVATIONS = 150
MIN_DECISION_SURFACE_COVERAGE = 0.98
MIN_RELATIVE_MAE_IMPROVEMENT = 0.05
DISAGREEMENT_ABSOLUTE_XP = 1.0
DISAGREEMENT_RELATIVE = 0.20
DECISION_SURFACE_CAPTAIN_LIMIT = 5
DECISION_SURFACE_POSITION_LIMIT = 5
DECISION_SURFACE_METHOD = "MODEL_NEUTRAL_DECISION_SURFACE_V1"

# Known methodological lineage. Family labels affect only consensus language and
# disagreement diagnostics; they never change production xP or optimiser inputs.
_PROVIDER_FAMILY = {
    "dastan": "openfpl-lineage",
    "openfpl": "openfpl-lineage",
}


@dataclass(frozen=True)
class PromotionAssessment:
    eligible: bool
    review_checkpoint: bool
    completed_gameweeks: int
    paired_observations: int
    coverage: float
    expanding_relative_mae_improvement: float | None
    recent_relative_mae_improvement: float | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def provider_family(provider_id: str) -> str:
    provider_id = str(provider_id).strip().lower()
    return _PROVIDER_FAMILY.get(provider_id, provider_id)


def is_review_checkpoint(gameweek: int) -> bool:
    return int(gameweek) in REVIEW_GAMEWEEKS


def disagreement_material(
    champion_xp: float,
    challenger_consensus_xp: float,
) -> bool:
    champion = float(champion_xp)
    challenger = float(challenger_consensus_xp)
    absolute = abs(champion - challenger)
    relative = absolute / max(abs(champion), 1.0)
    return (
        absolute >= DISAGREEMENT_ABSOLUTE_XP
        and relative >= DISAGREEMENT_RELATIVE
    )


def independent_challenger_consensus(
    champion_provider_id: str,
    forecasts_by_provider: dict[str, float],
) -> float | None:
    """Return the median across independent methodological families.

    Correlated providers are first collapsed to one family value using their
    within-family median. The family medians are then combined. This is a
    diagnostic only; it never modifies production forecasts.
    """

    champion = str(champion_provider_id).strip().lower()
    families: dict[str, list[float]] = {}
    for provider_id, value in forecasts_by_provider.items():
        provider = str(provider_id).strip().lower()
        if provider == champion:
            continue
        families.setdefault(provider_family(provider), []).append(float(value))
    if not families:
        return None
    family_values = [float(median(values)) for values in families.values()]
    return float(median(family_values))


def paired_error_summaries(
    predictions: dict[str, dict[int, float]],
    *,
    decision_surface: frozenset[int],
    actual: dict[int, float],
) -> dict[str, dict]:
    """Return aggregate all-vs-all errors on identical player observations.

    Only aggregate sums/counts leave this function. Persisting every provider
    pair prospectively means a future champion can still be compared over the
    expanding season without regenerating historical forecasts or publishing
    raw third-party rows.
    """

    required = frozenset(int(pid) for pid in decision_surface if int(pid) in actual)
    output: dict[str, dict] = {}
    for provider_a, provider_b in combinations(sorted(predictions), 2):
        rows_a = predictions[provider_a]
        rows_b = predictions[provider_b]
        overlap = sorted(required & rows_a.keys() & rows_b.keys())
        error_a = sum(abs(float(rows_a[pid]) - float(actual[pid])) for pid in overlap)
        error_b = sum(abs(float(rows_b[pid]) - float(actual[pid])) for pid in overlap)
        key = f"{provider_a}::{provider_b}"
        output[key] = {
            "provider_a": provider_a,
            "provider_b": provider_b,
            "paired_rows": len(overlap),
            "provider_a_absolute_error_sum": float(error_a),
            "provider_b_absolute_error_sum": float(error_b),
            "provider_a_mae": error_a / len(overlap) if overlap else None,
            "provider_b_mae": error_b / len(overlap) if overlap else None,
        }
    return output


def _h1_rows(surface: dict, gameweek: int) -> list[dict]:
    rows = []
    for row in surface.get("rows", []):
        if (
            int(row.get("gameweek", -1)) == int(gameweek)
            and int(row.get("horizon", -1)) == 1
            and row.get("coverage_status", "FORECAST") == "FORECAST"
            and row.get("expected_points") is not None
        ):
            rows.append(row)
    return rows


def build_model_neutral_decision_surface(
    private_manager_attempt: dict,
    provider_surfaces: dict[str, dict],
    *,
    gameweek: int,
    shadow_candidate_ids_by_provider: dict[str, Iterable[int]] | None = None,
) -> frozenset[int]:
    """Build the prospective player surface used to score the tournament.

    The cohort is a union, never a champion-selected set. It contains the
    current squad, the sealed production decision/route, top captain candidates
    from every provider, top legal transfer candidates by position from every
    provider, and any supplied shadow-optimiser candidate ids.
    """

    selected: set[int] = set()
    team_state = private_manager_attempt.get("team_state") or {}
    selected.update(int(pid) for pid in team_state.get("squad_ids") or [])

    system = private_manager_attempt.get("system_decision") or {}
    for key in ("squad_ids", "xi_ids", "bench_order", "transfers_in", "transfers_out"):
        selected.update(int(pid) for pid in system.get(key) or [])
    for key in ("captain_id", "vice_captain_id"):
        if system.get(key) is not None:
            selected.add(int(system[key]))

    for week in private_manager_attempt.get("transfer_plan") or []:
        for key in ("squad_ids", "transfers_in", "transfers_out"):
            selected.update(int(pid) for pid in week.get(key) or [])

    canonical = private_manager_attempt.get("canonical_forecast") or {}
    official = canonical.get("official") or {}
    players = {
        int(player["element_id"]): player
        for player in official.get("players") or []
        if player.get("element_id") is not None
    }

    for surface in provider_surfaces.values():
        rows = _h1_rows(surface, gameweek)
        ranked = sorted(
            rows,
            key=lambda row: (-float(row["expected_points"]), int(row["element_id"])),
        )
        selected.update(
            int(row["element_id"])
            for row in ranked[:DECISION_SURFACE_CAPTAIN_LIMIT]
        )

        by_position: dict[str, list[dict]] = {}
        for row in ranked:
            player_id = int(row["element_id"])
            player = players.get(player_id)
            if not player or player.get("can_transact") is not True:
                continue
            position = str(player.get("position") or "")
            by_position.setdefault(position, []).append(row)
        for position_rows in by_position.values():
            selected.update(
                int(row["element_id"])
                for row in position_rows[:DECISION_SURFACE_POSITION_LIMIT]
            )

    for ids in (shadow_candidate_ids_by_provider or {}).values():
        selected.update(int(pid) for pid in ids)

    return frozenset(selected)


def assess_promotion(
    *,
    gameweek: int,
    completed_gameweeks: int,
    paired_observations: int,
    coverage: float,
    champion_expanding_mae: float | None,
    challenger_expanding_mae: float | None,
    champion_recent_mae: float | None,
    challenger_recent_mae: float | None,
    horizon_compatible: bool,
    operationally_reliable: bool,
    decision_quality_passed: bool,
) -> PromotionAssessment:
    reasons: list[str] = []
    checkpoint = is_review_checkpoint(gameweek)
    if not checkpoint:
        reasons.append("not a scheduled promotion review checkpoint")
    if int(completed_gameweeks) < MIN_COMPLETED_GAMEWEEKS:
        reasons.append("insufficient completed Gameweeks")
    if int(paired_observations) < MIN_PAIRED_OBSERVATIONS:
        reasons.append("insufficient paired decision-surface observations")
    if float(coverage) < MIN_DECISION_SURFACE_COVERAGE:
        reasons.append("decision-surface coverage below 98%")
    if not horizon_compatible:
        reasons.append("challenger does not support the production decision horizon")
    if not operationally_reliable:
        reasons.append("challenger pre-deadline delivery is not operationally reliable")
    if not decision_quality_passed:
        reasons.append("decision-quality sanity check has not passed")

    expanding_improvement = None
    if (
        champion_expanding_mae is not None
        and challenger_expanding_mae is not None
        and float(champion_expanding_mae) > 0
    ):
        expanding_improvement = (
            float(champion_expanding_mae) - float(challenger_expanding_mae)
        ) / float(champion_expanding_mae)
        if expanding_improvement < MIN_RELATIVE_MAE_IMPROVEMENT:
            reasons.append("expanding-window MAE improvement below 5%")
    else:
        reasons.append("expanding-window MAE comparison unavailable")

    recent_improvement = None
    if (
        champion_recent_mae is not None
        and challenger_recent_mae is not None
        and float(champion_recent_mae) > 0
    ):
        recent_improvement = (
            float(champion_recent_mae) - float(challenger_recent_mae)
        ) / float(champion_recent_mae)
        if recent_improvement < 0:
            reasons.append("recent 8-GW MAE advantage has disappeared")
    else:
        reasons.append("recent-window MAE comparison unavailable")

    return PromotionAssessment(
        eligible=not reasons,
        review_checkpoint=checkpoint,
        completed_gameweeks=int(completed_gameweeks),
        paired_observations=int(paired_observations),
        coverage=float(coverage),
        expanding_relative_mae_improvement=expanding_improvement,
        recent_relative_mae_improvement=recent_improvement,
        reasons=tuple(reasons),
    )
