"""Capability-specific source admission and degradation registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.sources import (
    DegradationProfile,
    SourceAdmissionState,
    SourceCapability,
    SourceCriticality,
)


def _artifact_id(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class RegisteredSourceCapability:
    capability: SourceCapability
    qualification_artifact_id: str | None = None

    def __post_init__(self) -> None:
        artifact = self.qualification_artifact_id
        if self.capability.admission_state is SourceAdmissionState.QUALIFIED:
            if artifact is None:
                raise ValueError("qualified source capability requires qualification artifact")
            artifact = _artifact_id(artifact, label="source qualification artifact")
        elif artifact is not None:
            artifact = _artifact_id(artifact, label="source qualification artifact")
        object.__setattr__(self, "qualification_artifact_id", artifact)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "capability": self.capability.semantic_payload(),
            "qualification_artifact_id": self.qualification_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    entries: tuple[RegisteredSourceCapability, ...]
    degradation_profiles: tuple[DegradationProfile, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported source registry schema_version")
        keys: set[tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.capability.source_id, entry.capability.capability)
            if key in keys:
                raise ValueError(f"duplicate source capability registration: {key}")
            keys.add(key)
        profile_ids: set[str] = set()
        for profile in self.degradation_profiles:
            if profile.profile_id in profile_ids:
                raise ValueError(f"duplicate degradation profile: {profile.profile_id}")
            profile_ids.add(profile.profile_id)

    @property
    def registry_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-source-registry",
                "schema_version": self.schema_version,
                "entries": [
                    row.semantic_payload()
                    for row in sorted(
                        self.entries,
                        key=lambda item: (
                            item.capability.source_id,
                            item.capability.capability,
                        ),
                    )
                ],
                "degradation_profiles": [
                    {
                        "profile_id": row.profile_id,
                        "capability": row.capability,
                        "qualified": row.qualified,
                        "registered": row.registered,
                        "validation_artifact_id": row.validation_artifact_id,
                    }
                    for row in sorted(self.degradation_profiles, key=lambda item: item.profile_id)
                ],
            }
        )

    def get(self, source_id: str, capability: str) -> RegisteredSourceCapability | None:
        for row in self.entries:
            if row.capability.source_id == source_id and row.capability.capability == capability:
                return row
        return None

    def degradation_for(self, capability: str) -> DegradationProfile | None:
        usable = [
            row
            for row in self.degradation_profiles
            if row.capability == capability and row.usable
        ]
        if len(usable) > 1:
            raise ValueError(f"multiple usable degradation profiles for capability {capability}")
        return usable[0] if usable else None

    def verify_artifacts(self, store: ArtifactStore) -> None:
        for row in self.entries:
            artifact = row.qualification_artifact_id
            if artifact is not None and not store.verify(artifact):
                raise ValueError(
                    f"source qualification artifact is missing/corrupt for "
                    f"{row.capability.source_id}:{row.capability.capability}"
                )
        for profile in self.degradation_profiles:
            if not store.verify(profile.validation_artifact_id):
                raise ValueError(
                    f"degradation profile artifact is missing/corrupt: {profile.profile_id}"
                )


def _rows(value: object, *, label: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def load_source_registry(path: str | Path) -> SourceRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("source registry requires schema_version 1")
    entries: list[RegisteredSourceCapability] = []
    for row in _rows(raw.get("sources"), label="sources"):
        capability = SourceCapability(
            source_id=str(row.get("source_id") or ""),
            capability=str(row.get("capability") or ""),
            criticality=SourceCriticality(str(row.get("criticality") or "")),
            admission_state=SourceAdmissionState(str(row.get("admission_state") or "")),
            adapter_schema=str(row.get("adapter_schema") or ""),
            adapter_version=str(row.get("adapter_version") or ""),
            retention_understood=bool(row.get("retention_understood", False)),
            licensing_understood=bool(row.get("licensing_understood", False)),
            failure_semantics=str(row.get("failure_semantics") or ""),
            reliability_rationale=str(row.get("reliability_rationale") or ""),
        )
        entries.append(
            RegisteredSourceCapability(
                capability=capability,
                qualification_artifact_id=(
                    None
                    if row.get("qualification_artifact_id") is None
                    else str(row["qualification_artifact_id"])
                ),
            )
        )
    profiles = tuple(
        DegradationProfile(
            profile_id=str(row.get("profile_id") or ""),
            capability=str(row.get("capability") or ""),
            qualified=bool(row.get("qualified", False)),
            registered=bool(row.get("registered", False)),
            validation_artifact_id=str(row.get("validation_artifact_id") or ""),
        )
        for row in _rows(raw.get("degradation_profiles"), label="degradation_profiles")
    )
    return SourceRegistry(tuple(entries), profiles)
