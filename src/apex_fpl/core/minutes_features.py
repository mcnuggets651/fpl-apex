"""Point-in-time feature inputs for the later probabilistic minutes model.

This module deliberately does not estimate expected minutes. It exposes knowable inputs,
explicit missingness and exact observation lineage. The forecast slice is responsible for
an empirically qualified mapping from these features to a minutes distribution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .features import FeatureScope, FeatureSnapshot, FeatureValueKind
from .identity import OfficialPlayerId
from .ids import FeatureSnapshotId


@dataclass(frozen=True, slots=True)
class MinutesFeatureVector:
    player_id: OfficialPlayerId
    feature_snapshot_id: FeatureSnapshotId
    cutoff: str
    official_status: str | None
    official_chance_bps: int | None
    current_cumulative_minutes: int | None
    current_cumulative_starts: int | None
    prior_minutes: int | None
    prior_starts: int | None
    prior_appearances: int | None
    preseason_minutes: int | None
    preseason_starts: int | None
    preseason_appearances: int | None
    known_observation_ids: tuple[str, ...]
    missing_features: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.known_observation_ids) != len(set(self.known_observation_ids)):
            raise ValueError("minutes feature lineage contains duplicate observation IDs")
        if len(self.missing_features) != len(set(self.missing_features)):
            raise ValueError("minutes feature vector contains duplicate missing-feature labels")
        for label in (
            "official_chance_bps",
            "current_cumulative_minutes",
            "current_cumulative_starts",
            "prior_minutes",
            "prior_starts",
            "prior_appearances",
            "preseason_minutes",
            "preseason_starts",
            "preseason_appearances",
        ):
            value = getattr(self, label)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{label} must be a nonnegative integer or explicit missing")
        if self.official_chance_bps is not None and self.official_chance_bps > 10_000:
            raise ValueError("official_chance_bps must be in [0,10000]")
        if self.preseason_starts is not None and self.preseason_appearances is not None:
            if self.preseason_starts > self.preseason_appearances:
                raise ValueError("preseason starts cannot exceed preseason appearances")
        if self.prior_starts is not None and self.prior_appearances is not None:
            if self.prior_starts > self.prior_appearances:
                raise ValueError("prior starts cannot exceed prior appearances")

    @property
    def has_preseason_sample(self) -> bool:
        return bool(self.preseason_appearances and self.preseason_appearances > 0)

    @property
    def isolated_preseason_cameo(self) -> bool:
        return self.preseason_appearances == 1 and self.preseason_starts == 0


_INTEGER_FEATURES = {
    "official.chance_next_round_bps": "official_chance_bps",
    "official.cumulative_minutes": "current_cumulative_minutes",
    "official.cumulative_starts": "current_cumulative_starts",
    "history.prior_minutes": "prior_minutes",
    "history.prior_starts": "prior_starts",
    "history.prior_appearances": "prior_appearances",
    "preseason.minutes": "preseason_minutes",
    "preseason.starts": "preseason_starts",
    "preseason.appearances": "preseason_appearances",
}


def minutes_feature_vector(
    snapshot: FeatureSnapshot,
    player_id: OfficialPlayerId,
) -> MinutesFeatureVector:
    """Extract a no-default minutes input vector from one FeatureSnapshot."""

    entity = str(int(player_id))
    values: dict[str, int | None] = {attribute: None for attribute in _INTEGER_FEATURES.values()}
    missing: list[str] = []
    lineage: list[str] = []

    for feature_name, attribute in _INTEGER_FEATURES.items():
        observation = snapshot.get(
            scope=FeatureScope.PLAYER,
            entity_id=entity,
            feature_name=feature_name,
        )
        if observation is None or observation.value.kind is FeatureValueKind.MISSING:
            missing.append(feature_name)
            continue
        if observation.value.kind is not FeatureValueKind.INTEGER:
            raise ValueError(f"minutes feature {feature_name} must be INTEGER or MISSING")
        values[attribute] = observation.value.integer_value
        lineage.append(observation.observation_id)

    status_obs = snapshot.get(
        scope=FeatureScope.PLAYER,
        entity_id=entity,
        feature_name="official.status",
    )
    status: str | None = None
    if status_obs is None or status_obs.value.kind is FeatureValueKind.MISSING:
        missing.append("official.status")
    else:
        if status_obs.value.kind is not FeatureValueKind.CATEGORICAL:
            raise ValueError("minutes feature official.status must be CATEGORICAL or MISSING")
        status = status_obs.value.categorical_value
        lineage.append(status_obs.observation_id)

    return MinutesFeatureVector(
        player_id=player_id,
        feature_snapshot_id=snapshot.snapshot_id,
        cutoff=snapshot.cutoff,
        official_status=status,
        official_chance_bps=values["official_chance_bps"],
        current_cumulative_minutes=values["current_cumulative_minutes"],
        current_cumulative_starts=values["current_cumulative_starts"],
        prior_minutes=values["prior_minutes"],
        prior_starts=values["prior_starts"],
        prior_appearances=values["prior_appearances"],
        preseason_minutes=values["preseason_minutes"],
        preseason_starts=values["preseason_starts"],
        preseason_appearances=values["preseason_appearances"],
        known_observation_ids=tuple(sorted(lineage)),
        missing_features=tuple(sorted(missing)),
    )
