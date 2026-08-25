"""Dependency-free algorithmic qualification contracts for V2 reference-solver workers."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .experiments import qualification_subject_id
from .reference_solver_io import ExactSolverValue, REFERENCE_SOLVER_CONTRACT


QUALIFICATION_REPLAY_ALGORITHM_ID = "reference-solver-algorithmic-qualification-v1"


def _artifact_id(value: str, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _nonempty(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


@dataclass(frozen=True, slots=True)
class ReferenceSolverQualificationCase:
    request_artifact_id: str
    expected_decision_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver qualification case schema")
        object.__setattr__(
            self,
            "request_artifact_id",
            _artifact_id(self.request_artifact_id, label="qualification request artifact"),
        )
        object.__setattr__(
            self,
            "expected_decision_artifact_id",
            _artifact_id(
                self.expected_decision_artifact_id,
                label="qualification expected decision artifact",
            ),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-qualification-case",
            "schema_version": self.schema_version,
            "request_artifact_id": self.request_artifact_id,
            "expected_decision_artifact_id": self.expected_decision_artifact_id,
        }

    @property
    def case_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ReferenceSolverQualificationCorpus:
    season: str
    horizon_gameweeks: int
    solver_contract: str
    case_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver qualification corpus schema")
        season = _nonempty(self.season, label="qualification corpus season")
        contract = _nonempty(self.solver_contract, label="qualification corpus solver_contract")
        if contract != REFERENCE_SOLVER_CONTRACT:
            raise ValueError("qualification corpus uses unsupported solver contract")
        if (
            isinstance(self.horizon_gameweeks, bool)
            or not isinstance(self.horizon_gameweeks, int)
            or self.horizon_gameweeks <= 0
        ):
            raise ValueError("qualification corpus horizon must be positive integer")
        cases = tuple(
            sorted(
                {
                    _artifact_id(item, label="qualification case artifact")
                    for item in self.case_artifact_ids
                }
            )
        )
        if not cases:
            raise ValueError("qualification corpus requires at least one case")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "solver_contract", contract)
        object.__setattr__(self, "case_artifact_ids", cases)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-qualification-corpus",
            "schema_version": self.schema_version,
            "season": self.season,
            "horizon_gameweeks": self.horizon_gameweeks,
            "solver_contract": self.solver_contract,
            "case_artifact_ids": list(self.case_artifact_ids),
        }

    @property
    def corpus_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ReferenceSolverAlgorithmicQualificationCertificate:
    worker_subject_id: str
    worker_name: str
    worker_version: str
    worker_code_artifact_id: str
    solver_contract: str
    season: str
    max_horizon_gameweeks: int
    corpus_artifact_id: str
    corpus_id: str
    passed_case_count: int
    replay_algorithm_id: str = QUALIFICATION_REPLAY_ALGORITHM_ID
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver qualification certificate schema")
        subject = _artifact_id(self.worker_subject_id, label="worker qualification subject")
        code = _artifact_id(self.worker_code_artifact_id, label="worker code artifact")
        corpus_artifact = _artifact_id(
            self.corpus_artifact_id,
            label="qualification corpus artifact",
        )
        corpus_id = _artifact_id(self.corpus_id, label="qualification corpus identity")
        for label in ("worker_name", "worker_version", "season", "replay_algorithm_id"):
            object.__setattr__(self, label, _nonempty(getattr(self, label), label=label))
        if self.solver_contract != REFERENCE_SOLVER_CONTRACT:
            raise ValueError("qualification certificate uses unsupported solver contract")
        if (
            isinstance(self.max_horizon_gameweeks, bool)
            or not isinstance(self.max_horizon_gameweeks, int)
            or self.max_horizon_gameweeks <= 0
        ):
            raise ValueError("qualification certificate max horizon must be positive integer")
        if (
            isinstance(self.passed_case_count, bool)
            or not isinstance(self.passed_case_count, int)
            or self.passed_case_count <= 0
        ):
            raise ValueError("qualification certificate requires positive passed case count")
        if self.replay_algorithm_id != QUALIFICATION_REPLAY_ALGORITHM_ID:
            raise ValueError("unsupported reference solver qualification replay algorithm")
        object.__setattr__(self, "worker_subject_id", subject)
        object.__setattr__(self, "worker_code_artifact_id", code)
        object.__setattr__(self, "corpus_artifact_id", corpus_artifact)
        object.__setattr__(self, "corpus_id", corpus_id)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-algorithmic-qualification-certificate",
            "schema_version": self.schema_version,
            "worker_subject_id": self.worker_subject_id,
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "worker_code_artifact_id": self.worker_code_artifact_id,
            "solver_contract": self.solver_contract,
            "season": self.season,
            "max_horizon_gameweeks": self.max_horizon_gameweeks,
            "corpus_artifact_id": self.corpus_artifact_id,
            "corpus_id": self.corpus_id,
            "passed_case_count": self.passed_case_count,
            "replay_algorithm_id": self.replay_algorithm_id,
        }

    @property
    def certificate_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


def reference_solver_worker_subject_id(worker_payload: dict[str, object]) -> str:
    """Return stable prequalification identity, excluding only qualification state/artifact."""

    return qualification_subject_id(worker_payload)
