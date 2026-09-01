from __future__ import annotations

import math
import statistics
from typing import Any, Iterable

from apex_v2_tournament_common import _surface_rows

def _brier(predicted: list[float], actual: list[float]) -> float | None:
    if not predicted or len(predicted) != len(actual):
        return None
    return sum((float(p) - float(a)) ** 2 for p, a in zip(predicted, actual)) / len(predicted)


def specialist_metrics(
    surface: dict[str, Any],
    outcome: dict[str, Any],
    *,
    gameweek: int,
    horizon: int = 1,
) -> dict[str, Any]:
    actual_points = {int(k): float(v) for k, v in (outcome.get("actual_points") or {}).items()}
    actual_minutes = {int(k): float(v) for k, v in (outcome.get("actual_minutes") or {}).items()}
    actual_started = {int(k): int(v) for k, v in (outcome.get("actual_started") or {}).items()}
    rows = [
        row
        for row in _surface_rows(surface, horizon)
        if int(row.get("gameweek", -1)) == int(gameweek)
        and str(row.get("coverage_status") or "FORECAST").upper() == "FORECAST"
    ]
    minute_errors = []
    appearance_pred, appearance_actual = [], []
    start_pred, start_actual = [], []
    p60_pred, p60_actual = [], []
    catastrophic = []
    for row in rows:
        try:
            pid = int(row["element_id"])
        except Exception:
            continue
        if pid not in actual_points:
            continue
        if row.get("expected_minutes") is not None and pid in actual_minutes:
            error = abs(float(row["expected_minutes"]) - actual_minutes[pid])
            minute_errors.append(error)
            if error >= 45:
                catastrophic.append({"element_id": pid, "minutes_absolute_error": error})
        if row.get("p_appearance") is not None and pid in actual_minutes:
            appearance_pred.append(float(row["p_appearance"]))
            appearance_actual.append(1.0 if actual_minutes[pid] > 0 else 0.0)
        if row.get("p_start") is not None and pid in actual_started:
            start_pred.append(float(row["p_start"]))
            start_actual.append(float(actual_started[pid]))
        if row.get("p_60") is not None and pid in actual_minutes:
            p60_pred.append(float(row["p_60"]))
            p60_actual.append(1.0 if actual_minutes[pid] >= 60 else 0.0)
    return {
        "minutes": {
            "status": "SCORED" if minute_errors else "NOT_SCOREABLE",
            "rows": len(minute_errors),
            "mae": statistics.fmean(minute_errors) if minute_errors else None,
            "catastrophic_residual_count": len(catastrophic),
        },
        "appearance_probability": {
            "status": "SCORED" if appearance_pred else "NOT_SCOREABLE",
            "rows": len(appearance_pred),
            "brier": _brier(appearance_pred, appearance_actual),
        },
        "start_probability": {
            "status": "SCORED" if start_pred else "NOT_SCOREABLE_NO_REALIZED_START_LABEL",
            "rows": len(start_pred),
            "brier": _brier(start_pred, start_actual),
        },
        "p60_probability": {
            "status": "SCORED" if p60_pred else "NOT_SCOREABLE",
            "rows": len(p60_pred),
            "brier": _brier(p60_pred, p60_actual),
        },
        "component_policy": {
            "attacking_return": "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS",
            "clean_sheet_defensive": "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS",
            "bonus": "NOT_SCOREABLE_UNLESS_SEALED_COMPONENT_FORECAST_EXISTS",
            "no_hindsight_imputation": True,
        },
    }


