"""Admission registry for sealed scenario generators and convergence policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.empirical_qualification_admission import (
    verify_typed_empirical_qualification,
)
from apex_fpl.core.decision import RationalValue
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.ids import ScenarioGeneratorId, ScenarioPolicyId
from apex_fpl.core.scenarios import (
    ScenarioConvergencePolicy,
    ScenarioGeneratorArtifact,
    ScenarioQualificationState,
    ScenarioSet,
)


@dataclass(frozen=True, slots=True)
class ScenarioGovernanceRegistry:
    season: str
    generators: tuple[ScenarioGeneratorArtifact, ...]
    policies: tuple[ScenarioConvergencePolicy, ...]
    champion_generator_id: ScenarioGeneratorId | None = None
    champion_policy_id: ScenarioPolicyId | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported scenario governance registry schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("scenario governance registry requires season")
        generators = tuple(
            sorted(self.generators, key=lambda row: str(row.scenario_generator_id))
        )
        policies = tuple(sorted(self.policies, key=lambda row: str(row.scenario_policy_id)))
        generator_ids = [row.scenario_generator_id for row in generators]
        policy_ids = [row.scenario_policy_id for row in policies]
        if len(generator_ids) != len(set(generator_ids)):
            raise ValueError("scenario registry contains duplicate generator identities")
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("scenario registry contains duplicate policy identities")
        if any(season not in row.valid_seasons for row in generators):
            raise ValueError("scenario generator registry season mismatch")
        if any(row.season != season for row in policies):
            raise ValueError("scenario convergence registry season mismatch")
        if self.champion_generator_id is not None:
            champion = next(
                (
                    row
                    for row in generators
                    if row.scenario_generator_id == self.champion_generator_id
                ),
                None,
            )
            if champion is None:
                raise ValueError("scenario champion generator is not registered")
            if champion.qualification_state is not ScenarioQualificationState.QUALIFIED:
                raise ValueError("scenario champion generator must be QUALIFIED")
        if self.champion_policy_id is not None:
            champion_policy = next(
                (row for row in policies if row.scenario_policy_id == self.champion_policy_id),
                None,
            )
            if champion_policy is None:
                raise ValueError("scenario champion policy is not registered")
            if not champion_policy.production_qualified:
                raise ValueError("scenario champion policy must be production qualified")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "generators", generators)
        object.__setattr__(self, "policies", policies)

    def generator(self, generator_id: ScenarioGeneratorId) -> ScenarioGeneratorArtifact | None:
        return next(
            (row for row in self.generators if row.scenario_generator_id == generator_id),
            None,
        )

    def policy(self, policy_id: ScenarioPolicyId) -> ScenarioConvergencePolicy | None:
        return next((row for row in self.policies if row.scenario_policy_id == policy_id), None)

    def champion_generator(self) -> ScenarioGeneratorArtifact | None:
        if self.champion_generator_id is None:
            return None
        return self.generator(self.champion_generator_id)

    def champion_policy(self) -> ScenarioConvergencePolicy | None:
        if self.champion_policy_id is None:
            return None
        return self.policy(self.champion_policy_id)

    def verify_generator_artifacts(
        self,
        generator: ScenarioGeneratorArtifact,
        *,
        store: ArtifactStore,
        production: bool,
        as_of: str | None = None,
    ) -> None:
        if self.generator(generator.scenario_generator_id) != generator:
            raise ValueError("scenario generator is not registered under semantic identity")
        for artifact_id in generator.parameter_artifact_ids:
            store.read_bytes(artifact_id)
        if generator.qualification_artifact_id is not None:
            store.read_bytes(generator.qualification_artifact_id)
        if production:
            if generator.qualification_state is not ScenarioQualificationState.QUALIFIED:
                raise ValueError("production scenario generator is not QUALIFIED")
            if self.champion_generator_id != generator.scenario_generator_id:
                raise ValueError("production scenario generator is not registered champion")
            if as_of is None:
                raise ValueError("production scenario generator verification requires explicit as_of")
            verify_typed_empirical_qualification(
                qualification_artifact_id=generator.qualification_artifact_id,
                subject_payload=generator.semantic_payload(),
                subject_kind="apex.scenario-generator",
                proof_id="PO-SCENARIO-CONVERGENCE-001",
                season=self.season,
                as_of=as_of,
                store=store,
            )

    def verify_policy_artifacts(
        self,
        policy: ScenarioConvergencePolicy,
        *,
        store: ArtifactStore,
        production: bool,
        as_of: str | None = None,
    ) -> None:
        if self.policy(policy.scenario_policy_id) != policy:
            raise ValueError("scenario convergence policy is not registered under semantic identity")
        if policy.qualification_artifact_id is not None:
            store.read_bytes(policy.qualification_artifact_id)
        if production:
            if not policy.production_qualified:
                raise ValueError("production scenario convergence policy is not QUALIFIED")
            if self.champion_policy_id != policy.scenario_policy_id:
                raise ValueError("production scenario convergence policy is not registered champion")
            if as_of is None:
                raise ValueError("production scenario policy verification requires explicit as_of")
            verify_typed_empirical_qualification(
                qualification_artifact_id=policy.qualification_artifact_id,
                subject_payload=policy.semantic_payload(),
                subject_kind="apex.scenario-policy",
                proof_id="PO-SCENARIO-CONVERGENCE-001",
                season=self.season,
                as_of=as_of,
                store=store,
            )

    def verify_runtime_contract(
        self,
        scenario_set: ScenarioSet,
        *,
        generator: ScenarioGeneratorArtifact,
        policy: ScenarioConvergencePolicy,
        forecast: Forecast,
        store: ArtifactStore,
        production: bool,
    ) -> None:
        """Bind one sealed ScenarioSet to its registered generator/policy and Forecast."""

        if scenario_set.season != self.season or forecast.season != self.season:
            raise ValueError("scenario runtime registry/Forecast/ScenarioSet season mismatch")
        if scenario_set.forecast_id != forecast.forecast_id:
            raise ValueError("ScenarioSet does not bind to supplied Forecast identity")
        if scenario_set.scenario_generator_id != generator.scenario_generator_id:
            raise ValueError("ScenarioSet generator identity does not match registered generator")
        if scenario_set.rng_algorithm != generator.rng_algorithm:
            raise ValueError("ScenarioSet RNG identity does not match registered generator")
        if production and not forecast.production_eligible:
            raise ValueError("production scenario evidence requires a production-eligible Forecast")

        horizon_span = max(scenario_set.gameweeks) - min(scenario_set.gameweeks) + 1
        generator.require_valid_for(
            season=self.season,
            forecast_cutoff=forecast.feature_cutoff,
            horizon_gameweeks=horizon_span,
            production=production,
        )
        policy.require_available_for(
            season=self.season,
            cutoff=forecast.feature_cutoff,
            production=production,
        )
        self.verify_generator_artifacts(
            generator,
            store=store,
            production=production,
            as_of=forecast.feature_cutoff,
        )
        self.verify_policy_artifacts(
            policy,
            store=store,
            production=production,
            as_of=forecast.feature_cutoff,
        )
        for artifact_id in scenario_set.source_artifact_ids:
            store.read_bytes(artifact_id)


def _objects(value: object, *, label: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _rv(value: object, *, label: str) -> RationalValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be rational object")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise ValueError(f"{label} numerator must be integer")
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise ValueError(f"{label} denominator must be integer")
    return RationalValue(numerator, denominator)


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def load_scenario_governance_registry(path: str | Path) -> ScenarioGovernanceRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or _int(payload.get("schema_version"), label="schema_version") != 1:
        raise ValueError("scenario governance registry requires schema_version 1")
    season = str(payload.get("season") or "").strip()
    if not season:
        raise ValueError("scenario governance registry requires season")
    generators = tuple(
        ScenarioGeneratorArtifact(
            generator_name=str(row.get("generator_name") or ""),
            generator_version=str(row.get("generator_version") or ""),
            generator_contract=str(row.get("generator_contract") or ""),
            rng_algorithm=str(row.get("rng_algorithm") or ""),
            parameter_artifact_ids=tuple(
                str(item) for item in (row.get("parameter_artifact_ids") or [])
            ),
            qualification_state=ScenarioQualificationState(
                str(row.get("qualification_state") or "")
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row["qualification_artifact_id"])
            ),
            valid_seasons=tuple(str(item) for item in (row.get("valid_seasons") or [])),
            trained_through=str(row.get("trained_through") or ""),
            first_available_at=str(row.get("first_available_at") or ""),
            max_horizon_gameweeks=_int(
                row.get("max_horizon_gameweeks"),
                label="max_horizon_gameweeks",
            ),
        )
        for row in _objects(payload.get("generators"), label="scenario generators")
    )
    policies = tuple(
        ScenarioConvergencePolicy(
            policy_name=str(row.get("policy_name") or ""),
            policy_version=str(row.get("policy_version") or ""),
            season=str(row.get("season") or ""),
            qualification_state=ScenarioQualificationState(
                str(row.get("qualification_state") or "")
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row["qualification_artifact_id"])
            ),
            first_available_at=str(row.get("first_available_at") or ""),
            checkpoint_counts=tuple(
                _int(item, label="checkpoint_count")
                for item in (row.get("checkpoint_counts") or [])
            ),
            max_scenarios=_int(row.get("max_scenarios"), label="max_scenarios"),
            cvar_alpha_bps=_int(row.get("cvar_alpha_bps"), label="cvar_alpha_bps"),
            lower_quantile_bps=_int(
                row.get("lower_quantile_bps"),
                label="lower_quantile_bps",
            ),
            mean_tolerance=_rv(row.get("mean_tolerance"), label="mean_tolerance"),
            cvar_tolerance=_rv(row.get("cvar_tolerance"), label="cvar_tolerance"),
            tail_tolerance=_rv(row.get("tail_tolerance"), label="tail_tolerance"),
            xp_absolute_tolerance=_rv(
                row.get("xp_absolute_tolerance"),
                label="xp_absolute_tolerance",
            ),
            sampling_sigma_multiplier=_rv(
                row.get("sampling_sigma_multiplier"),
                label="sampling_sigma_multiplier",
            ),
            max_ev_regret_tolerance=_rv(
                row.get("max_ev_regret_tolerance"),
                label="max_ev_regret_tolerance",
            ),
        )
        for row in _objects(payload.get("policies"), label="scenario policies")
    )
    generator_raw = payload.get("champion_generator_id")
    policy_raw = payload.get("champion_policy_id")
    return ScenarioGovernanceRegistry(
        season=season,
        generators=generators,
        policies=policies,
        champion_generator_id=(
            None if generator_raw is None else ScenarioGeneratorId(str(generator_raw))
        ),
        champion_policy_id=(None if policy_raw is None else ScenarioPolicyId(str(policy_raw))),
    )
