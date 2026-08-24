"""Admission registry for sealed scenario generators and convergence policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.decision import RationalValue
from apex_fpl.core.ids import ScenarioGeneratorId, ScenarioPolicyId
from apex_fpl.core.scenarios import (
    ScenarioConvergencePolicy,
    ScenarioGeneratorArtifact,
    ScenarioQualificationState,
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

    def verify_policy_artifacts(
        self,
        policy: ScenarioConvergencePolicy,
        *,
        store: ArtifactStore,
        production: bool,
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


def _objects(value: object, *, label: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _rv(value: object, *, label: str) -> RationalValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be rational object")
    return RationalValue(int(value["numerator"]), int(value["denominator"]))


def load_scenario_governance_registry(path: str | Path) -> ScenarioGovernanceRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or int(payload.get("schema_version", -1)) != 1:
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
            max_horizon_gameweeks=int(row.get("max_horizon_gameweeks") or 0),
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
            checkpoint_counts=tuple(int(item) for item in row.get("checkpoint_counts") or []),
            max_scenarios=int(row.get("max_scenarios") or 0),
            cvar_alpha_bps=int(row.get("cvar_alpha_bps") or 0),
            lower_quantile_bps=int(row.get("lower_quantile_bps") or 0),
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
