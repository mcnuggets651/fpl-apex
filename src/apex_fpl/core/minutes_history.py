"""Identity-safe historical and preseason facts for minutes feature construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .features import FeatureObservation, FeatureScope, FeatureValue, FeatureValueKind
from .identity import OfficialPlayerId, PersonLink
from .ids import PersonId


def _aware_iso(value: str, *, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("minutes history source must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("minutes history source digest is invalid") from exc
    return text


def _count(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class HistoricalMinutesSample:
    person_id: PersonId
    season: str
    minutes: int
    starts: int
    appearances: int
    observed_at: str
    first_known_at: str
    source_artifact_id: str

    def __post_init__(self) -> None:
        season = str(self.season).strip()
        if not season:
            raise ValueError("historical minutes season cannot be empty")
        minutes = _count(self.minutes, label="historical minutes")
        starts = _count(self.starts, label="historical starts")
        appearances = _count(self.appearances, label="historical appearances")
        if starts > appearances:
            raise ValueError("historical starts cannot exceed appearances")
        observed = _aware_iso(self.observed_at, label="historical observed_at")
        first_known = _aware_iso(self.first_known_at, label="historical first_known_at")
        if _point(observed) > _point(first_known):
            raise ValueError("historical sample cannot be observed after first-known time")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "minutes", minutes)
        object.__setattr__(self, "starts", starts)
        object.__setattr__(self, "appearances", appearances)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "first_known_at", first_known)
        object.__setattr__(self, "source_artifact_id", _artifact_id(self.source_artifact_id))


def historical_minutes_observations(
    sample: HistoricalMinutesSample,
    *,
    current_link: PersonLink,
    cutoff: str,
) -> tuple[FeatureObservation, ...]:
    """Attach a cross-season sample only through a reviewed PersonLink."""

    cutoff_iso = _aware_iso(cutoff, label="feature cutoff")
    if sample.person_id != current_link.person_id:
        raise ValueError("historical sample PersonId does not match reviewed current-season link")
    if _point(sample.first_known_at) > _point(cutoff_iso):
        raise ValueError("historical minutes sample was not known by feature cutoff")
    values = (
        ("history.prior_minutes", sample.minutes, "minutes"),
        ("history.prior_starts", sample.starts, "starts"),
        ("history.prior_appearances", sample.appearances, "appearances"),
    )
    return tuple(
        FeatureObservation(
            feature_name=name,
            scope=FeatureScope.PLAYER,
            entity_id=str(int(current_link.player_id)),
            value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=value, unit=unit),
            observed_at=sample.observed_at,
            first_known_at=sample.first_known_at,
            source_artifact_ids=(sample.source_artifact_id,),
            derivation_id=f"historical_minutes.{sample.season}.reviewed_person_link.v1",
        )
        for name, value, unit in values
    )


@dataclass(frozen=True, slots=True)
class PreseasonAppearance:
    player_id: OfficialPlayerId
    match_at: str
    minutes: int
    started: bool
    first_known_at: str
    source_artifact_id: str

    def __post_init__(self) -> None:
        minutes = _count(self.minutes, label="preseason minutes")
        if minutes > 120:
            raise ValueError("preseason appearance minutes exceed supported match bound")
        if not isinstance(self.started, bool):
            raise ValueError("preseason started must be boolean")
        match_at = _aware_iso(self.match_at, label="preseason match_at")
        first_known = _aware_iso(self.first_known_at, label="preseason first_known_at")
        if _point(match_at) > _point(first_known):
            raise ValueError("preseason result cannot be first-known before match time")
        object.__setattr__(self, "minutes", minutes)
        object.__setattr__(self, "match_at", match_at)
        object.__setattr__(self, "first_known_at", first_known)
        object.__setattr__(self, "source_artifact_id", _artifact_id(self.source_artifact_id))


def preseason_minutes_observations(
    player_id: OfficialPlayerId,
    appearances: tuple[PreseasonAppearance, ...],
    *,
    cutoff: str,
) -> tuple[FeatureObservation, ...]:
    """Aggregate only preseason appearances actually known by the cutoff."""

    cutoff_iso = _aware_iso(cutoff, label="feature cutoff")
    rows = tuple(
        sorted(
            (
                row
                for row in appearances
                if row.player_id == player_id and _point(row.first_known_at) <= _point(cutoff_iso)
            ),
            key=lambda row: (row.match_at, row.first_known_at, row.source_artifact_id),
        )
    )
    if not rows:
        return ()
    total_minutes = sum(row.minutes for row in rows)
    starts = sum(1 for row in rows if row.started)
    apps = len(rows)
    latest = rows[-1]
    consecutive_starts = 0
    for row in reversed(rows):
        if not row.started:
            break
        consecutive_starts += 1
    source_artifacts = tuple(sorted({row.source_artifact_id for row in rows}))
    first_known = max(row.first_known_at for row in rows)
    observed = max(row.match_at for row in rows)
    integer_values = (
        ("preseason.minutes", total_minutes, "minutes"),
        ("preseason.starts", starts, "starts"),
        ("preseason.appearances", apps, "appearances"),
        ("preseason.latest_appearance_minutes", latest.minutes, "minutes"),
        ("preseason.consecutive_recent_starts", consecutive_starts, "starts"),
    )
    observations = [
        FeatureObservation(
            feature_name=name,
            scope=FeatureScope.PLAYER,
            entity_id=str(int(player_id)),
            value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=value, unit=unit),
            observed_at=observed,
            first_known_at=first_known,
            source_artifact_ids=source_artifacts,
            derivation_id="preseason.appearance_aggregate.v1",
        )
        for name, value, unit in integer_values
    ]
    observations.append(
        FeatureObservation(
            feature_name="preseason.latest_appearance_started",
            scope=FeatureScope.PLAYER,
            entity_id=str(int(player_id)),
            value=FeatureValue(kind=FeatureValueKind.BOOLEAN, boolean_value=latest.started),
            observed_at=latest.match_at,
            first_known_at=latest.first_known_at,
            source_artifact_ids=(latest.source_artifact_id,),
            derivation_id="preseason.latest_appearance.v1",
        )
    )
    return tuple(observations)
