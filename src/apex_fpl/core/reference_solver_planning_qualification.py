"""Dependency-free algorithmic qualification contracts for planning reference workers."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .experiments import qualification_subject_id
from .reference_solver_planning_io import REFERENCE_SOLVER_PLANNING_CONTRACT


PLANNING_QUALIFICATION_REPLAY_ALGORITHM_ID = "reference-solver-planning-qualification-v2"
PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE = (
    "BENCH_BOOST_SURFACE",
    "FREE_HIT_REVERSAL_SURFACE",
    "FT_BANKING_SURFACE",
    "FULL_OFFICIAL_ACTION_SURFACE",
    "MULTI_GAMEWEEK_OBJECTIVE",
    "ROOT_ACTION_PARITY",
    "SUPPORT_POLICY_BINDING",
    "TERMINAL_CHIP_RESERVE",
    "TRAJECTORY_PARITY",
    "TRANSFER_FINANCE_SURFACE",
    "TRIPLE_CAPTAIN_SURFACE",
    "WILDCARD_PERSISTENCE_SURFACE",
    "ZERO_GAP_COMPLETENESS",
)


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
class PlanningReferenceSolverQualificationCase:
    request_artifact_id: str
    expected_planning_result_artifact_id: str
    candidate_universe_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference qualification case schema")
        for field, label in (
            ("request_artifact_id", "planning qualification request"),
            ("expected_planning_result_artifact_id", "planning qualification result"),
            ("candidate_universe_artifact_id", "planning qualification universe"),
        ):
            object.__setattr__(self, field, _artifact_id(getattr(self, field), label=label))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-reference-solver-qualification-case",
            "schema_version": self.schema_version,
            "request_artifact_id": self.request_artifact_id,
            "expected_planning_result_artifact_id": self.expected_planning_result_artifact_id,
            "candidate_universe_artifact_id": self.candidate_universe_artifact_id,
        }

    @property
    def case_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class PlanningReferenceSolverQualificationCorpus:
    season: str
    max_horizon_gameweeks: int
    case_artifact_ids: tuple[str, ...]
    solver_contract: str = REFERENCE_SOLVER_PLANNING_CONTRACT
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference qualification corpus schema")
        season = _nonempty(self.season, label="planning qualification season")
        if self.solver_contract != REFERENCE_SOLVER_PLANNING_CONTRACT:
            raise ValueError("planning qualification corpus uses unsupported solver contract")
        if (
            isinstance(self.max_horizon_gameweeks, bool)
            or not isinstance(self.max_horizon_gameweeks, int)
            or self.max_horizon_gameweeks < 2
        ):
            raise ValueError("planning qualification max horizon must be integer >= 2")
        cases = tuple(
            sorted(
                {
                    _artifact_id(item, label="planning qualification case artifact")
                    for item in self.case_artifact_ids
                }
            )
        )
        if not cases:
            raise ValueError("planning qualification corpus requires at least one case")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "case_artifact_ids", cases)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-reference-solver-qualification-corpus",
            "schema_version": self.schema_version,
            "season": self.season,
            "max_horizon_gameweeks": self.max_horizon_gameweeks,
            "solver_contract": self.solver_contract,
            "case_artifact_ids": list(self.case_artifact_ids),
        }

    @property
    def corpus_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class PlanningReferenceSolverAlgorithmicQualificationCertificate:
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
    coverage_tags: tuple[str, ...]
    replay_algorithm_id: str = PLANNING_QUALIFICATION_REPLAY_ALGORITHM_ID
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference qualification certificate schema")
        object.__setattr__(
            self,
            "worker_subject_id",
            _artifact_id(self.worker_subject_id, label="planning worker subject"),
        )
        object.__setattr__(
            self,
            "worker_code_artifact_id",
            _artifact_id(self.worker_code_artifact_id, label="planning worker code artifact"),
        )
        object.__setattr__(
            self,
            "corpus_artifact_id",
            _artifact_id(self.corpus_artifact_id, label="planning corpus artifact"),
        )
        object.__setattr__(
            self,
            "corpus_id",
            _artifact_id(self.corpus_id, label="planning corpus identity"),
        )
        for field in ("worker_name", "worker_version", "season", "replay_algorithm_id"):
            object.__setattr__(self, field, _nonempty(getattr(self, field), label=field))
        if self.solver_contract != REFERENCE_SOLVER_PLANNING_CONTRACT:
            raise ValueError("planning qualification certificate uses unsupported solver contract")
        if (
            isinstance(self.max_horizon_gameweeks, bool)
            or not isinstance(self.max_horizon_gameweeks, int)
            or self.max_horizon_gameweeks < 2
        ):
            raise ValueError("planning qualification max horizon must be integer >= 2")
        if (
            isinstance(self.passed_case_count, bool)
            or not isinstance(self.passed_case_count, int)
            or self.passed_case_count <= 0
        ):
            raise ValueError("planning qualification requires positive passed case count")
        coverage = tuple(sorted({_nonempty(item, label="planning coverage tag") for item in self.coverage_tags}))
        required = set(PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE)
        actual = set(coverage)
        if actual != required:
            raise ValueError(
                "planning qualification lacks mandatory derived coverage "
                f"missing={sorted(required - actual)} extra={sorted(actual - required)}"
            )
        if self.replay_algorithm_id != PLANNING_QUALIFICATION_REPLAY_ALGORITHM_ID:
            raise ValueError("unsupported planning qualification replay algorithm")
        object.__setattr__(self, "coverage_tags", coverage)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-reference-solver-algorithmic-qualification-certificate",
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
            "coverage_tags": list(self.coverage_tags),
            "replay_algorithm_id": self.replay_algorithm_id,
        }

    @property
    def certificate_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


def planning_reference_worker_subject_id(worker_payload: dict[str, object]) -> str:
    return qualification_subject_id(worker_payload)
