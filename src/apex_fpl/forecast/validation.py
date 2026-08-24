"""Release-path safety checks for probabilistic prediction batches."""

from __future__ import annotations

from apex_fpl.core.forecast import (
    PredictionBatch,
    PredictionDisposition,
    UncertaintyKind,
)


_ALLOWED_STRUCTURAL_ZERO_REASONS = frozenset(
    {"OFFICIAL_SUSPENSION", "OFFICIAL_INELIGIBLE"}
)


def validate_prediction_batch_safety(batch: PredictionBatch) -> None:
    """Reject physically impossible or falsely-certain future prediction rows."""

    for row in batch.rows:
        if row.disposition is PredictionDisposition.ABSTAINED:
            continue
        for scenario in row.scenarios:
            outcome = scenario.outcome
            if outcome.minutes == 0:
                impossible = {
                    "goals": outcome.goals,
                    "assists": outcome.assists,
                    "goals_conceded_while_on_pitch": outcome.goals_conceded_while_on_pitch,
                    "goalkeeper_saves": outcome.goalkeeper_saves,
                    "penalty_saves": outcome.penalty_saves,
                    "penalty_misses": outcome.penalty_misses,
                    "defensive_contributions": outcome.defensive_contributions,
                    "yellow_cards": outcome.yellow_cards,
                    "red_cards": outcome.red_cards,
                    "own_goals": outcome.own_goals,
                    "bonus_points": outcome.bonus_points,
                }
                if any(impossible.values()):
                    raise ValueError(
                        f"zero-minute scenario contains match events for target {row.target.key}"
                    )
        if row.uncertainty_kind is UncertaintyKind.STRUCTURALLY_DETERMINISTIC:
            reason = str(row.deterministic_reason or "")
            if reason not in _ALLOWED_STRUCTURAL_ZERO_REASONS:
                raise ValueError(
                    "structural determinism is restricted to official suspension/ineligibility"
                )
            outcome = row.scenarios[0].outcome
            if outcome.minutes != 0:
                raise ValueError(
                    "structurally deterministic football forecast may only assert zero minutes"
                )
