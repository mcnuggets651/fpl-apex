"""Immutable build/runtime provenance contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re

from apex_fpl.core.canonical import canonical_sha256


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _require_digest(label: str, value: str) -> str:
    text = str(value).strip().lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return text


@dataclass(frozen=True, slots=True)
class BuildManifest:
    source_sha: str
    dependency_lock_digest: str
    runtime_digest: str
    base_image_digest: str
    builder_identity: str
    built_at: str
    sbom_artifact_id: str
    provenance_artifact_id: str
    action_pins: tuple[tuple[str, str], ...] = ()
    schema_name: str = "apex-build-manifest"
    schema_version: int = 1

    def __post_init__(self) -> None:
        source_sha = self.source_sha.strip().lower()
        if not _GIT_SHA.fullmatch(source_sha):
            raise ValueError("source_sha must be a full 40-character Git SHA")
        object.__setattr__(self, "source_sha", source_sha)
        for label in (
            "dependency_lock_digest",
            "runtime_digest",
            "base_image_digest",
            "sbom_artifact_id",
            "provenance_artifact_id",
        ):
            object.__setattr__(self, label, _require_digest(label, getattr(self, label)))
        if not self.builder_identity.strip():
            raise ValueError("builder_identity is required")
        if not self.built_at.strip():
            raise ValueError("built_at must be supplied by the control plane")
        if len(dict(self.action_pins)) != len(self.action_pins):
            raise ValueError("action_pins contains duplicate action names")
        for action, sha in self.action_pins:
            if not action.strip() or not _GIT_SHA.fullmatch(sha.strip().lower()):
                raise ValueError(f"invalid action pin: {action!r}={sha!r}")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "source_sha": self.source_sha,
            "dependency_lock_digest": self.dependency_lock_digest,
            "runtime_digest": self.runtime_digest,
            "base_image_digest": self.base_image_digest,
            "builder_identity": self.builder_identity,
            "built_at": self.built_at,
            "sbom_artifact_id": self.sbom_artifact_id,
            "provenance_artifact_id": self.provenance_artifact_id,
            "action_pins": [[action, sha] for action, sha in sorted(self.action_pins)],
        }

    @property
    def build_manifest_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
