"""Distribution-first probabilistic forecast contracts for Apex V2.

The predictive model is authoritative only for probabilities of future football outcomes.
Official FPL scoring remains a separate deterministic transformation owned by the sealed
RuleSet. All durable numeric semantics are integer/rational; no binary floats enter
forecast identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .ids import (
    FeatureSnapshotId,
    ForecastId,
    GlobalWorldId,
    ModelArtifactId,
    PredictionBatchId,
    RuleSetId,
)
from .rules import FPL_POSITIONS, RuleSet


PROBABILITY_DENOMINATOR = 10_000


def _aware_iso(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_id(value: str, *, label: str = "artifact") -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


class ModelQualificationState(str, Enum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class ForecastUseMode(str, Enum):
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"


class PredictionDisposition(str, Enum):
    PREDICTED = "PREDICTED"
    ABSTAINED = "ABSTAINED"


class UncertaintyKind(str, Enum):
    PROBABILISTIC = "PROBABILISTIC"
    STRUCTURALLY_DETERMINISTIC = "STRUCTURALLY_DETERMINISTIC"


@dataclass(frozen=True, slots=True)
class ForecastModelArtifact:
    model_name: str
    model_version: str
    feature_contract: str
    prediction_contract: str
    parameter_artifact_ids: tuple[str, ...]
    qualification_state: ModelQualificationState
    qualification_artifact_id: str | None
    valid_seasons: tuple[str, ...]
    trained_through: str
    first_available_at: str
    max_horizon_gameweeks: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ForecastModelArtifact schema_version")
        for label in ("model_name", "model_version", "feature_contract", "prediction_contract"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"forecast model {label} cannot be empty")
            object.__setattr__(self, label, value)
        params = tuple(sorted({_artifact_id(item, label="model parameter artifact") for item in self.parameter_artifact_ids}))
        if not params:
            raise ValueError("forecast model requires at least one immutable parameter artifact")
        seasons = tuple(sorted({str(item).strip() for item in self.valid_seasons if str(item).strip()}))
        if not seasons:
            raise ValueError("forecast model requires at least one valid season")
        trained = _aware_iso(self.trained_through, label="model trained_through")
        available = _aware_iso(self.first_available_at, label="model first_available_at")
        if _point(trained) > _point(available):
            raise ValueError("forecast model cannot be available before its training cutoff")
        if isinstance(self.max_horizon_gameweeks, bool) or not isinstance(self.max_horizon_gameweeks, int):
            raise ValueError("max_horizon_gameweeks must be an integer")
        if self.max_horizon_gameweeks <= 0:
            raise ValueError("max_horizon_gameweeks must be positive")
        qualification = self.qualification_artifact_id
        if self.qualification_state is ModelQualificationState.QUALIFIED:
            if qualification is None:
                raise ValueError("qualified forecast model requires qualification artifact")
            qualification = _artifact_id(qualification, label="model qualification artifact")
        elif qualification is not None:
            qualification = _artifact_id(qualification, label="model qualification artifact")
        object.__setattr__(self, "parameter_artifact_ids", params)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "valid_seasons", seasons)
        object.__setattr__(self, "trained_through", trained)
        object.__setattr__(self, "first_available_at", available)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-forecast-model-artifact",
            "schema_version": self.schema_version,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "feature_contract": self.feature_contract,
            "prediction_contract": self.prediction_contract,
            "parameter_artifact_ids": list(self.parameter_artifact_ids),
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "valid_seasons": list(self.valid_seasons),
            "trained_through": self.trained_through,
            "first_available_at": self.first_available_at,
            "max_horizon_gameweeks": self.max_horizon_gameweeks,
        }

    @property
    def model_artifact_id(self) -> ModelArtifactId:
        return ModelArtifactId(canonical_sha256(self.semantic_payload()))

    def require_valid_for(
        self,
        *,
        season: str,
        feature_cutoff: str,
        horizon_gameweeks: int,
        production: bool,
    ) -> None:
        cutoff = _aware_iso(feature_cutoff, label="forecast feature_cutoff")
        if season not in self.valid_seasons:
            raise ValueError(f"forecast model is not valid for season {season}")
        if horizon_gameweeks <= 0 or horizon_gameweeks > self.max_horizon_gameweeks:
            raise ValueError("forecast horizon is outside model validity scope")
        if _point(self.trained_through) > _point(cutoff):
            raise ValueError("forecast model training data leaks beyond feature cutoff")
        if _point(self.first_available_at) > _point(cutoff):
            raise ValueError("forecast model was not available at feature cutoff")
        if self.qualification_state is ModelQualificationState.SUSPENDED:
            raise ValueError("forecast model is suspended")
        if production and self.qualification_state is not ModelQualificationState.QUALIFIED:
            raise ValueError("production forecast requires a qualified forecast model")


@dataclass(frozen=True, slots=True)
class DiscreteIntegerDistribution:
    """Exact discrete integer distribution with probabilities in basis points."""

    support: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if not self.support:
            raise ValueError("distribution support cannot be empty")
        rows: list[tuple[int, int]] = []
        values: set[int] = set()
        total = 0
        for value, probability_bps in self.support:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("distribution values must be integers")
            if value in values:
                raise ValueError("distribution support contains duplicate values")
            if (
                isinstance(probability_bps, bool)
                or not isinstance(probability_bps, int)
                or probability_bps <= 0
                or probability_bps > PROBABILITY_DENOMINATOR
            ):
                raise ValueError("distribution probabilities must be positive integer basis points")
            values.add(value)
            total += probability_bps
            rows.append((value, probability_bps))
        if total != PROBABILITY_DENOMINATOR:
            raise ValueError(
                f"distribution probability mass {total} != {PROBABILITY_DENOMINATOR}"
            )
        object.__setattr__(self, "support", tuple(sorted(rows)))

    def semantic_payload(self) -> list[list[int]]:
        return [[value, probability] for value, probability in self.support]

    @property
    def expectation_numerator(self) -> int:
        """Exact numerator whose denominator is ``PROBABILITY_DENOMINATOR``."""
        return sum(value * probability for value, probability in self.support)

    def quantile(self, probability_bps: int) -> int:
        if (
            isinstance(probability_bps, bool)
            or not isinstance(probability_bps, int)
            or not 0 <= probability_bps <= PROBABILITY_DENOMINATOR
        ):
            raise ValueError("quantile probability must be integer basis points in [0,10000]")
        if probability_bps == 0:
            return self.support[0][0]
        cumulative = 0
        for value, probability in self.support:
            cumulative += probability
            if cumulative >= probability_bps:
                return value
        return self.support[-1][0]

    def probability_at_least(self, threshold: int) -> int:
        return sum(probability for value, probability in self.support if value >= threshold)

    def probability_exactly(self, expected: int) -> int:
        return next((probability for value, probability in self.support if value == expected), 0)


@dataclass(frozen=True, slots=True)
class PlayerFixtureTarget:
    fixture_id: int
    gameweek: int
    player_id: OfficialPlayerId
    team_id: int
    opponent_team_id: int
    is_home: bool
    position: str

    def __post_init__(self) -> None:
        for label in ("fixture_id", "gameweek", "team_id", "opponent_team_id"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"forecast target {label} must be a positive integer")
        if self.team_id == self.opponent_team_id:
            raise ValueError("forecast target team cannot play itself")
        if self.position not in FPL_POSITIONS:
            raise ValueError(f"invalid forecast target position: {self.position!r}")
        if not isinstance(self.is_home, bool):
            raise ValueError("forecast target is_home must be boolean")

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.gameweek, self.fixture_id, int(self.player_id))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "gameweek": self.gameweek,
            "player_id": int(self.player_id),
            "team_id": self.team_id,
            "opponent_team_id": self.opponent_team_id,
            "is_home": self.is_home,
            "position": self.position,
        }

    @property
    def target_id(self) -> str:
        return canonical_sha256(
            {"schema_name": "apex-player-fixture-target", **self.semantic_payload()}
        )


@dataclass(frozen=True, slots=True)
class PlayerMatchOutcome:
    minutes: int
    goals: int = 0
    assists: int = 0
    goals_conceded_while_on_pitch: int = 0
    goalkeeper_saves: int = 0
    penalty_saves: int = 0
    penalty_misses: int = 0
    defensive_contributions: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    bonus_points: int = 0

    def __post_init__(self) -> None:
        for label in (
            "minutes",
            "goals",
            "assists",
            "goals_conceded_while_on_pitch",
            "goalkeeper_saves",
            "penalty_saves",
            "penalty_misses",
            "defensive_contributions",
            "yellow_cards",
            "red_cards",
            "own_goals",
            "bonus_points",
        ):
            _nonnegative_int(getattr(self, label), label=label)
        if self.minutes > 90:
            raise ValueError("single-fixture player minutes cannot exceed 90")
        if self.yellow_cards > 1 or self.red_cards > 1:
            raise ValueError("card event counts must be 0 or 1 per fixture")
        if self.bonus_points > 3:
            raise ValueError("FPL bonus_points must be in [0,3]")

    def semantic_payload(self) -> dict[str, int]:
        return {
            "minutes": self.minutes,
            "goals": self.goals,
            "assists": self.assists,
            "goals_conceded_while_on_pitch": self.goals_conceded_while_on_pitch,
            "goalkeeper_saves": self.goalkeeper_saves,
            "penalty_saves": self.penalty_saves,
            "penalty_misses": self.penalty_misses,
            "defensive_contributions": self.defensive_contributions,
            "yellow_cards": self.yellow_cards,
            "red_cards": self.red_cards,
            "own_goals": self.own_goals,
            "bonus_points": self.bonus_points,
        }


@dataclass(frozen=True, slots=True)
class PlayerFixtureScenario:
    scenario_id: str
    probability_bps: int
    outcome: PlayerMatchOutcome

    def __post_init__(self) -> None:
        scenario_id = str(self.scenario_id).strip()
        if not scenario_id:
            raise ValueError("forecast scenario_id cannot be empty")
        if (
            isinstance(self.probability_bps, bool)
            or not isinstance(self.probability_bps, int)
            or not 0 < self.probability_bps <= PROBABILITY_DENOMINATOR
        ):
            raise ValueError("scenario probability must be positive integer basis points")
        object.__setattr__(self, "scenario_id", scenario_id)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "probability_bps": self.probability_bps,
            "outcome": self.outcome.semantic_payload(),
        }


@dataclass(frozen=True, slots=True)
class PredictionRow:
    target: PlayerFixtureTarget
    disposition: PredictionDisposition
    scenarios: tuple[PlayerFixtureScenario, ...] = ()
    abstention_reason: str | None = None
    uncertainty_kind: UncertaintyKind | None = None
    deterministic_reason: str | None = None

    def __post_init__(self) -> None:
        scenarios = tuple(sorted(self.scenarios, key=lambda item: item.scenario_id))
        if self.disposition is PredictionDisposition.ABSTAINED:
            reason = str(self.abstention_reason or "").strip()
            if not reason:
                raise ValueError("abstained prediction requires a reason")
            if scenarios:
                raise ValueError("abstained prediction cannot contain scenarios")
            if self.uncertainty_kind is not None or self.deterministic_reason is not None:
                raise ValueError("abstained prediction cannot declare forecast uncertainty")
            object.__setattr__(self, "abstention_reason", reason)
            object.__setattr__(self, "scenarios", scenarios)
            return

        if self.abstention_reason is not None:
            raise ValueError("predicted row cannot have abstention_reason")
        if not scenarios:
            raise ValueError("predicted row requires scenarios")
        ids = [item.scenario_id for item in scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("prediction row contains duplicate scenario IDs")
        total = sum(item.probability_bps for item in scenarios)
        if total != PROBABILITY_DENOMINATOR:
            raise ValueError(
                f"prediction scenario mass {total} != {PROBABILITY_DENOMINATOR}"
            )
        unique_outcomes = {
            canonical_sha256(item.outcome.semantic_payload()) for item in scenarios
        }
        if len(unique_outcomes) == 1:
            if self.uncertainty_kind is not UncertaintyKind.STRUCTURALLY_DETERMINISTIC:
                raise ValueError("degenerate future prediction must be explicitly structural")
            reason = str(self.deterministic_reason or "").strip()
            if not reason:
                raise ValueError("structurally deterministic forecast requires a reason")
            object.__setattr__(self, "deterministic_reason", reason)
        else:
            if self.uncertainty_kind is not UncertaintyKind.PROBABILISTIC:
                raise ValueError("non-degenerate future prediction must be PROBABILISTIC")
            if self.deterministic_reason is not None:
                raise ValueError("probabilistic prediction cannot have deterministic_reason")
        object.__setattr__(self, "scenarios", scenarios)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "target": self.target.semantic_payload(),
            "disposition": self.disposition.value,
            "scenarios": [item.semantic_payload() for item in self.scenarios],
            "abstention_reason": self.abstention_reason,
            "uncertainty_kind": (
                None if self.uncertainty_kind is None else self.uncertainty_kind.value
            ),
            "deterministic_reason": self.deterministic_reason,
        }

    @property
    def prediction_row_id(self) -> str:
        return canonical_sha256(
            {"schema_name": "apex-player-fixture-prediction", **self.semantic_payload()}
        )


@dataclass(frozen=True, slots=True)
class PredictionBatch:
    season: str
    feature_snapshot_id: FeatureSnapshotId
    feature_cutoff: str
    global_world_id: GlobalWorldId
    model_artifact_id: ModelArtifactId
    gameweeks: tuple[int, ...]
    rows: tuple[PredictionRow, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported PredictionBatch schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("prediction batch season cannot be empty")
        cutoff = _aware_iso(self.feature_cutoff, label="prediction feature_cutoff")
        gameweeks = tuple(sorted(set(self.gameweeks)))
        if not gameweeks or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in gameweeks
        ):
            raise ValueError("prediction batch requires positive integer gameweeks")
        rows = tuple(sorted(self.rows, key=lambda item: item.target.key))
        keys = [row.target.key for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("prediction batch contains duplicate player-fixture targets")
        if any(row.target.gameweek not in gameweeks for row in rows):
            raise ValueError("prediction row lies outside declared gameweeks")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "feature_cutoff", cutoff)
        object.__setattr__(self, "gameweeks", gameweeks)
        object.__setattr__(self, "rows", rows)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-prediction-batch",
            "schema_version": self.schema_version,
            "season": self.season,
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "feature_cutoff": self.feature_cutoff,
            "global_world_id": str(self.global_world_id),
            "model_artifact_id": str(self.model_artifact_id),
            "gameweeks": list(self.gameweeks),
            "prediction_row_ids": [row.prediction_row_id for row in self.rows],
        }

    @property
    def prediction_batch_id(self) -> PredictionBatchId:
        return PredictionBatchId(canonical_sha256(self.semantic_payload()))

    def require_exact_target_coverage(
        self,
        expected_targets: Iterable[PlayerFixtureTarget],
    ) -> None:
        expected = {item.key: item for item in expected_targets}
        actual = {row.target.key: row.target for row in self.rows}
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            raise ValueError(
                f"prediction target coverage mismatch missing={missing[:10]} extra={extra[:10]}"
            )
        mismatched = [
            key
            for key, target in expected.items()
            if actual[key].semantic_payload() != target.semantic_payload()
        ]
        if mismatched:
            raise ValueError(f"prediction target identity/context mismatch: {mismatched[:10]}")


@dataclass(frozen=True, slots=True)
class ForecastUncertainty:
    uncertainty_kind: UncertaintyKind
    deterministic_reason: str | None
    scenario_count: int
    minutes_p10: int
    minutes_p50: int
    minutes_p90: int
    points_p10: int
    points_p50: int
    points_p90: int
    appearance_probability_bps: int
    sixty_plus_probability_bps: int

    def semantic_payload(self) -> dict[str, object]:
        return {
            "uncertainty_kind": self.uncertainty_kind.value,
            "deterministic_reason": self.deterministic_reason,
            "scenario_count": self.scenario_count,
            "minutes_p10": self.minutes_p10,
            "minutes_p50": self.minutes_p50,
            "minutes_p90": self.minutes_p90,
            "points_p10": self.points_p10,
            "points_p50": self.points_p50,
            "points_p90": self.points_p90,
            "appearance_probability_bps": self.appearance_probability_bps,
            "sixty_plus_probability_bps": self.sixty_plus_probability_bps,
        }


@dataclass(frozen=True, slots=True)
class PlayerFixtureForecast:
    target: PlayerFixtureTarget
    prediction_row_id: str
    minutes_distribution: DiscreteIntegerDistribution
    points_distribution: DiscreteIntegerDistribution
    uncertainty: ForecastUncertainty

    @property
    def expected_minutes_numerator(self) -> int:
        return self.minutes_distribution.expectation_numerator

    @property
    def expected_points_numerator(self) -> int:
        return self.points_distribution.expectation_numerator

    def semantic_payload(self) -> dict[str, object]:
        return {
            "target": self.target.semantic_payload(),
            "prediction_row_id": self.prediction_row_id,
            "minutes_distribution": self.minutes_distribution.semantic_payload(),
            "points_distribution": self.points_distribution.semantic_payload(),
            "uncertainty": self.uncertainty.semantic_payload(),
        }


@dataclass(frozen=True, slots=True)
class ForecastAbstention:
    target: PlayerFixtureTarget
    prediction_row_id: str
    reason: str

    def __post_init__(self) -> None:
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("forecast abstention reason cannot be empty")
        object.__setattr__(self, "reason", reason)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "target": self.target.semantic_payload(),
            "prediction_row_id": self.prediction_row_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Forecast:
    season: str
    feature_snapshot_id: FeatureSnapshotId
    feature_cutoff: str
    global_world_id: GlobalWorldId
    ruleset_id: RuleSetId
    model_artifact_id: ModelArtifactId
    prediction_batch_id: PredictionBatchId
    use_mode: ForecastUseMode
    model_qualification_state: ModelQualificationState
    rows: tuple[PlayerFixtureForecast, ...]
    abstentions: tuple[ForecastAbstention, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported Forecast schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("forecast season cannot be empty")
        cutoff = _aware_iso(self.feature_cutoff, label="forecast feature_cutoff")
        rows = tuple(sorted(self.rows, key=lambda item: item.target.key))
        abstentions = tuple(sorted(self.abstentions, key=lambda item: item.target.key))
        predicted_keys = [item.target.key for item in rows]
        abstained_keys = [item.target.key for item in abstentions]
        if len(predicted_keys) != len(set(predicted_keys)):
            raise ValueError("forecast contains duplicate predicted targets")
        if len(abstained_keys) != len(set(abstained_keys)):
            raise ValueError("forecast contains duplicate abstained targets")
        overlap = sorted(set(predicted_keys) & set(abstained_keys))
        if overlap:
            raise ValueError(f"forecast target cannot be predicted and abstained: {overlap[:10]}")
        if (
            self.use_mode is ForecastUseMode.PRODUCTION
            and self.model_qualification_state is not ModelQualificationState.QUALIFIED
        ):
            raise ValueError("production forecast cannot carry an unqualified model")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "feature_cutoff", cutoff)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "abstentions", abstentions)

    @property
    def production_eligible(self) -> bool:
        return (
            self.use_mode is ForecastUseMode.PRODUCTION
            and self.model_qualification_state is ModelQualificationState.QUALIFIED
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-probabilistic-forecast",
            "schema_version": self.schema_version,
            "season": self.season,
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "feature_cutoff": self.feature_cutoff,
            "global_world_id": str(self.global_world_id),
            "ruleset_id": str(self.ruleset_id),
            "model_artifact_id": str(self.model_artifact_id),
            "prediction_batch_id": str(self.prediction_batch_id),
            "use_mode": self.use_mode.value,
            "model_qualification_state": self.model_qualification_state.value,
            "rows": [row.semantic_payload() for row in self.rows],
            "abstentions": [row.semantic_payload() for row in self.abstentions],
        }

    @property
    def forecast_id(self) -> ForecastId:
        return ForecastId(canonical_sha256(self.semantic_payload()))

    def player_gameweek_expected_points_numerator(
        self,
        player_id: OfficialPlayerId,
        gameweek: int,
    ) -> int:
        return sum(
            row.expected_points_numerator
            for row in self.rows
            if row.target.player_id == player_id and row.target.gameweek == gameweek
        )


def _mapping_int(mapping: dict[str, object], key: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"scoring rule {key} must be integer")
    return value


def score_match_outcome(
    *,
    ruleset: RuleSet,
    position: str,
    outcome: PlayerMatchOutcome,
) -> int:
    """Apply exact sealed FPL scoring mechanics to one realised fixture outcome."""

    if position not in FPL_POSITIONS:
        raise ValueError(f"invalid FPL position: {position!r}")
    if position != "GK" and (outcome.goalkeeper_saves or outcome.penalty_saves):
        raise ValueError("non-goalkeeper outcome cannot contain goalkeeper save events")
    scoring = ruleset.mapping("FPL-SCORING-BASE-001")
    goals = scoring["goals"]
    clean_sheet = scoring["clean_sheet"]
    thresholds = scoring["defensive_contribution_threshold"]
    if not isinstance(goals, dict) or not isinstance(clean_sheet, dict) or not isinstance(thresholds, dict):
        raise TypeError("scoring position maps are malformed")

    points = 0
    if outcome.minutes > 0:
        appearance_key = "appearance_60_plus" if outcome.minutes >= 60 else "appearance_up_to_59"
        points += _mapping_int(scoring, appearance_key)
    points += outcome.goals * int(goals[position])
    points += outcome.assists * _mapping_int(scoring, "assist")

    if outcome.minutes >= 60 and outcome.goals_conceded_while_on_pitch == 0:
        points += int(clean_sheet[position])

    if position == "GK":
        saves_per_point = _mapping_int(scoring, "goalkeeper_saves_per_point")
        save_point = _mapping_int(scoring, "goalkeeper_save_point")
        points += (outcome.goalkeeper_saves // saves_per_point) * save_point
        points += outcome.penalty_saves * _mapping_int(scoring, "penalty_save")

    if position in thresholds:
        threshold = int(thresholds[position])
        if outcome.defensive_contributions >= threshold:
            points += _mapping_int(scoring, "defensive_contribution_points")

    points += outcome.penalty_misses * _mapping_int(scoring, "penalty_miss")
    if position in {"GK", "DEF"}:
        conceded_per_penalty = _mapping_int(scoring, "goals_conceded_per_penalty")
        points += (
            outcome.goals_conceded_while_on_pitch // conceded_per_penalty
        ) * _mapping_int(scoring, "goals_conceded_penalty")
    points += outcome.yellow_cards * _mapping_int(scoring, "yellow_card")
    points += outcome.red_cards * _mapping_int(scoring, "red_card")
    points += outcome.own_goals * _mapping_int(scoring, "own_goal")
    points += outcome.bonus_points
    return points


def _distribution(values: Iterable[tuple[int, int]]) -> DiscreteIntegerDistribution:
    aggregated: dict[int, int] = {}
    for value, probability in values:
        aggregated[value] = aggregated.get(value, 0) + probability
    return DiscreteIntegerDistribution(tuple(aggregated.items()))


def compile_prediction_row(
    row: PredictionRow,
    *,
    ruleset: RuleSet,
) -> PlayerFixtureForecast | ForecastAbstention:
    if row.disposition is PredictionDisposition.ABSTAINED:
        return ForecastAbstention(
            target=row.target,
            prediction_row_id=row.prediction_row_id,
            reason=str(row.abstention_reason),
        )

    minutes_distribution = _distribution(
        (scenario.outcome.minutes, scenario.probability_bps) for scenario in row.scenarios
    )
    points_distribution = _distribution(
        (
            score_match_outcome(
                ruleset=ruleset,
                position=row.target.position,
                outcome=scenario.outcome,
            ),
            scenario.probability_bps,
        )
        for scenario in row.scenarios
    )
    uncertainty = ForecastUncertainty(
        uncertainty_kind=row.uncertainty_kind or UncertaintyKind.PROBABILISTIC,
        deterministic_reason=row.deterministic_reason,
        scenario_count=len(row.scenarios),
        minutes_p10=minutes_distribution.quantile(1_000),
        minutes_p50=minutes_distribution.quantile(5_000),
        minutes_p90=minutes_distribution.quantile(9_000),
        points_p10=points_distribution.quantile(1_000),
        points_p50=points_distribution.quantile(5_000),
        points_p90=points_distribution.quantile(9_000),
        appearance_probability_bps=(
            PROBABILITY_DENOMINATOR - minutes_distribution.probability_exactly(0)
        ),
        sixty_plus_probability_bps=minutes_distribution.probability_at_least(60),
    )
    return PlayerFixtureForecast(
        target=row.target,
        prediction_row_id=row.prediction_row_id,
        minutes_distribution=minutes_distribution,
        points_distribution=points_distribution,
        uncertainty=uncertainty,
    )


def compile_forecast(
    *,
    prediction_batch: PredictionBatch,
    ruleset: RuleSet,
    model: ForecastModelArtifact,
    use_mode: ForecastUseMode,
    expected_targets: Iterable[PlayerFixtureTarget] | None = None,
) -> Forecast:
    """Compile model scenarios into exact FPL point distributions without fetching data."""

    if prediction_batch.season != ruleset.season:
        raise ValueError("prediction batch season does not match RuleSet")
    if prediction_batch.model_artifact_id != model.model_artifact_id:
        raise ValueError("prediction batch model identity does not match model artifact")
    if expected_targets is not None:
        prediction_batch.require_exact_target_coverage(expected_targets)
    model.require_valid_for(
        season=prediction_batch.season,
        feature_cutoff=prediction_batch.feature_cutoff,
        horizon_gameweeks=len(prediction_batch.gameweeks),
        production=use_mode is ForecastUseMode.PRODUCTION,
    )

    forecasts: list[PlayerFixtureForecast] = []
    abstentions: list[ForecastAbstention] = []
    for row in prediction_batch.rows:
        compiled = compile_prediction_row(row, ruleset=ruleset)
        if isinstance(compiled, ForecastAbstention):
            abstentions.append(compiled)
        else:
            forecasts.append(compiled)

    return Forecast(
        season=prediction_batch.season,
        feature_snapshot_id=prediction_batch.feature_snapshot_id,
        feature_cutoff=prediction_batch.feature_cutoff,
        global_world_id=prediction_batch.global_world_id,
        ruleset_id=ruleset.ruleset_id,
        model_artifact_id=model.model_artifact_id,
        prediction_batch_id=prediction_batch.prediction_batch_id,
        use_mode=use_mode,
        model_qualification_state=model.qualification_state,
        rows=tuple(forecasts),
        abstentions=tuple(abstentions),
    )