def _prediction_frame_rows(
    surface: dict[str, Any],
    *,
    gameweek: int,
    horizon: int,
    actual_points: dict[int, float],
    actual_minutes: dict[int, float],
    allowed_ids: frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    output = []
    for row in _surface_rows(surface, horizon):
        if int(row.get("gameweek", -1)) != int(gameweek):
            continue
        if str(row.get("coverage_status") or "FORECAST").upper() != "FORECAST":
            continue
        if row.get("expected_points") is None:
            continue
        pid = int(row["element_id"])
        if pid not in actual_points or (allowed_ids is not None and pid not in allowed_ids):
            continue
        output.append(
            {
                "gameweek": int(gameweek),
                "element_id": pid,
                "predicted_points": float(row["expected_points"]),
                "actual_points": actual_points[pid],
                "actual_minutes": actual_minutes.get(pid, 0.0),
            }
        )
    return output


def score_horizon(
    provider_surfaces: dict[str, dict[str, Any]],
    *,
    entrants: Iterable[str],
    gameweek: int,
    horizon: int,
    live_payload: dict[str, Any],
    decision_surface: frozenset[int] | None = None,
) -> dict[str, Any]:
    """Score one realized horizon using the frozen ``score_predictions`` primitive.

    H1 can additionally receive the frozen model-neutral decision surface. Strategic
    horizons intentionally score the full overlapping forecast universe because the
    future manager decision surface was not known at the original seal.
    """
    import pandas as pd
    from apex.governance.evaluation import score_predictions

    actual_points: dict[int, float] = {}
    actual_minutes: dict[int, float] = {}
    for element in live_payload.get("elements") or []:
        pid = int(element["id"])
        stats = element.get("stats") or {}
        actual_points[pid] = float(stats.get("total_points", 0))
        actual_minutes[pid] = float(stats.get("minutes", 0))
    entrant_ids = [pid for pid in entrants if pid in provider_surfaces]
    metrics: dict[str, Any] = {}
    prediction_maps: dict[str, dict[int, float]] = {}
    required_surface = (
        frozenset(int(pid) for pid in decision_surface if int(pid) in actual_points)
        if decision_surface is not None
        else None
    )
    for pid in entrant_ids:
        surface = provider_surfaces[pid]
        all_rows = _prediction_frame_rows(
            surface,
            gameweek=gameweek,
            horizon=horizon,
            actual_points=actual_points,
            actual_minutes=actual_minutes,
            allowed_ids=None,
        )
        if not all_rows:
            continue
        all_frame = pd.DataFrame(all_rows)
        starters = all_frame[all_frame.actual_minutes >= 60]
        surface_rows = (
            _prediction_frame_rows(
                surface,
                gameweek=gameweek,
                horizon=horizon,
                actual_points=actual_points,
                actual_minutes=actual_minutes,
                allowed_ids=required_surface,
            )
            if required_surface is not None
            else all_rows
        )
        pair_rows = surface_rows if required_surface is not None else all_rows
        prediction_maps[pid] = {
            int(row["element_id"]): float(row["predicted_points"]) for row in pair_rows
        }
        surface_frame = pd.DataFrame(surface_rows)
        required_count = len(required_surface) if required_surface is not None else len(surface_rows)
        surface_ids = {int(row["element_id"]) for row in surface_rows}
        metrics[pid] = {
            "all": score_predictions(all_frame).to_dict(),
            "starters_60plus": score_predictions(starters).to_dict() if not starters.empty else None,
            "all_rows": len(all_frame),
            "decision_surface": (
                score_predictions(surface_frame).to_dict() if not surface_frame.empty else None
            ),
            "decision_surface_rows": len(surface_ids),
            "decision_surface_required_rows": required_count,
            "decision_surface_coverage": (
                len(surface_ids) / required_count if required_count else None
            ),
            "specialist": specialist_metrics(
                surface,
                {"actual_points": actual_points, "actual_minutes": actual_minutes},
                gameweek=gameweek,
                horizon=horizon,
            ),
        }
    pairwise: dict[str, Any] = {}
    for i, provider_a in enumerate(sorted(prediction_maps)):
        for provider_b in sorted(prediction_maps)[i + 1 :]:
            a = prediction_maps[provider_a]
            b = prediction_maps[provider_b]
            overlap = sorted(set(a) & set(b) & set(actual_points))
            ae_a = sum(abs(a[x] - actual_points[x]) for x in overlap)
            ae_b = sum(abs(b[x] - actual_points[x]) for x in overlap)
            pairwise[f"{provider_a}::{provider_b}"] = {
                "provider_a": provider_a,
                "provider_b": provider_b,
                "paired_rows": len(overlap),
                "provider_a_mae": ae_a / len(overlap) if overlap else None,
                "provider_b_mae": ae_b / len(overlap) if overlap else None,
            }
    return {
        "providers": metrics,
        "all_pairwise": pairwise,
        "actual_points": actual_points,
        "actual_minutes": actual_minutes,
        "decision_surface_player_count": len(required_surface) if required_surface is not None else None,
    }
