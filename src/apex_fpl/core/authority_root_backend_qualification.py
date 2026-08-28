"""Independent qualification contract for the production authority-root registry."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256


_REFERENCE_BACKEND_ID = "apex.reference.filesystem-authority-root-registry.v1"
_PRODUCTION_PREFIX = "apex.production.postgres-authority-root-registry.v1:"


@dataclass(frozen=True, slots=True)
class AuthorityRootRegistryQualification:
    backend_id: str
    probe_artifact_id: str
    durable_shared_registry: bool
    immutable_root_history: bool
    atomic_compare_and_swap: bool
    stale_writer_rejected: bool
    qualification_scope: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AuthorityRootRegistryQualification schema_version")
        backend_id = str(self.backend_id).strip()
        probe_id = str(self.probe_artifact_id).strip()
        scope = str(self.qualification_scope).strip()
        if not backend_id or not probe_id or not scope:
            raise ValueError("authority-root registry qualification identities/scope are required")
        algorithm, separator, digest = probe_id.partition(":")
        if algorithm != "sha256" or not separator or len(digest) != 64:
            raise ValueError("authority-root registry probe artifact must be sha256 identity")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("authority-root registry probe digest is invalid") from exc
        for field in (
            "durable_shared_registry",
            "immutable_root_history",
            "atomic_compare_and_swap",
            "stale_writer_rejected",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"authority-root registry {field} must be boolean")
        object.__setattr__(self, "backend_id", backend_id)
        object.__setattr__(self, "probe_artifact_id", probe_id)
        object.__setattr__(self, "qualification_scope", scope)

    @property
    def qualified(self) -> bool:
        return (
            self.backend_id != _REFERENCE_BACKEND_ID
            and self.backend_id.startswith(_PRODUCTION_PREFIX)
            and self.durable_shared_registry
            and self.immutable_root_history
            and self.atomic_compare_and_swap
            and self.stale_writer_rejected
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-authority-root-registry-qualification",
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "probe_artifact_id": self.probe_artifact_id,
            "durable_shared_registry": self.durable_shared_registry,
            "immutable_root_history": self.immutable_root_history,
            "atomic_compare_and_swap": self.atomic_compare_and_swap,
            "stale_writer_rejected": self.stale_writer_rejected,
            "qualification_scope": self.qualification_scope,
        }

    @property
    def qualification_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
