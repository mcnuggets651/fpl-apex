"""Qualified deadline-relative freshness policies for governed source capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.freshness import DeadlineFreshnessPolicy, FreshnessBand
from apex_fpl.core.sources import HealthState, SourceCriticality


@dataclass(frozen=True, slots=True)
class RegisteredFreshnessPolicy:
    criticality: SourceCriticality
    policy: DeadlineFreshnessPolicy


@dataclass(frozen=True, slots=True)
class FreshnessRegistry:
    policies: tuple[RegisteredFreshnessPolicy, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported freshness registry schema_version")
        keys: set[tuple[str, SourceCriticality]] = set()
        for row in self.policies:
            key = (row.policy.capability, row.criticality)
            if key in keys:
                raise ValueError(f"duplicate freshness policy for {key}")
            keys.add(key)

    def get(
        self,
        *,
        capability: str,
        criticality: SourceCriticality,
    ) -> DeadlineFreshnessPolicy | None:
        for row in self.policies:
            if row.policy.capability == capability and row.criticality is criticality:
                return row.policy
        return None

    def assess(
        self,
        *,
        capability: str,
        criticality: SourceCriticality,
        source_age_seconds: int,
        seconds_to_deadline: int,
        store: ArtifactStore,
    ) -> HealthState:
        policy = self.get(capability=capability, criticality=criticality)
        if policy is None or policy.qualification_artifact_id is None:
            return HealthState.UNKNOWN
        if not store.verify(policy.qualification_artifact_id):
            return HealthState.UNKNOWN
        return (
            HealthState.PASS
            if policy.is_fresh(
                source_age_seconds=source_age_seconds,
                seconds_to_deadline=seconds_to_deadline,
            )
            else HealthState.FAIL
        )


def load_freshness_registry(path: str | Path) -> FreshnessRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("freshness registry requires schema_version 1")
    rows = raw.get("policies", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("freshness policies must be an array of objects")
    registered: list[RegisteredFreshnessPolicy] = []
    for row in rows:
        bands_raw = row.get("bands")
        if not isinstance(bands_raw, list) or any(not isinstance(item, dict) for item in bands_raw):
            raise ValueError("freshness policy bands must be an array of objects")
        policy = DeadlineFreshnessPolicy(
            policy_id=str(row.get("policy_id") or ""),
            capability=str(row.get("capability") or ""),
            bands=tuple(
                FreshnessBand(
                    max_seconds_to_deadline=(
                        None
                        if item.get("max_seconds_to_deadline") is None
                        else int(item["max_seconds_to_deadline"])
                    ),
                    max_source_age_seconds=int(item.get("max_source_age_seconds", -1)),
                    rationale=str(item.get("rationale") or ""),
                )
                for item in bands_raw
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row["qualification_artifact_id"])
            ),
        )
        registered.append(
            RegisteredFreshnessPolicy(
                criticality=SourceCriticality(str(row.get("criticality") or "")),
                policy=policy,
            )
        )
    return FreshnessRegistry(tuple(registered))
