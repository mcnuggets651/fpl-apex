from __future__ import annotations

import statistics
from typing import Any, Iterable

from apex_v2_tournament_common import TournamentContractError, _surface_rows

CATASTROPHIC_XP_RESIDUAL = 5.0


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
            if error >= 45.0:
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
            "catastrophic_residual_threshold_minutes": 45.0,
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


def score_horizon(
    provider_surfaces: dict[str, dict[str, Any]],
    *,
    entrants: Iterable[str],
    gameweek: int,
    horizon: int,
    live_payload: dict[str, Any],
    decision_surface: frozenset[int] | None = None,
) -> dict[str, Any]:
    """Score one realized horizon without silently changing the entrant field.

    H1 uses the frozen model-neutral decision surface supplied by the caller.
    Strategic horizons use the exact common forecast intersection across every
    entered provider and realized Official player. Provider-specific all-player
    metrics are retained as descriptive diagnostics, but comparative metrics and
    pairwise evidence always use one common cohort.
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
    for element in live_payload.get("elements") or []:
        player_id = int(element["id"])
        stats = element.get("stats") or {}
        actual_points[player_id] = float(stats.get("total_points", 0))
        actual_minutes[player_id] = float(stats.get("minutes", 0))
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
                },
                gameweek=gameweek,
                horizon=horizon,
            ),
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
    }
