from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any, Iterable

import requests

from apex_v2_tournament_common import (
    EVALUATION_PREFIX,
    FPL_BOOTSTRAP,
    FPL_LIVE,
    SELECTION_PREFIX,
    TournamentContractError,
    _find_release,
    _load_json,
    _release_asset_map,
    _surface_rows,
    _write_json,
    canonical_sha256,
    sha256_path,
)

CATASTROPHIC_XP_RESIDUAL = 5.0
CATASTROPHIC_MINUTES_RESIDUAL = 45.0
MINUTES_RISK_NAILED_THRESHOLD = 75.0
MINUTES_RISK_MANAGED_THRESHOLD = 45.0
MINUTES_DISAGREEMENT_THRESHOLD = 20.0


def _brier(predicted: list[float], actual: list[float]) -> float | None:
    if not predicted or len(predicted) != len(actual):
        return None
    return sum(
        (float(prediction) - float(label)) ** 2
        for prediction, label in zip(predicted, actual)
    ) / len(predicted)


def specialist_metrics(
    surface: dict[str, Any],
    outcome: dict[str, Any],
    *,
    gameweek: int,
    horizon: int = 1,
) -> dict[str, Any]:
    actual_points = {
        int(key): float(value)
        for key, value in (outcome.get("actual_points") or {}).items()
    }
    actual_minutes = {
        int(key): float(value)
        for key, value in (outcome.get("actual_minutes") or {}).items()
    }
    actual_started = {
        int(key): int(value)
        for key, value in (outcome.get("actual_started") or {}).items()
    }
    rows = [
        row
        for row in _surface_rows(surface, horizon)
        if int(row.get("gameweek", -1)) == int(gameweek)
        and str(row.get("coverage_status") or "FORECAST").upper()
        == "FORECAST"
    ]

    minute_errors: list[float] = []
    appearance_pred: list[float] = []
    appearance_actual: list[float] = []
    start_pred: list[float] = []
    start_actual: list[float] = []
    p60_pred: list[float] = []
    p60_actual: list[float] = []
    catastrophic_minutes = 0

    for row in rows:
        try:
            player_id = int(row["element_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if player_id not in actual_points:
            continue

        if (
            row.get("expected_minutes") is not None
            and player_id in actual_minutes
        ):
            error = abs(
                float(row["expected_minutes"])
                - actual_minutes[player_id]
            )
            minute_errors.append(error)
            if error >= CATASTROPHIC_MINUTES_RESIDUAL:
                catastrophic_minutes += 1

        if (
            row.get("p_appearance") is not None
            and player_id in actual_minutes
        ):
            appearance_pred.append(float(row["p_appearance"]))
            appearance_actual.append(
                1.0 if actual_minutes[player_id] > 0 else 0.0
            )

        if row.get("p_start") is not None and player_id in actual_started:
            start_pred.append(float(row["p_start"]))
            start_actual.append(float(actual_started[player_id]))

        if row.get("p_60") is not None and player_id in actual_minutes:
            p60_pred.append(float(row["p_60"]))
            p60_actual.append(
                1.0 if actual_minutes[player_id] >= 60 else 0.0
            )

    return {
        "minutes": {
            "status": "SCORED" if minute_errors else "NOT_SCOREABLE",
            "rows": len(minute_errors),
            "mae": (
                statistics.fmean(minute_errors)
                if minute_errors
                else None
            ),
            "catastrophic_residual_threshold_minutes": (
                CATASTROPHIC_MINUTES_RESIDUAL
            ),
            "catastrophic_residual_count": catastrophic_minutes,
        },
        "appearance_probability": {
            "status": "SCORED" if appearance_pred else "NOT_SCOREABLE",
            "rows": len(appearance_pred),
            "brier": _brier(appearance_pred, appearance_actual),
        },
        "start_probability": {
            "status": (
                "SCORED"
                if start_pred
                else "NOT_SCOREABLE_NO_REALIZED_START_LABEL"
            ),
            "rows": len(start_pred),
            "brier": _brier(start_pred, start_actual),
        },
        "p60_probability": {
            "status": "SCORED" if p60_pred else "NOT_SCOREABLE",
            "rows": len(p60_pred),
            "brier": _brier(p60_pred, p60_actual),
        },
        "component_policy": {
            "attacking_return": (
                "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS"
            ),
            "clean_sheet_defensive": (
                "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS"
            ),
            "bonus": (
                "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS"
            ),
            "no_hindsight_imputation": True,
        },
    }


def _prediction_rows(
    surface: dict[str, Any],
    *,
    gameweek: int,
    horizon: int,
    actual_points: dict[int, float],
    actual_minutes: dict[int, float],
    allowed_ids: frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in _surface_rows(surface, horizon):
        if int(row.get("gameweek", -1)) != int(gameweek):
            continue
        if (
            str(row.get("coverage_status") or "FORECAST").upper()
            != "FORECAST"
        ):
            continue
        if row.get("expected_points") is None:
            continue
        player_id = int(row["element_id"])
        if player_id not in actual_points:
            continue
        if allowed_ids is not None and player_id not in allowed_ids:
            continue
        output.append(
            {
                "gameweek": int(gameweek),
                "element_id": player_id,
                "predicted_points": float(row["expected_points"]),
                "actual_points": actual_points[player_id],
                "actual_minutes": actual_minutes.get(player_id, 0.0),
                "expected_minutes": (
                    float(row["expected_minutes"])
                    if row.get("expected_minutes") is not None
                    else None
                ),
            }
        )
    return output


def _forecast_id_set(
    surface: dict[str, Any],
    *,
    gameweek: int,
    horizon: int,
    actual_points: dict[int, float],
) -> frozenset[int]:
    return frozenset(
        int(row["element_id"])
        for row in _prediction_rows(
            surface,
            gameweek=gameweek,
            horizon=horizon,
            actual_points=actual_points,
            actual_minutes={},
        )
    )


def _xp_residual_diagnostics(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    residuals = [
        abs(float(row["predicted_points"]) - float(row["actual_points"]))
        for row in rows
    ]
    return {
        "threshold_points": CATASTROPHIC_XP_RESIDUAL,
        "catastrophic_residual_count": sum(
            value >= CATASTROPHIC_XP_RESIDUAL for value in residuals
        ),
        "max_absolute_residual": max(residuals) if residuals else None,
    }


def _minutes_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [
        abs(float(row["expected_minutes"]) - float(row["actual_minutes"]))
        for row in rows
        if row.get("expected_minutes") is not None
    ]
    return {
        "status": "SCORED" if errors else "NOT_SCOREABLE",
        "rows": len(errors),
        "mae": statistics.fmean(errors) if errors else None,
        "catastrophic_residual_threshold_minutes": (
            CATASTROPHIC_MINUTES_RESIDUAL
        ),
        "catastrophic_residual_count": sum(
            value >= CATASTROPHIC_MINUTES_RESIDUAL for value in errors
        ),
    }


def _cohort_metric(
    rows: list[dict[str, Any]],
    *,
    allowed_ids: frozenset[int],
) -> dict[str, Any]:
    import pandas as pd

    from apex.governance.evaluation import score_predictions

    cohort_rows = [
        row for row in rows if int(row["element_id"]) in allowed_ids
    ]
    if not cohort_rows:
        return {
            "rows": 0,
            "xp": None,
            "minutes": {
                "status": "NOT_SCOREABLE",
                "rows": 0,
                "mae": None,
                "catastrophic_residual_threshold_minutes": (
                    CATASTROPHIC_MINUTES_RESIDUAL
                ),
                "catastrophic_residual_count": 0,
            },
        }
    frame = pd.DataFrame(cohort_rows)
    return {
        "rows": len(cohort_rows),
        "xp": score_predictions(frame).to_dict(),
        "minutes": _minutes_metrics(cohort_rows),
    }


def _consensus_minutes_cohorts(
    provider_surfaces: dict[str, dict[str, Any]],
    entrant_ids: tuple[str, ...],
    *,
    comparison_ids: frozenset[int],
    gameweek: int,
    horizon: int,
) -> tuple[dict[str, frozenset[int]], dict[str, frozenset[int]]]:
    minute_maps: dict[str, dict[int, float]] = {}
    for provider_id in entrant_ids:
        values: dict[int, float] = {}
        for row in _surface_rows(provider_surfaces[provider_id], horizon):
            if int(row.get("gameweek", -1)) != int(gameweek):
                continue
            if (
                str(row.get("coverage_status") or "FORECAST").upper()
                != "FORECAST"
            ):
                continue
            if row.get("expected_minutes") is None:
                continue
            player_id = int(row["element_id"])
            if player_id in comparison_ids:
                values[player_id] = float(row["expected_minutes"])
        minute_maps[provider_id] = values

    risk: dict[str, set[int]] = {
        "NAILED_75_PLUS": set(),
        "MANAGED_45_TO_74": set(),
        "ROTATION_RISK_UNDER_45": set(),
        "UNKNOWN_MINUTES": set(),
    }
    disagreement: dict[str, set[int]] = {
        "HIGH_DISAGREEMENT_20_PLUS": set(),
        "LOW_DISAGREEMENT_UNDER_20": set(),
        "UNKNOWN_MINUTES": set(),
    }
    for player_id in comparison_ids:
        values = [
            minute_maps[provider_id][player_id]
            for provider_id in entrant_ids
            if player_id in minute_maps[provider_id]
        ]
        if len(values) < 2:
            risk["UNKNOWN_MINUTES"].add(player_id)
            disagreement["UNKNOWN_MINUTES"].add(player_id)
            continue
        consensus = statistics.median(values)
        if consensus >= MINUTES_RISK_NAILED_THRESHOLD:
            risk["NAILED_75_PLUS"].add(player_id)
        elif consensus >= MINUTES_RISK_MANAGED_THRESHOLD:
            risk["MANAGED_45_TO_74"].add(player_id)
        else:
            risk["ROTATION_RISK_UNDER_45"].add(player_id)

        spread = max(values) - min(values)
        if spread >= MINUTES_DISAGREEMENT_THRESHOLD:
            disagreement["HIGH_DISAGREEMENT_20_PLUS"].add(player_id)
        else:
            disagreement["LOW_DISAGREEMENT_UNDER_20"].add(player_id)

    return (
        {key: frozenset(value) for key, value in risk.items()},
        {key: frozenset(value) for key, value in disagreement.items()},
    )


def _position_cohorts(
    player_positions: dict[int, str] | None,
    comparison_ids: frozenset[int],
) -> dict[str, frozenset[int]]:
    if not player_positions:
        return {}
    normalized: dict[str, set[int]] = {}
    aliases = {
        "GKP": "GK",
        "GOALKEEPER": "GK",
        "DEFENDER": "DEF",
        "MIDFIELDER": "MID",
        "FORWARD": "FWD",
        "STRIKER": "FWD",
    }
    for player_id in comparison_ids:
        raw = str(player_positions.get(player_id) or "").strip().upper()
        if not raw:
            continue
        position = aliases.get(raw, raw)
        normalized.setdefault(position, set()).add(player_id)
    return {
        position: frozenset(player_ids)
        for position, player_ids in sorted(normalized.items())
        if player_ids
    }


def score_horizon(
    provider_surfaces: dict[str, dict[str, Any]],
    *,
    entrants: Iterable[str],
    gameweek: int,
    horizon: int,
    live_payload: dict[str, Any],
    decision_surface: frozenset[int] | None = None,
    player_positions: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Score one realized horizon without silently changing the entrant field.

    H1 uses the frozen model-neutral decision surface supplied by the caller.
    Strategic horizons use the exact common forecast intersection across every
    entered provider and realized Official player. Provider-specific all-player
    metrics are retained as descriptive diagnostics, but comparative metrics and
    pairwise evidence always use one common cohort.

    Specialist cohorts are also common across entrants. Minutes-risk and minutes-
    disagreement cohorts are derived only from the sealed pre-outcome provider
    forecasts. Position cohorts use Official season-position identity supplied by
    the caller; no outcome is used to decide cohort membership.
    """

    import pandas as pd

    from apex.governance.evaluation import score_predictions

    entrant_ids = tuple(dict.fromkeys(str(value) for value in entrants))
    if not entrant_ids:
        raise TournamentContractError("tournament scoring has no entrants")
    missing_surfaces = [
        provider_id
        for provider_id in entrant_ids
        if provider_id not in provider_surfaces
    ]
    if missing_surfaces:
        raise TournamentContractError(
            "entered provider surface missing at evaluation: "
            + ", ".join(missing_surfaces)
        )

    actual_points: dict[int, float] = {}
    actual_minutes: dict[int, float] = {}
    actual_started: dict[int, int] = {}
    for element in live_payload.get("elements") or []:
        player_id = int(element["id"])
        stats = element.get("stats") or {}
        actual_points[player_id] = float(stats.get("total_points", 0))
        actual_minutes[player_id] = float(stats.get("minutes", 0))
        if stats.get("starts") is not None:
            actual_started[player_id] = 1 if float(stats["starts"]) > 0 else 0
    if not actual_points:
        raise TournamentContractError(
            "Official live payload contains no realized player points"
        )

    forecast_sets: dict[str, frozenset[int]] = {}
    all_rows_by_provider: dict[str, list[dict[str, Any]]] = {}
    for provider_id in entrant_ids:
        surface = provider_surfaces[provider_id]
        rows = _prediction_rows(
            surface,
            gameweek=gameweek,
            horizon=horizon,
            actual_points=actual_points,
            actual_minutes=actual_minutes,
        )
        if not rows:
            raise TournamentContractError(
                f"entered provider has no scoreable H{horizon} rows: {provider_id}"
            )
        all_rows_by_provider[provider_id] = rows
        forecast_sets[provider_id] = frozenset(
            int(row["element_id"]) for row in rows
        )

    if decision_surface is not None:
        comparison_ids = frozenset(
            int(player_id)
            for player_id in decision_surface
            if int(player_id) in actual_points
        )
        comparison_method = "MODEL_NEUTRAL_DECISION_SURFACE_V1"
    else:
        comparison_ids = frozenset.intersection(
            *(forecast_sets[provider_id] for provider_id in entrant_ids)
        )
        comparison_method = "COMMON_FORECAST_INTERSECTION"

    if not comparison_ids:
        raise TournamentContractError(
            f"H{horizon} comparison surface is empty"
        )

    risk_cohorts, disagreement_cohorts = _consensus_minutes_cohorts(
        provider_surfaces,
        entrant_ids,
        comparison_ids=comparison_ids,
        gameweek=gameweek,
        horizon=horizon,
    )
    position_cohorts = _position_cohorts(player_positions, comparison_ids)

    metrics: dict[str, Any] = {}
    prediction_maps: dict[str, dict[int, float]] = {}
    for provider_id in entrant_ids:
        surface = provider_surfaces[provider_id]
        all_rows = all_rows_by_provider[provider_id]
        comparison_rows = _prediction_rows(
            surface,
            gameweek=gameweek,
            horizon=horizon,
            actual_points=actual_points,
            actual_minutes=actual_minutes,
            allowed_ids=comparison_ids,
        )
        comparison_row_ids = {
            int(row["element_id"]) for row in comparison_rows
        }
        if comparison_row_ids != set(comparison_ids):
            missing = sorted(set(comparison_ids) - comparison_row_ids)
            raise TournamentContractError(
                f"entered provider lacks common comparison rows: {provider_id}: {missing}"
            )

        all_frame = pd.DataFrame(all_rows)
        comparison_frame = pd.DataFrame(comparison_rows)
        starters = all_frame[all_frame.actual_minutes >= 60]
        prediction_maps[provider_id] = {
            int(row["element_id"]): float(row["predicted_points"])
            for row in comparison_rows
        }
        cohorts = {
            "position": {
                key: _cohort_metric(comparison_rows, allowed_ids=value)
                for key, value in position_cohorts.items()
            },
            "minutes_risk": {
                key: _cohort_metric(comparison_rows, allowed_ids=value)
                for key, value in risk_cohorts.items()
                if value
            },
            "minutes_disagreement": {
                key: _cohort_metric(comparison_rows, allowed_ids=value)
                for key, value in disagreement_cohorts.items()
                if value
            },
        }
        metrics[provider_id] = {
            "all": score_predictions(all_frame).to_dict(),
            "starters_60plus": (
                score_predictions(starters).to_dict()
                if not starters.empty
                else None
            ),
            "comparison_surface": score_predictions(
                comparison_frame
            ).to_dict(),
            "all_rows": len(all_rows),
            "comparison_surface_rows": len(comparison_rows),
            "comparison_surface_required_rows": len(comparison_ids),
            "comparison_surface_coverage": (
                len(comparison_rows) / len(comparison_ids)
            ),
            "xp_residuals": _xp_residual_diagnostics(comparison_rows),
            "specialist": specialist_metrics(
                surface,
                {
                    "actual_points": actual_points,
                    "actual_minutes": actual_minutes,
                    "actual_started": actual_started,
                },
                gameweek=gameweek,
                horizon=horizon,
            ),
            "cohorts": cohorts,
        }

    if set(metrics) != set(entrant_ids):
        raise TournamentContractError(
            "tournament evaluator silently changed entrant set"
        )

    pairwise: dict[str, Any] = {}
    sorted_ids = sorted(prediction_maps)
    for index, provider_a in enumerate(sorted_ids):
        for provider_b in sorted_ids[index + 1 :]:
            map_a = prediction_maps[provider_a]
            map_b = prediction_maps[provider_b]
            overlap = sorted(
                comparison_ids & map_a.keys() & map_b.keys()
            )
            if set(overlap) != set(comparison_ids):
                raise TournamentContractError(
                    "pairwise comparison lost common-surface observations"
                )
            error_a = sum(
                abs(map_a[player_id] - actual_points[player_id])
                for player_id in overlap
            )
            error_b = sum(
                abs(map_b[player_id] - actual_points[player_id])
                for player_id in overlap
            )
            pairwise[f"{provider_a}::{provider_b}"] = {
                "provider_a": provider_a,
                "provider_b": provider_b,
                "paired_rows": len(overlap),
                "provider_a_mae": error_a / len(overlap),
                "provider_b_mae": error_b / len(overlap),
            }

    return {
        "providers": metrics,
        "all_pairwise": pairwise,
        "actual_points": actual_points,
        "actual_minutes": actual_minutes,
        "comparison_surface_method": comparison_method,
        "comparison_surface_player_count": len(comparison_ids),
        "comparison_surface_player_ids_published": False,
        "catastrophic_xp_residual_threshold": CATASTROPHIC_XP_RESIDUAL,
        "specialist_cohort_policy": {
            "position_source": (
                "OFFICIAL_SEASON_POSITION_IDENTITY_ONLY"
                if player_positions
                else "NOT_SUPPLIED"
            ),
            "minutes_risk_source": (
                "PREOUTCOME_MEDIAN_SEALED_EXPECTED_MINUTES_ACROSS_ENTRANTS"
            ),
            "minutes_risk_thresholds": {
                "nailed_minimum": MINUTES_RISK_NAILED_THRESHOLD,
                "managed_minimum": MINUTES_RISK_MANAGED_THRESHOLD,
            },
            "minutes_disagreement_source": (
                "PREOUTCOME_SEALED_EXPECTED_MINUTES_RANGE_ACROSS_ENTRANTS"
            ),
            "minutes_disagreement_threshold": (
                MINUTES_DISAGREEMENT_THRESHOLD
            ),
            "no_hindsight_cohort_assignment": True,
            "player_ids_published": False,
        },
    }


LEARNING_PREFIX = "apex-v2/tournament-learning"
LEARNING_CONTRACT = "APEX_V2_ONLINE_SPECIALIST_RELIABILITY_V1"
EVALUATION_CONTRACT = "APEX_V2_PROSPECTIVE_TOURNAMENT_EVALUATION_V1"
RECENCY_HALF_LIFE_OBSERVATIONS = 4.0
MIN_COHORT_ROWS = 8
MIN_GENERAL_ROWS = 2

STAGE_RANK = {
    "INSUFFICIENT_COMPARISON": 0,
    "DIAGNOSTIC_SIGNAL": 1,
    "MIXED_EVIDENCE": 2,
    "EMERGING_EDGE": 3,
    "FAST_TRACK_REVIEW_ELIGIBLE": 4,
    "ACTIONABLE_SPECIALIST_REVIEW": 5,
    "SPECIALIST_ROLE_CANDIDATE": 6,
    "STRONG_EVIDENCE": 7,
    "MATURE_EVIDENCE": 8,
}
REVIEW_ELIGIBLE_STAGES = frozenset(
    {
        "FAST_TRACK_REVIEW_ELIGIBLE",
        "ACTIONABLE_SPECIALIST_REVIEW",
        "SPECIALIST_ROLE_CANDIDATE",
        "STRONG_EVIDENCE",
        "MATURE_EVIDENCE",
    }
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _load_evaluation(
    store: Any,
    release: dict[str, Any],
    root: Path,
) -> tuple[dict[str, Any], str]:
    from apex_v2_tournament_ops import _download_release_files

    names = {
        "tournament_evaluation.json",
        "tournament_evaluation_attestation.json",
    }
    if release.get("immutable") is not True:
        raise TournamentContractError("published tournament evaluation is mutable")
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("tournament evaluation asset set mismatch")
    files = _download_release_files(store, release, names, root)
    evaluation = _load_json(files["tournament_evaluation.json"])
    attestation = _load_json(files["tournament_evaluation_attestation.json"])
    if attestation.get("scope") != "PUBLIC_TOURNAMENT_EVALUATION":
        raise TournamentContractError("tournament evaluation attestation scope mismatch")
    digest = sha256_path(files["tournament_evaluation.json"])
    if str(attestation.get("evaluation_sha256") or "") != digest:
        raise TournamentContractError("tournament evaluation digest mismatch")
    if evaluation.get("contract") != EVALUATION_CONTRACT:
        raise TournamentContractError("unexpected tournament evaluation contract")
    if evaluation.get("production_influence") != "NONE":
        raise TournamentContractError("tournament evaluation crossed production boundary")
    if evaluation.get("promotion_authority") is not False:
        raise TournamentContractError("tournament evaluation gained promotion authority")
    return evaluation, digest


def _load_learning(
    store: Any,
    release: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    from apex_v2_tournament_ops import _download_release_files

    names = {"online_learning.json", "online_learning_attestation.json"}
    if release.get("immutable") is not True:
        raise TournamentContractError("published online-learning release is mutable")
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("online-learning release asset set mismatch")
    files = _download_release_files(store, release, names, root)
    report = _load_json(files["online_learning.json"])
    attestation = _load_json(files["online_learning_attestation.json"])
    if attestation.get("scope") != "PUBLIC_TOURNAMENT_ONLINE_LEARNING":
        raise TournamentContractError("online-learning attestation scope mismatch")
    if str(attestation.get("learning_sha256") or "") != sha256_path(
        files["online_learning.json"]
    ):
        raise TournamentContractError("online-learning digest mismatch")
    if report.get("contract") != LEARNING_CONTRACT:
        raise TournamentContractError("online-learning contract mismatch")
    if report.get("production_influence") != "NONE":
        raise TournamentContractError("online learning crossed production boundary")
    if report.get("promotion_authority") is not False:
        raise TournamentContractError("online learning gained promotion authority")
    if report.get("automatic_serving_change") is not False:
        raise TournamentContractError("online learning gained automatic serving authority")
    return report


def _position_map(bootstrap: dict[str, Any]) -> dict[int, str]:
    labels = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    for row in bootstrap.get("element_types") or []:
        try:
            element_type = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue
        raw = str(
            row.get("singular_name_short")
            or row.get("plural_name_short")
            or ""
        ).strip().upper()
        if raw:
            labels[element_type] = "GK" if raw == "GKP" else raw
    output: dict[int, str] = {}
    for row in bootstrap.get("elements") or []:
        try:
            output[int(row["id"])] = labels[int(row["element_type"])]
        except (KeyError, TypeError, ValueError):
            continue
    return output


def _core_projection_view(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "comparison_surface": provider.get("comparison_surface"),
        "comparison_surface_rows": provider.get("comparison_surface_rows"),
        "comparison_surface_required_rows": provider.get(
            "comparison_surface_required_rows"
        ),
        "comparison_surface_coverage": provider.get(
            "comparison_surface_coverage"
        ),
        "xp_residuals": provider.get("xp_residuals"),
        "specialist": provider.get("specialist"),
    }


def _observation_from_selected_evaluation(
    *,
    public_store: Any,
    private_store: Any,
    releases_by_tag: dict[str, dict[str, Any]],
    private_releases_by_tag: dict[str, dict[str, Any]],
    selection: dict[str, Any],
    evaluation: dict[str, Any],
    evaluation_sha256: str,
    player_positions: dict[int, str],
    root: Path,
) -> dict[str, Any]:
    from apex.governance.tournament import build_model_neutral_decision_surface
    from apex_v2_tournament_ops import (
        _download_candidate,
        _load_internal_private_surfaces,
        _load_private_manager_attempt,
        _load_private_tournament_surface,
    )

    observation = int(selection["prospective_observation_number"])
    target_gameweek = int(selection["target_gameweek"])
    if int(evaluation.get("prospective_observation_number") or 0) != observation:
        raise TournamentContractError("H1 evaluation observation identity mismatch")
    if int(evaluation.get("horizon") or 0) != 1:
        raise TournamentContractError("online learning accepts H1 evaluations only")
    if int(evaluation.get("target_gameweek") or 0) != target_gameweek:
        raise TournamentContractError("H1 evaluation target gameweek mismatch")

    candidate_tag = str(selection.get("selected_candidate_tag") or "")
    candidate_release = releases_by_tag.get(candidate_tag)
    if candidate_release is None:
        raise TournamentContractError(
            f"selected tournament candidate missing: {candidate_tag}"
        )
    readiness = _download_candidate(
        public_store,
        candidate_release,
        root / f"candidate-{observation}",
    )
    if str(readiness.get("readiness_sha256") or "") != str(
        selection.get("selected_readiness_sha256") or ""
    ):
        raise TournamentContractError(
            "online learning selection does not bind exact candidate readiness"
        )

    seal = readiness.get("common_seal") or {}
    run_id = str(seal.get("run_id") or "")
    source_tag = str(seal.get("source_release_tag") or "")
    private_base_tag = str(seal.get("private_base_release_tag") or "")
    private_tournament_tag = str(
        seal.get("private_tournament_release_tag") or ""
    )
    source_release = releases_by_tag.get(source_tag)
    private_base_release = private_releases_by_tag.get(private_base_tag)
    if source_release is None or private_base_release is None:
        raise TournamentContractError(
            "online learning selected source release pair missing"
        )

    internal, _, _, public_attempt = _load_internal_private_surfaces(
        public_store=public_store,
        private_store=private_store,
        public_release=source_release,
        private_release=private_base_release,
        workdir=root / f"source-{observation}",
    )
    surfaces = dict(internal)
    if private_tournament_tag:
        supplemental_release = private_releases_by_tag.get(
            private_tournament_tag
        )
        if supplemental_release is None:
            raise TournamentContractError(
                "online learning selected private tournament supplement missing"
            )
        supplemental, _ = _load_private_tournament_surface(
            private_store=private_store,
            release=supplemental_release,
            public_attempt_id=str(public_attempt["public_attempt_id"]),
            expected_run_id=run_id,
            workdir=root / f"supplement-{observation}",
        )
        surfaces.update(supplemental)

    manager_tag = f"apex-v2/private/{public_attempt['season']}/{run_id}"
    manager_release = private_releases_by_tag.get(manager_tag)
    if manager_release is None:
        raise TournamentContractError(
            "online learning selected private manager release missing"
        )
    manager_attempt = _load_private_manager_attempt(
        private_store=private_store,
        release=manager_release,
        public_attempt_id=str(public_attempt["public_attempt_id"]),
        workdir=root / f"manager-{observation}",
    )
    decision_surface = build_model_neutral_decision_surface(
        manager_attempt,
        surfaces,
        gameweek=target_gameweek,
    )
    if not decision_surface:
        raise TournamentContractError(
            "online learning model-neutral H1 decision surface is empty"
        )

    entrants = list(evaluation.get("entrants") or [])
    if not entrants:
        raise TournamentContractError("online learning H1 evaluation has no entrants")
    missing = [provider_id for provider_id in entrants if provider_id not in surfaces]
    if missing:
        raise TournamentContractError(
            "online learning sealed entrant missing from private surfaces: "
            + ", ".join(missing)
        )

    live_response = requests.get(FPL_LIVE.format(gameweek=target_gameweek), timeout=30)
    live_response.raise_for_status()
    live = live_response.json()
    observed_live_hash = canonical_sha256(live)
    expected_live_hash = str(evaluation.get("official_live_sha256") or "")
    if observed_live_hash != expected_live_hash:
        raise TournamentContractError(
            "Official realized H1 payload drifted from immutable evaluation; "
            "position enrichment is refused rather than backfilled with hindsight"
        )

    scored = score_horizon(
        surfaces,
        entrants=entrants,
        gameweek=target_gameweek,
        horizon=1,
        live_payload=live,
        decision_surface=decision_surface,
        player_positions=player_positions,
    )
    if set(scored["providers"]) != set(entrants):
        raise TournamentContractError(
            "online learning recomputation changed sealed H1 entrant set"
        )
    if scored["all_pairwise"] != evaluation.get("all_pairwise"):
        raise TournamentContractError(
            "online learning recomputation disagrees with immutable pairwise H1 scoring"
        )
    for provider_id in entrants:
        observed = _core_projection_view(scored["providers"][provider_id])
        expected = _core_projection_view(
            (evaluation.get("providers") or {}).get(provider_id) or {}
        )
        if observed != expected:
            raise TournamentContractError(
                f"online learning core H1 recomputation drift: {provider_id}"
            )

    return {
        "observation_number": observation,
        "target_gameweek": target_gameweek,
        "evaluation_release_tag": (
            f"{EVALUATION_PREFIX}/{public_attempt['season']}/obs{observation}/h1"
        ),
        "evaluation_sha256": evaluation_sha256,
        "official_live_sha256": expected_live_hash,
        "selected_candidate_tag": candidate_tag,
        "selected_readiness_sha256": selection.get("selected_readiness_sha256"),
        "entrants": entrants,
        "comparison_surface": {
            "method": scored["comparison_surface_method"],
            "player_count": scored["comparison_surface_player_count"],
            "player_ids_published": False,
        },
        "specialist_cohort_policy": scored["specialist_cohort_policy"],
        "providers": scored["providers"],
    }


def _metric_rows(provider: dict[str, Any]) -> Iterable[dict[str, Any]]:
    comparison = provider.get("comparison_surface") or {}
    comparison_rows = int(provider.get("comparison_surface_rows") or 0)
    for metric_id, label, direction, value in (
        (
            "overall.xp_mae",
            "Overall H1 xP MAE",
            "LOWER_IS_BETTER",
            comparison.get("mae"),
        ),
        (
            "overall.xp_rmse",
            "Overall H1 xP RMSE",
            "LOWER_IS_BETTER",
            comparison.get("rmse"),
        ),
        (
            "overall.top10_ranking_ndcg",
            "Top-10 player ranking NDCG",
            "HIGHER_IS_BETTER",
            comparison.get("mean_ndcg10"),
        ),
        (
            "overall.top25_ranking_ndcg",
            "Top-25 player ranking NDCG",
            "HIGHER_IS_BETTER",
            comparison.get("mean_ndcg25"),
        ),
    ):
        numeric = _safe_float(value)
        if numeric is not None:
            yield {
                "metric_id": metric_id,
                "label": label,
                "family": "OVERALL",
                "direction": direction,
                "rows": comparison_rows,
                "value": numeric,
                "minimum_rows": MIN_GENERAL_ROWS,
            }

    residuals = provider.get("xp_residuals") or {}
    residual_count = _safe_float(residuals.get("catastrophic_residual_count"))
    if residual_count is not None and comparison_rows > 0:
        yield {
            "metric_id": "overall.xp_catastrophic_rate",
            "label": "Catastrophic xP residual rate",
            "family": "OVERALL",
            "direction": "LOWER_IS_BETTER",
            "rows": comparison_rows,
            "value": residual_count / comparison_rows,
            "minimum_rows": MIN_GENERAL_ROWS,
        }

    specialist = provider.get("specialist") or {}
    for metric_id, label, component, field in (
        (
            "availability.minutes_mae",
            "Expected-minutes MAE",
            "minutes",
            "mae",
        ),
        (
            "availability.appearance_brier",
            "Appearance-probability Brier",
            "appearance_probability",
            "brier",
        ),
        (
            "availability.start_brier",
            "Start-probability Brier",
            "start_probability",
            "brier",
        ),
        (
            "availability.p60_brier",
            "60-minute probability Brier",
            "p60_probability",
            "brier",
        ),
    ):
        block = specialist.get(component) or {}
        numeric = _safe_float(block.get(field))
        rows = int(block.get("rows") or 0)
        if numeric is not None and rows >= MIN_GENERAL_ROWS:
            yield {
                "metric_id": metric_id,
                "label": label,
                "family": "AVAILABILITY",
                "direction": "LOWER_IS_BETTER",
                "rows": rows,
                "value": numeric,
                "minimum_rows": MIN_GENERAL_ROWS,
            }
    minute_block = specialist.get("minutes") or {}
    minute_rows = int(minute_block.get("rows") or 0)
    minute_catastrophic = _safe_float(
        minute_block.get("catastrophic_residual_count")
    )
    if minute_catastrophic is not None and minute_rows > 0:
        yield {
            "metric_id": "availability.minutes_catastrophic_rate",
            "label": "Catastrophic minutes residual rate",
            "family": "AVAILABILITY",
            "direction": "LOWER_IS_BETTER",
            "rows": minute_rows,
            "value": minute_catastrophic / minute_rows,
            "minimum_rows": MIN_GENERAL_ROWS,
        }

    cohorts = provider.get("cohorts") or {}
    for cohort_family, buckets in cohorts.items():
        if not isinstance(buckets, dict):
            continue
        family_label = str(cohort_family).upper()
        for bucket, block in sorted(buckets.items()):
            if not isinstance(block, dict):
                continue
            rows = int(block.get("rows") or 0)
            xp = block.get("xp") or {}
            xp_mae = _safe_float(xp.get("mae"))
            if xp_mae is not None and rows >= MIN_COHORT_ROWS:
                yield {
                    "metric_id": f"{cohort_family}.{bucket}.xp_mae",
                    "label": f"{cohort_family}:{bucket} xP MAE",
                    "family": family_label,
                    "cohort": str(bucket),
                    "direction": "LOWER_IS_BETTER",
                    "rows": rows,
                    "value": xp_mae,
                    "minimum_rows": MIN_COHORT_ROWS,
                }
            minutes = block.get("minutes") or {}
            minute_rows = int(minutes.get("rows") or 0)
            minute_mae = _safe_float(minutes.get("mae"))
            if minute_mae is not None and minute_rows >= MIN_COHORT_ROWS:
                yield {
                    "metric_id": f"{cohort_family}.{bucket}.minutes_mae",
                    "label": f"{cohort_family}:{bucket} minutes MAE",
                    "family": family_label,
                    "cohort": str(bucket),
                    "direction": "LOWER_IS_BETTER",
                    "rows": minute_rows,
                    "value": minute_mae,
                    "minimum_rows": MIN_COHORT_ROWS,
                }


def _relative_edge(value: float, alternative: float, direction: str) -> float:
    denominator = max(abs(alternative), 1e-9)
    if direction == "LOWER_IS_BETTER":
        return (alternative - value) / denominator
    if direction == "HIGHER_IS_BETTER":
        return (value - alternative) / denominator
    raise TournamentContractError(f"unknown metric direction: {direction}")


def _stage(
    *,
    observation_count: int,
    consistency: float,
    mean_edge: float,
    worst_edge: float,
) -> str:
    if observation_count <= 0:
        return "INSUFFICIENT_COMPARISON"
    if observation_count == 1:
        return "DIAGNOSTIC_SIGNAL"
    if (
        observation_count >= 12
        and consistency >= 0.70
        and mean_edge >= 0.03
        and worst_edge >= -0.10
    ):
        return "MATURE_EVIDENCE"
    if (
        observation_count >= 8
        and consistency >= 0.70
        and mean_edge >= 0.04
        and worst_edge >= -0.10
    ):
        return "STRONG_EVIDENCE"
    if (
        observation_count >= 5
        and consistency >= 0.70
        and mean_edge >= 0.05
        and worst_edge >= -0.10
    ):
        return "SPECIALIST_ROLE_CANDIDATE"
    if (
        observation_count >= 3
        and consistency >= 0.67
        and mean_edge >= 0.04
        and worst_edge >= -0.12
    ):
        return "ACTIONABLE_SPECIALIST_REVIEW"
    if (
        observation_count == 2
        and consistency >= 0.999
        and mean_edge >= 0.10
        and worst_edge >= 0.0
    ):
        return "FAST_TRACK_REVIEW_ELIGIBLE"
    if observation_count >= 2 and consistency >= 0.67 and mean_edge >= 0.03:
        return "EMERGING_EDGE"
    return "MIXED_EVIDENCE"


def build_online_learning_report(
    observations: Iterable[dict[str, Any]],
    *,
    season: str,
) -> dict[str, Any]:
    rows = sorted(
        [dict(row) for row in observations],
        key=lambda row: int(row["observation_number"]),
    )
    observation_numbers = [int(row["observation_number"]) for row in rows]
    if len(set(observation_numbers)) != len(observation_numbers):
        raise TournamentContractError("duplicate H1 observation in online learning")
    max_observation = max(observation_numbers) if observation_numbers else 0

    metric_observations: dict[str, list[dict[str, Any]]] = {}
    metric_meta: dict[str, dict[str, Any]] = {}
    for observation in rows:
        observation_number = int(observation["observation_number"])
        providers = observation.get("providers") or {}
        per_metric: dict[str, dict[str, Any]] = {}
        for provider_id, provider in sorted(providers.items()):
            for metric in _metric_rows(provider):
                metric_id = str(metric["metric_id"])
                existing = metric_meta.setdefault(
                    metric_id,
                    {
                        key: metric.get(key)
                        for key in (
                            "metric_id",
                            "label",
                            "family",
                            "cohort",
                            "direction",
                            "minimum_rows",
                        )
                        if metric.get(key) is not None
                    },
                )
                if existing.get("direction") != metric.get("direction"):
                    raise TournamentContractError(
                        f"metric direction drift: {metric_id}"
                    )
                per_metric.setdefault(metric_id, {})[provider_id] = {
                    "value": float(metric["value"]),
                    "rows": int(metric["rows"]),
                }
        for metric_id, values in per_metric.items():
            if len(values) < 2:
                continue
            metric_observations.setdefault(metric_id, []).append(
                {
                    "observation_number": observation_number,
                    "values": values,
                }
            )

    leaders: dict[str, Any] = {}
    provider_summary: dict[str, dict[str, Any]] = {}
    for metric_id, obs_rows in sorted(metric_observations.items()):
        meta = metric_meta[metric_id]
        direction = str(meta["direction"])
        provider_stats: dict[str, dict[str, Any]] = {}
        for obs in obs_rows:
            observation_number = int(obs["observation_number"])
            weight = 0.5 ** (
                (max_observation - observation_number)
                / RECENCY_HALF_LIFE_OBSERVATIONS
            )
            values = {
                provider_id: float(payload["value"])
                for provider_id, payload in obs["values"].items()
            }
            if len(values) < 2:
                continue
            ordered = sorted(
                values,
                key=lambda provider_id: (
                    values[provider_id]
                    if direction == "LOWER_IS_BETTER"
                    else -values[provider_id],
                    provider_id,
                ),
            )
            ranks = {provider_id: index + 1 for index, provider_id in enumerate(ordered)}
            for provider_id, value in values.items():
                alternatives = [
                    alt_value
                    for alt_provider, alt_value in values.items()
                    if alt_provider != provider_id
                ]
                best_alternative = (
                    min(alternatives)
                    if direction == "LOWER_IS_BETTER"
                    else max(alternatives)
                )
                edge = _relative_edge(value, best_alternative, direction)
                stat = provider_stats.setdefault(
                    provider_id,
                    {
                        "weighted_value_numerator": 0.0,
                        "weighted_rank_numerator": 0.0,
                        "weighted_edge_numerator": 0.0,
                        "weighted_positive_numerator": 0.0,
                        "weight": 0.0,
                        "observation_count": 0,
                        "win_count": 0,
                        "edges": [],
                        "values": [],
                    },
                )
                stat["weighted_value_numerator"] += weight * value
                stat["weighted_rank_numerator"] += weight * ranks[provider_id]
                stat["weighted_edge_numerator"] += weight * edge
                stat["weighted_positive_numerator"] += weight * (1.0 if edge > 0 else 0.0)
                stat["weight"] += weight
                stat["observation_count"] += 1
                stat["win_count"] += 1 if ranks[provider_id] == 1 else 0
                stat["edges"].append(edge)
                stat["values"].append(value)

        normalized: dict[str, Any] = {}
        for provider_id, stat in sorted(provider_stats.items()):
            weight = float(stat["weight"])
            if weight <= 0:
                continue
            normalized[provider_id] = {
                "observation_count": int(stat["observation_count"]),
                "win_count": int(stat["win_count"]),
                "weighted_mean_value": stat["weighted_value_numerator"] / weight,
                "weighted_mean_rank": stat["weighted_rank_numerator"] / weight,
                "weighted_relative_edge_vs_best_alternative": (
                    stat["weighted_edge_numerator"] / weight
                ),
                "weighted_positive_edge_rate": (
                    stat["weighted_positive_numerator"] / weight
                ),
                "simple_mean_value": statistics.fmean(stat["values"]),
                "worst_relative_edge": min(stat["edges"]),
                "best_relative_edge": max(stat["edges"]),
            }
        if len(normalized) < 2:
            continue

        leader = min(
            normalized,
            key=lambda provider_id: (
                normalized[provider_id]["weighted_mean_rank"],
                -normalized[provider_id][
                    "weighted_relative_edge_vs_best_alternative"
                ],
                -normalized[provider_id]["weighted_positive_edge_rate"],
                provider_id,
            ),
        )
        leader_stats = normalized[leader]
        stage = _stage(
            observation_count=int(leader_stats["observation_count"]),
            consistency=float(leader_stats["weighted_positive_edge_rate"]),
            mean_edge=float(
                leader_stats["weighted_relative_edge_vs_best_alternative"]
            ),
            worst_edge=float(leader_stats["worst_relative_edge"]),
        )
        entry = {
            **meta,
            "comparison_observations": [
                int(row["observation_number"]) for row in obs_rows
            ],
            "leader": leader,
            "stage": stage,
            "review_eligible": stage in REVIEW_ELIGIBLE_STAGES,
            "automatic_serving_change": False,
            "leader_stats": leader_stats,
            "providers": normalized,
        }
        leaders[metric_id] = entry
        summary = provider_summary.setdefault(
            leader,
            {
                "led_metrics": [],
                "emerging_edges": [],
                "review_eligible_edges": [],
            },
        )
        summary["led_metrics"].append(metric_id)
        if STAGE_RANK[stage] >= STAGE_RANK["EMERGING_EDGE"]:
            summary["emerging_edges"].append(metric_id)
        if stage in REVIEW_ELIGIBLE_STAGES:
            summary["review_eligible_edges"].append(metric_id)

    review_queue = sorted(
        [
            {
                "provider_id": entry["leader"],
                "metric_id": metric_id,
                "label": entry["label"],
                "stage": entry["stage"],
                "observations": entry["leader_stats"]["observation_count"],
                "weighted_relative_edge_vs_best_alternative": entry[
                    "leader_stats"
                ]["weighted_relative_edge_vs_best_alternative"],
                "weighted_positive_edge_rate": entry["leader_stats"][
                    "weighted_positive_edge_rate"
                ],
                "serving_change_authorized": False,
            }
            for metric_id, entry in leaders.items()
            if entry["review_eligible"]
        ],
        key=lambda row: (
            -STAGE_RANK[row["stage"]],
            -float(row["weighted_relative_edge_vs_best_alternative"]),
            row["metric_id"],
        ),
    )
    watch_queue = sorted(
        [
            {
                "provider_id": entry["leader"],
                "metric_id": metric_id,
                "label": entry["label"],
                "stage": entry["stage"],
                "observations": entry["leader_stats"]["observation_count"],
                "weighted_relative_edge_vs_best_alternative": entry[
                    "leader_stats"
                ]["weighted_relative_edge_vs_best_alternative"],
            }
            for metric_id, entry in leaders.items()
            if entry["stage"] in {"DIAGNOSTIC_SIGNAL", "EMERGING_EDGE"}
        ],
        key=lambda row: (
            -STAGE_RANK[row["stage"]],
            -float(row["weighted_relative_edge_vs_best_alternative"]),
            row["metric_id"],
        ),
    )

    return {
        "schema_version": 1,
        "contract": LEARNING_CONTRACT,
        "season": season,
        "production_influence": "NONE",
        "promotion_authority": False,
        "automatic_serving_change": False,
        "serving_provider_contract": "UNCHANGED_UNLESS_EXPLICIT_GOVERNED_CHANGE",
        "learning_state": (
            "ACTIVE" if observation_numbers else "AWAITING_FIRST_PROSPECTIVE_H1"
        ),
        "completed_h1_observation_count": len(observation_numbers),
        "observation_numbers": observation_numbers,
        "through_observation": max_observation or None,
        "learning_policy": {
            "mode": "SEQUENTIAL_EVERY_COMPLETED_CANONICAL_H1",
            "recency_half_life_observations": RECENCY_HALF_LIFE_OBSERVATIONS,
            "minimum_general_rows": MIN_GENERAL_ROWS,
            "minimum_cohort_rows": MIN_COHORT_ROWS,
            "stages": {
                "1_observation": "DIAGNOSTIC_SIGNAL",
                "2_plus_consistent_3pct_edge": "EMERGING_EDGE",
                "2_unanimous_10pct_edge": "FAST_TRACK_REVIEW_ELIGIBLE",
                "3_plus_consistent_4pct_edge": "ACTIONABLE_SPECIALIST_REVIEW",
                "5_plus_consistent_5pct_edge": "SPECIALIST_ROLE_CANDIDATE",
                "8_plus_consistent_4pct_edge": "STRONG_EVIDENCE",
                "12_plus_consistent_3pct_edge": "MATURE_EVIDENCE",
            },
            "twelve_gameweeks_required_before_learning": False,
            "twelve_gameweeks_required_before_review": False,
            "final_structural_decision_can_use_longer_sample": True,
            "no_hindsight_imputation": True,
            "provider_names_do_not_receive_priors": True,
        },
        "metric_leaders": leaders,
        "provider_specialist_summary": provider_summary,
        "owner_review_queue": review_queue,
        "watch_queue": watch_queue,
        "serving_action": "NO_AUTOMATIC_CHANGE",
        "observation_metrics": rows,
    }


def _latest_learning_release(
    releases: Iterable[dict[str, Any]],
    *,
    season: str,
) -> dict[str, Any] | None:
    prefix = f"{LEARNING_PREFIX}/{season}/through-obs"
    candidates: list[tuple[int, dict[str, Any]]] = []
    for release in releases:
        tag = str(release.get("tag_name") or "")
        if not tag.startswith(prefix):
            continue
        if release.get("draft") or release.get("immutable") is not True:
            raise TournamentContractError(
                "published online-learning release is not immutable"
            )
        suffix = tag[len(prefix) :]
        try:
            observation = int(suffix)
        except ValueError as exc:
            raise TournamentContractError(
                f"invalid online-learning release tag: {tag}"
            ) from exc
        candidates.append((observation, release))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def publish_online_learning_github(
    *,
    repo: str,
    token: str,
    private_repo: str,
    private_token: str,
    season: str,
    control_plane_sha: str,
    output: Path | None = None,
) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore
    from apex_v2_tournament_ops import _load_selection

    public_store = GitHubReleaseStore(repo, token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    releases_by_tag = {
        str(row.get("tag_name") or ""): row for row in releases
    }
    private_releases_by_tag = {
        str(row.get("tag_name") or ""): row for row in private_releases
    }

    h1_evaluations: dict[int, tuple[dict[str, Any], str, str]] = {}
    selections: dict[int, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for release in releases:
            tag = str(release.get("tag_name") or "")
            if tag.startswith(f"{SELECTION_PREFIX}/{season}/"):
                if release.get("draft") or release.get("immutable") is not True:
                    continue
                selection = _load_selection(
                    public_store,
                    release,
                    root / f"selection-{release['id']}",
                )
                observation = int(selection["prospective_observation_number"])
                if observation in selections:
                    raise TournamentContractError(
                        f"duplicate canonical selection for observation {observation}"
                    )
                selections[observation] = selection

        for observation, selection in sorted(selections.items()):
            tag = f"{EVALUATION_PREFIX}/{season}/obs{observation}/h1"
            release = releases_by_tag.get(tag)
            if release is None:
                continue
            evaluation, digest = _load_evaluation(
                public_store,
                release,
                root / f"evaluation-{observation}",
            )
            h1_evaluations[observation] = (evaluation, digest, tag)

        latest_learning_release = _latest_learning_release(
            releases,
            season=season,
        )
        prior_observations: list[dict[str, Any]] = []
        if latest_learning_release is not None:
            previous = _load_learning(
                public_store,
                latest_learning_release,
                root / "previous-learning",
            )
            prior_observations = list(previous.get("observation_metrics") or [])

        covered = {
            int(row["observation_number"]) for row in prior_observations
        }
        if covered - set(h1_evaluations):
            raise TournamentContractError(
                "online-learning history references missing immutable H1 evaluation"
            )

        missing = sorted(set(h1_evaluations) - covered)
        new_observations: list[dict[str, Any]] = []
        if missing:
            bootstrap_response = requests.get(FPL_BOOTSTRAP, timeout=30)
            bootstrap_response.raise_for_status()
            player_positions = _position_map(bootstrap_response.json())
            if not player_positions:
                raise TournamentContractError(
                    "Official bootstrap contains no position identity for specialist learning"
                )
            for observation in missing:
                evaluation, digest, _ = h1_evaluations[observation]
                new_observations.append(
                    _observation_from_selected_evaluation(
                        public_store=public_store,
                        private_store=private_store,
                        releases_by_tag=releases_by_tag,
                        private_releases_by_tag=private_releases_by_tag,
                        selection=selections[observation],
                        evaluation=evaluation,
                        evaluation_sha256=digest,
                        player_positions=player_positions,
                        root=root / f"obs-{observation}",
                    )
                )

        all_observations = prior_observations + new_observations
        report = build_online_learning_report(
            all_observations,
            season=season,
        )
        through = report.get("through_observation")
        if through is None:
            if output:
                _write_json(output, report)
            return report

        tag = f"{LEARNING_PREFIX}/{season}/through-obs{through}"
        existing = _find_release(releases, tag)
        if existing is not None:
            observed = _load_learning(
                public_store,
                existing,
                root / "existing-learning",
            )
            if observed != report:
                raise TournamentContractError(
                    "immutable online-learning snapshot exists with different evidence"
                )
            if output:
                _write_json(output, observed)
            return observed

        report_path = _write_json(root / "online_learning.json", report)
        attestation_path = _write_json(
            root / "online_learning_attestation.json",
            {
                "schema_version": 1,
                "scope": "PUBLIC_TOURNAMENT_ONLINE_LEARNING",
                "learning_sha256": sha256_path(report_path),
                "through_observation": through,
                "production_influence": "NONE",
                "promotion_authority": False,
                "automatic_serving_change": False,
            },
        )
        public_store.create_once(
            tag,
            {
                "online_learning.json": report_path,
                "online_learning_attestation.json": attestation_path,
            },
            target_commitish=control_plane_sha,
            name=f"Apex V2 online specialist learning through observation {through}",
            body=(
                "Immutable sequential specialist-learning snapshot. It can surface "
                "early review-eligible edges but has no serving or automatic "
                "promotion authority."
            ),
        )
        if output:
            _write_json(output, report)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apex V2 sequential specialist reliability controller"
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--private-repo", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--control-plane-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    private_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    if not private_token:
        raise SystemExit("APEX_PRIVATE_GITHUB_TOKEN is required")

    result = publish_online_learning_github(
        repo=args.repo,
        token=token,
        private_repo=args.private_repo,
        private_token=private_token,
        season=args.season,
        control_plane_sha=args.control_plane_sha,
        output=args.output,
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
