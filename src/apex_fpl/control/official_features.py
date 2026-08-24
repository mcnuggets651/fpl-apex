"""Derive point-in-time Official FPL player features from a sealed GlobalWorld only."""

from __future__ import annotations

from datetime import datetime, timezone

from apex_fpl.acquisition import load_official_global_world
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.features import (
    FeatureObservation,
    FeatureScope,
    FeatureValue,
    FeatureValueKind,
)
from apex_fpl.core.ids import GlobalWorldId


def _aware(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _exact_int(value: object, *, label: str, nonnegative: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an exact integer")
    if nonnegative and value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _integer_or_missing(
    payload: dict[str, object],
    field: str,
    *,
    unit: str,
    label: str,
) -> FeatureValue:
    if field not in payload or payload[field] is None:
        return FeatureValue(
            kind=FeatureValueKind.MISSING,
            missing_reason=f"Official FPL field {field} is absent/null at this cutoff",
        )
    return FeatureValue(
        kind=FeatureValueKind.INTEGER,
        integer_value=_exact_int(payload[field], label=label),
        unit=unit,
    )


def _chance_or_missing(payload: dict[str, object]) -> FeatureValue:
    field = "chance_of_playing_next_round"
    if field not in payload or payload[field] is None:
        return FeatureValue(
            kind=FeatureValueKind.MISSING,
            missing_reason="Official FPL chance_of_playing_next_round is absent/null",
        )
    percent = _exact_int(payload[field], label=field)
    if not 0 <= percent <= 100:
        raise ValueError("Official FPL chance_of_playing_next_round must be in [0,100]")
    return FeatureValue(
        kind=FeatureValueKind.INTEGER,
        integer_value=percent * 100,
        unit="basis_points",
    )


def official_player_feature_observations(
    *,
    global_world_manifest_artifact_id: str,
    cutoff: str,
    store: ArtifactStore,
) -> tuple[GlobalWorldId, tuple[FeatureObservation, ...], tuple[str, ...]]:
    """Return direct Official features that were knowable by ``cutoff``.

    No network/clock port is exposed. The complete sealed GlobalWorld must have been
    retrieved by the cutoff because its semantic identity is referenced by the feature
    snapshot. Missing Official fields remain explicit MISSING values.
    """

    cutoff_point = _aware(cutoff, label="feature cutoff")
    replay = load_official_global_world(global_world_manifest_artifact_id, store=store)
    if not replay.captures:
        raise ValueError("sealed GlobalWorld has no raw captures")
    for capture in replay.captures:
        if _aware(capture.retrieved_at, label=f"{capture.source_name} retrieved_at") > cutoff_point:
            raise ValueError(
                f"GlobalWorld source {capture.source_name} was retrieved after feature cutoff"
            )
    bootstrap_capture = next(
        (row for row in replay.captures if row.source_name == "official_fpl_bootstrap"),
        None,
    )
    if bootstrap_capture is None:
        raise ValueError("sealed GlobalWorld is missing Official FPL bootstrap capture")
    elements = replay.bootstrap.get("elements")
    if not isinstance(elements, list):
        raise ValueError("sealed Official FPL bootstrap elements are missing")

    source_artifact = bootstrap_capture.body_artifact_id
    stamp = bootstrap_capture.retrieved_at
    observations: list[FeatureObservation] = []
    for raw in elements:
        if not isinstance(raw, dict):
            raise ValueError("Official FPL bootstrap element row must be an object")
        player_id = _exact_int(raw.get("id"), label="Official player id")
        entity = str(player_id)
        direct: tuple[tuple[str, FeatureValue], ...] = (
            (
                "official.price_tenths",
                _integer_or_missing(raw, "now_cost", unit="tenths_gbp", label="now_cost"),
            ),
            (
                "official.team_id",
                _integer_or_missing(raw, "team", unit="official_team_id", label="team"),
            ),
            (
                "official.position_id",
                _integer_or_missing(
                    raw,
                    "element_type",
                    unit="official_position_id",
                    label="element_type",
                ),
            ),
            (
                "official.cumulative_minutes",
                _integer_or_missing(raw, "minutes", unit="minutes", label="minutes"),
            ),
            (
                "official.cumulative_starts",
                _integer_or_missing(raw, "starts", unit="starts", label="starts"),
            ),
            ("official.chance_next_round_bps", _chance_or_missing(raw)),
        )
        status = str(raw.get("status") or "").strip()
        status_value = (
            FeatureValue(kind=FeatureValueKind.CATEGORICAL, categorical_value=status)
            if status
            else FeatureValue(
                kind=FeatureValueKind.MISSING,
                missing_reason="Official FPL status is absent/empty",
            )
        )
        for feature_name, value in (*direct, ("official.status", status_value)):
            observations.append(
                FeatureObservation(
                    feature_name=feature_name,
                    scope=FeatureScope.PLAYER,
                    entity_id=entity,
                    value=value,
                    observed_at=stamp,
                    first_known_at=stamp,
                    source_artifact_ids=(source_artifact,),
                    derivation_id="official_fpl.bootstrap.direct.v1",
                )
            )

    input_artifacts = tuple(
        sorted(
            {
                str(global_world_manifest_artifact_id),
                *(row.body_artifact_id for row in replay.captures),
            }
        )
    )
    return replay.world.world_id, tuple(observations), input_artifacts
