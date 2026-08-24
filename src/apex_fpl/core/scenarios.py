"""Constitutional joint-scenario and convergence contracts for Apex V2.

Scenario generation is deliberately outside the post-seal decision runtime. This module
contains only immutable semantic contracts: a qualified generator identity, one ordered
joint scenario stream, governed convergence policy and typed robustness evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .canonical import canonical_sha256
from .decision import RationalValue
from .identity import OfficialPlayerId
from .ids import (
    DecisionId,
    ForecastId,
    RobustnessReportId,
    ScenarioGeneratorId,
    ScenarioPolicyId,
    ScenarioSetId,
)


PROBABILITY_BPS = 10_000
HISTORICAL_SCENARIO_FLOOR = 256


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


def _artifact_id(value: str | None, *, label: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required")
        return None
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _nonnegative_rational(value: RationalValue, *, label: str) -> None:
    if value.numerator < 0:
        raise ValueError(f"{label} cannot be negative")


class ScenarioQualificationState(str, Enum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class ScenarioConvergenceStatus(str, Enum):
    CONVERGED = "CONVERGED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class ScenarioGeneratorArtifact:
    generator_name: str
    generator_version: str
    generator_contract: str
    rng_algorithm: str
    parameter_artifact_ids: tuple[str, ...]
    qualification_state: ScenarioQualificationState
    qualification_artifact_id: str | None
    valid_seasons: tuple[str, ...]
    trained_through: str
    first_available_at: str
    max_horizon_gameweeks: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ScenarioGeneratorArtifact schema_version")
        for label in (
            "generator_name",
            "generator_version",
            "generator_contract",
            "rng_algorithm",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"scenario generator {label} cannot be empty")
            object.__setattr__(self, label, value)
        parameters = tuple(
            sorted(
                {
                    str(_artifact_id(item, label="scenario generator parameter artifact"))
                    for item in self.parameter_artifact_ids
                }
            )
        )
        if not parameters:
            raise ValueError("scenario generator requires immutable parameter evidence")
        seasons = tuple(sorted({str(item).strip() for item in self.valid_seasons if str(item).strip()}))
        if not seasons:
            raise ValueError("scenario generator requires at least one valid season")
        trained = _aware_iso(self.trained_through, label="scenario generator trained_through")
        available = _aware_iso(
            self.first_available_at,
            label="scenario generator first_available_at",
        )
        if _point(trained) > _point(available):
            raise ValueError("scenario generator cannot be available before training cutoff")
        _positive_int(self.max_horizon_gameweeks, label="max_horizon_gameweeks")
        qualification = _artifact_id(
            self.qualification_artifact_id,
            label="scenario generator qualification artifact",
            required=self.qualification_state is ScenarioQualificationState.QUALIFIED,
        )
        object.__setattr__(self, "parameter_artifact_ids", parameters)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "valid_seasons", seasons)
        object.__setattr__(self, "trained_through", trained)
        object.__setattr__(self, "first_available_at", available)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-scenario-generator",
            "schema_version": self.schema_version,
            "generator_name": self.generator_name,
            "generator_version": self.generator_version,
            "generator_contract": self.generator_contract,
            "rng_algorithm": self.rng_algorithm,
            "parameter_artifact_ids": list(self.parameter_artifact_ids),
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "valid_seasons": list(self.valid_seasons),
            "trained_through": self.trained_through,
            "first_available_at": self.first_available_at,
            "max_horizon_gameweeks": self.max_horizon_gameweeks,
        }

    @property
    def scenario_generator_id(self) -> ScenarioGeneratorId:
        return ScenarioGeneratorId(canonical_sha256(self.semantic_payload()))

    def require_valid_for(
        self,
        *,
        season: str,
        forecast_cutoff: str,
        horizon_gameweeks: int,
        production: bool,
    ) -> None:
        cutoff = _aware_iso(forecast_cutoff, label="scenario forecast_cutoff")
        if season not in self.valid_seasons:
            raise ValueError(f"scenario generator is not valid for season {season}")
        if horizon_gameweeks <= 0 or horizon_gameweeks > self.max_horizon_gameweeks:
            raise ValueError("scenario horizon lies outside generator validity scope")
        if _point(self.trained_through) > _point(cutoff):
            raise ValueError("scenario generator training leaks beyond forecast cutoff")
        if _point(self.first_available_at) > _point(cutoff):
            raise ValueError("scenario generator was not available at forecast cutoff")
        if self.qualification_state is ScenarioQualificationState.SUSPENDED:
            raise ValueError("scenario generator is suspended")
        if production and self.qualification_state is not ScenarioQualificationState.QUALIFIED:
            raise ValueError("production scenarios require a qualified generator")


@dataclass(frozen=True, slots=True)
class JointPlayerGameweekOutcome:
    player_id: OfficialPlayerId
    gameweek: int
    appeared: bool
    points: int

    def __post_init__(self) -> None:
        _positive_int(self.gameweek, label="scenario outcome gameweek")
        if not isinstance(self.appeared, bool):
            raise ValueError("scenario outcome appeared must be boolean")
        if isinstance(self.points, bool) or not isinstance(self.points, int):
            raise ValueError("scenario outcome points must be integer")
        if not self.appeared and self.points != 0:
            raise ValueError("non-appearing player cannot receive FPL points in a scenario")

    @property
    def key(self) -> tuple[int, int]:
        return (self.gameweek, int(self.player_id))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "player_id": int(self.player_id),
            "gameweek": self.gameweek,
            "appeared": self.appeared,
            "points": self.points,
        }


@dataclass(frozen=True, slots=True)
class JointScenario:
    ordinal: int
    weight: int
    outcomes: tuple[JointPlayerGameweekOutcome, ...]

    def __post_init__(self) -> None:
        _positive_int(self.ordinal, label="scenario ordinal")
        _positive_int(self.weight, label="scenario weight")
        outcomes = tuple(sorted(self.outcomes, key=lambda row: row.key))
        keys = [row.key for row in outcomes]
        if not outcomes or len(keys) != len(set(keys)):
            raise ValueError("joint scenario requires unique player-gameweek outcomes")
        object.__setattr__(self, "outcomes", outcomes)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "weight": self.weight,
            "outcomes": [row.semantic_payload() for row in self.outcomes],
        }

    @property
    def scenario_id(self) -> str:
        return canonical_sha256(
            {"schema_name": "apex-joint-scenario", **self.semantic_payload()}
        )


@dataclass(frozen=True, slots=True)
class ScenarioSet:
    season: str
    forecast_id: ForecastId
    scenario_generator_id: ScenarioGeneratorId
    rng_algorithm: str
    seed: int
    gameweeks: tuple[int, ...]
    player_ids: tuple[OfficialPlayerId, ...]
    scenarios: tuple[JointScenario, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ScenarioSet schema_version")
        season = str(self.season).strip()
        rng = str(self.rng_algorithm).strip()
        if not season or not rng:
            raise ValueError("ScenarioSet requires season and rng_algorithm")
        _nonnegative_int(self.seed, label="scenario seed")
        gameweeks = tuple(sorted(set(self.gameweeks)))
        if not gameweeks or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in gameweeks
        ):
            raise ValueError("ScenarioSet requires positive integer gameweeks")
        players = tuple(sorted(set(self.player_ids)))
        if not players:
            raise ValueError("ScenarioSet requires player coverage")
        scenarios = tuple(sorted(self.scenarios, key=lambda row: row.ordinal))
        ordinals = [row.ordinal for row in scenarios]
        if ordinals != list(range(1, len(scenarios) + 1)):
            raise ValueError("ScenarioSet ordinals must be contiguous from one")
        expected_keys = {(gw, int(pid)) for gw in gameweeks for pid in players}
        for scenario in scenarios:
            actual = {row.key for row in scenario.outcomes}
            if actual != expected_keys:
                missing = sorted(expected_keys - actual)[:10]
                extra = sorted(actual - expected_keys)[:10]
                raise ValueError(
                    f"ScenarioSet coverage mismatch missing={missing} extra={extra}"
                )
        artifacts = tuple(
            sorted(
                {
                    str(_artifact_id(item, label="scenario source artifact"))
                    for item in self.source_artifact_ids
                }
            )
        )
        if not artifacts:
            raise ValueError("ScenarioSet requires immutable source artifacts")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "rng_algorithm", rng)
        object.__setattr__(self, "gameweeks", gameweeks)
        object.__setattr__(self, "player_ids", players)
        object.__setattr__(self, "scenarios", scenarios)
        object.__setattr__(self, "source_artifact_ids", artifacts)

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    @property
    def total_weight(self) -> int:
        return sum(row.weight for row in self.scenarios)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-scenario-set",
            "schema_version": self.schema_version,
            "season": self.season,
            "forecast_id": str(self.forecast_id),
            "scenario_generator_id": str(self.scenario_generator_id),
            "rng_algorithm": self.rng_algorithm,
            "seed": self.seed,
            "gameweeks": list(self.gameweeks),
            "player_ids": [int(item) for item in self.player_ids],
            "scenario_ids": [row.scenario_id for row in self.scenarios],
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def scenario_set_id(self) -> ScenarioSetId:
        return ScenarioSetId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class ScenarioConvergencePolicy:
    policy_name: str
    policy_version: str
    season: str
    qualification_state: ScenarioQualificationState
    qualification_artifact_id: str | None
    first_available_at: str
    checkpoint_counts: tuple[int, ...]
    max_scenarios: int
    cvar_alpha_bps: int
    lower_quantile_bps: int
    mean_tolerance: RationalValue
    cvar_tolerance: RationalValue
    tail_tolerance: RationalValue
    xp_absolute_tolerance: RationalValue
    sampling_sigma_multiplier: RationalValue
    max_ev_regret_tolerance: RationalValue
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ScenarioConvergencePolicy schema_version")
        for label in ("policy_name", "policy_version", "season"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"scenario convergence {label} cannot be empty")
            object.__setattr__(self, label, value)
        checkpoints = tuple(self.checkpoint_counts)
        if (
            len(checkpoints) < 2
            or any(
                isinstance(item, bool) or not isinstance(item, int)
                for item in checkpoints
            )
            or any(item < HISTORICAL_SCENARIO_FLOOR for item in checkpoints)
            or tuple(sorted(set(checkpoints))) != checkpoints
        ):
            raise ValueError(
                "scenario convergence checkpoints must be unique increasing counts >= 256"
            )
        _positive_int(self.max_scenarios, label="scenario max_scenarios")
        if checkpoints[-1] > self.max_scenarios:
            raise ValueError("scenario checkpoints cannot exceed max_scenarios")
        for label in ("cvar_alpha_bps", "lower_quantile_bps"):
            value = getattr(self, label)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 < value < PROBABILITY_BPS
            ):
                raise ValueError(f"{label} must be integer basis points in (0,10000)")
        for label in (
            "mean_tolerance",
            "cvar_tolerance",
            "tail_tolerance",
            "xp_absolute_tolerance",
            "sampling_sigma_multiplier",
            "max_ev_regret_tolerance",
        ):
            _nonnegative_rational(getattr(self, label), label=label)
        available = _aware_iso(
            self.first_available_at,
            label="scenario convergence first_available_at",
        )
        qualification = _artifact_id(
            self.qualification_artifact_id,
            label="scenario convergence qualification artifact",
            required=self.qualification_state is ScenarioQualificationState.QUALIFIED,
        )
        object.__setattr__(self, "checkpoint_counts", checkpoints)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "first_available_at", available)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-scenario-convergence-policy",
            "schema_version": self.schema_version,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "season": self.season,
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "first_available_at": self.first_available_at,
            "checkpoint_counts": list(self.checkpoint_counts),
            "max_scenarios": self.max_scenarios,
            "cvar_alpha_bps": self.cvar_alpha_bps,
            "lower_quantile_bps": self.lower_quantile_bps,
            "mean_tolerance": self.mean_tolerance.semantic_payload(),
            "cvar_tolerance": self.cvar_tolerance.semantic_payload(),
            "tail_tolerance": self.tail_tolerance.semantic_payload(),
            "xp_absolute_tolerance": self.xp_absolute_tolerance.semantic_payload(),
            "sampling_sigma_multiplier": self.sampling_sigma_multiplier.semantic_payload(),
            "max_ev_regret_tolerance": self.max_ev_regret_tolerance.semantic_payload(),
        }

    @property
    def scenario_policy_id(self) -> ScenarioPolicyId:
        return ScenarioPolicyId(canonical_sha256(self.semantic_payload()))

    @property
    def production_qualified(self) -> bool:
        return (
            self.qualification_state is ScenarioQualificationState.QUALIFIED
            and self.qualification_artifact_id is not None
        )

    def require_available_for(self, *, season: str, cutoff: str, production: bool) -> None:
        point = _aware_iso(cutoff, label="scenario convergence cutoff")
        if season != self.season:
            raise ValueError(f"scenario convergence policy is not valid for season {season}")
        if _point(self.first_available_at) > _point(point):
            raise ValueError("scenario convergence policy was not available at cutoff")
        if self.qualification_state is ScenarioQualificationState.SUSPENDED:
            raise ValueError("scenario convergence policy is suspended")
        if production and not self.production_qualified:
            raise ValueError("production robustness requires a qualified convergence policy")


@dataclass(frozen=True, slots=True)
class ActionRobustnessMetrics:
    action_id: str
    sample_count: int
    mean_points: RationalValue
    lower_cvar_points: RationalValue
    lower_quantile_points: int

    def __post_init__(self) -> None:
        action_id = str(self.action_id).strip()
        if not action_id:
            raise ValueError("action robustness requires action_id")
        _positive_int(self.sample_count, label="action robustness sample_count")
        if isinstance(self.lower_quantile_points, bool) or not isinstance(
            self.lower_quantile_points, int
        ):
            raise ValueError("lower_quantile_points must be integer")
        object.__setattr__(self, "action_id", action_id)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "sample_count": self.sample_count,
            "mean_points": self.mean_points.semantic_payload(),
            "lower_cvar_points": self.lower_cvar_points.semantic_payload(),
            "lower_quantile_points": self.lower_quantile_points,
        }


@dataclass(frozen=True, slots=True)
class ScenarioConvergenceCheckpoint:
    sample_count: int
    metrics: tuple[ActionRobustnessMetrics, ...]
    mean_ranking: tuple[str, ...]
    cvar_ranking: tuple[str, ...]
    tail_ranking: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive_int(self.sample_count, label="convergence sample_count")
        metrics = tuple(sorted(self.metrics, key=lambda row: row.action_id))
        ids = tuple(row.action_id for row in metrics)
        if not metrics or len(ids) != len(set(ids)):
            raise ValueError("convergence checkpoint requires unique action metrics")
        if any(row.sample_count != self.sample_count for row in metrics):
            raise ValueError("checkpoint metric sample counts must match checkpoint")
        expected = set(ids)
        for label in ("mean_ranking", "cvar_ranking", "tail_ranking"):
            ranking = tuple(getattr(self, label))
            if set(ranking) != expected or len(ranking) != len(expected):
                raise ValueError(f"{label} must rank every action exactly once")
            object.__setattr__(self, label, ranking)
        object.__setattr__(self, "metrics", metrics)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "metrics": [row.semantic_payload() for row in self.metrics],
            "mean_ranking": list(self.mean_ranking),
            "cvar_ranking": list(self.cvar_ranking),
            "tail_ranking": list(self.tail_ranking),
        }


@dataclass(frozen=True, slots=True)
class RobustnessReport:
    decision_id: DecisionId
    forecast_id: ForecastId
    scenario_set_id: ScenarioSetId
    scenario_policy_id: ScenarioPolicyId
    ev_anchor_action_id: str
    robust_preferred_action_id: str | None
    robust_preferred_ev_regret: RationalValue | None
    status: ScenarioConvergenceStatus
    xp_reconciled: bool
    checkpoints: tuple[ScenarioConvergenceCheckpoint, ...]
    blockers: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported RobustnessReport schema_version")
        if not isinstance(self.status, ScenarioConvergenceStatus):
            raise ValueError("robustness report status must be ScenarioConvergenceStatus")
        if not isinstance(self.xp_reconciled, bool):
            raise ValueError("robustness report xp_reconciled must be boolean")
        anchor = str(self.ev_anchor_action_id).strip()
        if not anchor:
            raise ValueError("robustness report requires EV anchor action")
        checkpoints = tuple(sorted(self.checkpoints, key=lambda row: row.sample_count))
        if len({row.sample_count for row in checkpoints}) != len(checkpoints):
            raise ValueError("robustness report contains duplicate checkpoints")
        action_sets = tuple(
            frozenset(metric.action_id for metric in checkpoint.metrics)
            for checkpoint in checkpoints
        )
        if action_sets and any(action_set != action_sets[0] for action_set in action_sets[1:]):
            raise ValueError("robustness report checkpoint action sets must be identical")
        if action_sets and anchor not in action_sets[0]:
            raise ValueError("robustness report EV anchor must be present in checkpoint actions")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        preferred = self.robust_preferred_action_id
        regret = self.robust_preferred_ev_regret
        if preferred is not None:
            preferred = str(preferred).strip()
            if not preferred or regret is None:
                raise ValueError("robust preferred action requires explicit EV regret")
            _nonnegative_rational(regret, label="robust preferred EV regret")
            if action_sets and preferred not in action_sets[0]:
                raise ValueError(
                    "robustness preferred action must be present in checkpoint actions"
                )
        elif regret is not None:
            raise ValueError("robust EV regret requires a preferred action")

        if self.status is ScenarioConvergenceStatus.CONVERGED:
            if not self.xp_reconciled or blockers:
                raise ValueError("CONVERGED robustness cannot carry reconciliation blockers")
            if len(checkpoints) < 2:
                raise ValueError("CONVERGED robustness requires at least two checkpoints")
            if preferred is None or regret is None:
                raise ValueError(
                    "CONVERGED robustness requires a bounded preferred-action diagnostic"
                )
        else:
            if not blockers:
                raise ValueError("INCONCLUSIVE robustness requires explicit blockers")
            if preferred is not None or regret is not None:
                raise ValueError(
                    "INCONCLUSIVE robustness cannot expose a preferred action or EV regret"
                )

        object.__setattr__(self, "ev_anchor_action_id", anchor)
        object.__setattr__(self, "robust_preferred_action_id", preferred)
        object.__setattr__(self, "checkpoints", checkpoints)
        object.__setattr__(self, "blockers", blockers)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-robustness-report",
            "schema_version": self.schema_version,
            "decision_id": str(self.decision_id),
            "forecast_id": str(self.forecast_id),
            "scenario_set_id": str(self.scenario_set_id),
            "scenario_policy_id": str(self.scenario_policy_id),
            "ev_anchor_action_id": self.ev_anchor_action_id,
            "robust_preferred_action_id": self.robust_preferred_action_id,
            "robust_preferred_ev_regret": (
                None
                if self.robust_preferred_ev_regret is None
                else self.robust_preferred_ev_regret.semantic_payload()
            ),
            "status": self.status.value,
            "xp_reconciled": self.xp_reconciled,
            "checkpoints": [row.semantic_payload() for row in self.checkpoints],
            "blockers": list(self.blockers),
        }

    @property
    def robustness_report_id(self) -> RobustnessReportId:
        return RobustnessReportId(canonical_sha256(self.semantic_payload()))
