"""Admission registry for external reference-solver workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reference_solver_planning_qualification import (
    verify_planning_reference_solver_algorithmic_qualification,
)
from apex_fpl.control.reference_solver_qualification import (
    verify_reference_solver_algorithmic_qualification,
)
from apex_fpl.core.assurance import ReferenceSolverCertificate
from apex_fpl.core.ids import ReferenceSolverWorkerId
from apex_fpl.core.reference_solver_io import REFERENCE_SOLVER_CONTRACT
from apex_fpl.core.reference_solver_planning_assurance import PlanningReferenceSolverCertificate
from apex_fpl.core.reference_solver_planning_io import REFERENCE_SOLVER_PLANNING_CONTRACT
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)


ReferenceCertificate = ReferenceSolverCertificate | PlanningReferenceSolverCertificate


@dataclass(frozen=True, slots=True)
class ReferenceSolverRegistry:
    season: str
    workers: tuple[ReferenceSolverWorkerArtifact, ...]
    champion_worker_id: ReferenceSolverWorkerId | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver registry schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("reference solver registry requires season")
        workers = tuple(sorted(self.workers, key=lambda row: str(row.worker_id)))
        ids = [row.worker_id for row in workers]
        if len(ids) != len(set(ids)):
            raise ValueError("reference solver registry contains duplicate worker identities")
        if any(season not in row.valid_seasons for row in workers):
            raise ValueError("reference solver worker registry season mismatch")
        if self.champion_worker_id is not None:
            champion = next(
                (row for row in workers if row.worker_id == self.champion_worker_id),
                None,
            )
            if champion is None:
                raise ValueError("reference solver champion is not registered")
            if not champion.production_qualified:
                raise ValueError("reference solver champion must be production qualified")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "workers", workers)

    def get(self, worker_id: ReferenceSolverWorkerId) -> ReferenceSolverWorkerArtifact | None:
        return next((row for row in self.workers if row.worker_id == worker_id), None)

    def champion(self) -> ReferenceSolverWorkerArtifact | None:
        if self.champion_worker_id is None:
            return None
        return self.get(self.champion_worker_id)

    def match_certificate(
        self,
        certificate: ReferenceCertificate,
    ) -> ReferenceSolverWorkerArtifact | None:
        return next(
            (
                row
                for row in self.workers
                if row.worker_name == certificate.worker_name
                and row.worker_version == certificate.worker_version
                and row.code_artifact_id == certificate.worker_artifact_id
            ),
            None,
        )

    @staticmethod
    def _require_certificate_contract(
        worker: ReferenceSolverWorkerArtifact,
        certificate: ReferenceCertificate,
    ) -> None:
        if worker.solver_contract == REFERENCE_SOLVER_CONTRACT:
            if not isinstance(certificate, ReferenceSolverCertificate):
                raise ValueError("tactical reference worker requires tactical solver certificate")
            return
        if worker.solver_contract == REFERENCE_SOLVER_PLANNING_CONTRACT:
            if not isinstance(certificate, PlanningReferenceSolverCertificate):
                raise ValueError("planning reference worker requires planning solver certificate")
            if certificate.solver_contract != worker.solver_contract:
                raise ValueError("planning solver certificate contract does not match worker")
            return
        raise ValueError(f"unsupported registered reference solver contract: {worker.solver_contract}")

    @staticmethod
    def _verify_qualification(
        worker: ReferenceSolverWorkerArtifact,
        *,
        qualification_artifact_id: str,
        store: ArtifactStore,
        season: str,
        horizon_gameweeks: int,
    ) -> None:
        if worker.solver_contract == REFERENCE_SOLVER_CONTRACT:
            verify_reference_solver_algorithmic_qualification(
                worker,
                qualification_artifact_id=qualification_artifact_id,
                store=store,
                season=season,
                horizon_gameweeks=horizon_gameweeks,
            )
            return
        if worker.solver_contract == REFERENCE_SOLVER_PLANNING_CONTRACT:
            verify_planning_reference_solver_algorithmic_qualification(
                worker,
                qualification_artifact_id=qualification_artifact_id,
                store=store,
                season=season,
                horizon_gameweeks=horizon_gameweeks,
            )
            return
        raise ValueError(f"unsupported registered reference solver contract: {worker.solver_contract}")

    def verify_certificate_worker(
        self,
        certificate: ReferenceCertificate,
        *,
        store: ArtifactStore,
        season: str,
        cutoff: str,
        horizon_gameweeks: int,
        production: bool,
    ) -> ReferenceSolverWorkerArtifact:
        worker = self.match_certificate(certificate)
        if worker is None:
            raise ValueError("reference solver certificate worker is not registered under exact identity")
        self._require_certificate_contract(worker, certificate)
        if not store.verify(worker.code_artifact_id):
            raise ValueError("reference solver worker code artifact is missing/corrupt")
        qualification = worker.qualification_artifact_id
        if worker.qualification_state is ReferenceSolverWorkerQualification.QUALIFIED:
            if qualification is None:
                raise ValueError("qualified reference solver worker lacks qualification artifact")
            self._verify_qualification(
                worker,
                qualification_artifact_id=qualification,
                store=store,
                season=season,
                horizon_gameweeks=horizon_gameweeks,
            )
        elif qualification is not None and not store.verify(qualification):
            raise ValueError("reference solver worker qualification artifact is missing/corrupt")
        worker.require_available_for(
            season=season,
            cutoff=cutoff,
            horizon_gameweeks=horizon_gameweeks,
            production=production,
        )
        if production and self.champion_worker_id != worker.worker_id:
            raise ValueError("production reference solver worker is not registered champion")
        return worker


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _workers(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("reference solver workers must be an array of objects")
    return [dict(row) for row in value]


def load_reference_solver_registry(path: str | Path) -> ReferenceSolverRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("reference solver registry must be object")
    if _strict_int(payload.get("schema_version"), label="schema_version") != 1:
        raise ValueError("reference solver registry requires schema_version 1")
    season = str(payload.get("season") or "").strip()
    if not season:
        raise ValueError("reference solver registry requires season")
    workers = tuple(
        ReferenceSolverWorkerArtifact(
            worker_name=str(row.get("worker_name") or ""),
            worker_version=str(row.get("worker_version") or ""),
            solver_contract=str(row.get("solver_contract") or ""),
            code_artifact_id=str(row.get("code_artifact_id") or ""),
            qualification_state=ReferenceSolverWorkerQualification(
                str(row.get("qualification_state") or "")
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row.get("qualification_artifact_id"))
            ),
            valid_seasons=tuple(str(item) for item in (row.get("valid_seasons") or [])),
            first_available_at=str(row.get("first_available_at") or ""),
            max_horizon_gameweeks=_strict_int(
                row.get("max_horizon_gameweeks"),
                label="max_horizon_gameweeks",
            ),
        )
        for row in _workers(payload.get("workers"))
    )
    champion_raw = payload.get("champion_worker_id")
    return ReferenceSolverRegistry(
        season=season,
        workers=workers,
        champion_worker_id=(
            None
            if champion_raw is None
            else ReferenceSolverWorkerId(str(champion_raw))
        ),
    )
