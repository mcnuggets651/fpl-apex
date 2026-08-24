"""Strict offline normalization of VERIFIED Slice 11 post-event truth.

The evaluator must not trust a normalized ``actual_value`` merely because it is shared by
candidate and incumbent. For the Official FPL authorities currently marked VERIFIED in
``outcome_truth_v2.yaml``, this module recomputes the exact value from the retained raw
artifact bytes and the exact Official player ID.
"""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.learning_common import ExactMetricValue
from apex_fpl.core.learning_dataset import EvaluationCase
from apex_fpl.core.outcome_truth import (
    OutcomeTarget,
    OutcomeTruthRegistry,
    TruthAuthorityStatus,
)

_EVENT_FIELDS = {
    OutcomeTarget.FPL_POINTS: "total_points",
    OutcomeTarget.MINUTES: "minutes",
    OutcomeTarget.GOAL: "goals_scored",
    OutcomeTarget.ASSIST: "assists",
}


def _strict_json_object(content: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _elements(payload: dict[str, object], *, label: str) -> list[dict[str, object]]:
    rows = payload.get("elements")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{label} elements must be an array of objects")
    return [dict(row) for row in rows]


def _exact_player_row(
    payload: dict[str, object],
    *,
    player_id: int,
    label: str,
) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for row in _elements(payload, label=label):
        raw_id = row.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int):
            raise ValueError(f"{label} element id must be integer")
        if raw_id == player_id:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError(
            f"{label} must contain exactly one element for Official player {player_id}"
        )
    return matches[0]


def normalize_verified_outcome(
    *,
    case: EvaluationCase,
    truth_registry: OutcomeTruthRegistry,
    store: ArtifactStore,
) -> ExactMetricValue:
    """Recompute one VERIFIED outcome value from its retained canonical source bytes."""

    authority = truth_registry.authority_for(case.target)
    if authority.status is not TruthAuthorityStatus.VERIFIED:
        raise ValueError(f"{case.target.value} outcome truth authority is not VERIFIED")
    if authority.source_id != "official_fpl":
        raise ValueError(
            f"no built-in verified normalizer for truth source {authority.source_id!r}"
        )
    if not store.verify(case.outcome_artifact_id):
        raise ValueError("evaluation outcome artifact is missing or corrupt")

    payload = _strict_json_object(
        store.read_bytes(case.outcome_artifact_id),
        label=f"Official FPL {case.target.value} truth artifact",
    )
    player_id = int(case.player_id)

    if case.target in _EVENT_FIELDS:
        if authority.capability != "event_scoring_truth":
            raise ValueError("Official event truth capability does not match registry authority")
        row = _exact_player_row(payload, player_id=player_id, label="Official FPL event-live")
        stats = row.get("stats")
        if not isinstance(stats, dict):
            raise ValueError("Official FPL event-live element stats must be object")
        field = _EVENT_FIELDS[case.target]
        value = _strict_int(stats.get(field), label=f"Official FPL event-live stats.{field}")
        return ExactMetricValue(value)

    if case.target is OutcomeTarget.PRICE:
        if authority.capability != "price_truth":
            raise ValueError("Official price truth capability does not match registry authority")
        row = _exact_player_row(payload, player_id=player_id, label="Official FPL bootstrap")
        value = _strict_int(row.get("now_cost"), label="Official FPL bootstrap now_cost")
        return ExactMetricValue(value)

    raise ValueError(
        f"VERIFIED target {case.target.value} has no implemented canonical normalizer"
    )
