"""Versioned data-only contracts for isolated/untrusted model workers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkerKind(StrEnum):
    AIRSENAL = "AIRSENAL"
    REFERENCE_SOLVER = "REFERENCE_SOLVER"


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    kind: WorkerKind
    runtime_digest: str
    source_revision: str
    request_schema_version: int = 1
    response_schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.runtime_digest.strip():
            raise ValueError("worker runtime_digest is required")
        if not self.source_revision.strip():
            raise ValueError("worker source_revision is required")


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    kind: WorkerKind
    request_id: str
    input_artifact_ids: tuple[str, ...]
    schema_name: str = "apex-worker-request"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("worker request_id is required")
        if not self.input_artifact_ids:
            raise ValueError("worker request must consume immutable input artifacts")


@dataclass(frozen=True, slots=True)
class WorkerResponse:
    kind: WorkerKind
    request_id: str
    runtime: WorkerRuntime
    output_artifact_ids: tuple[str, ...]
    success: bool
    error_type: str | None = None
    schema_name: str = "apex-worker-response"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.kind is not self.runtime.kind:
            raise ValueError("worker response/runtime kind mismatch")
        if not self.request_id.strip():
            raise ValueError("worker response request_id is required")
        if self.success and not self.output_artifact_ids:
            raise ValueError("successful worker response requires output artifacts")
        if not self.success and not self.error_type:
            raise ValueError("failed worker response requires typed error_type")
