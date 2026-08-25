from __future__ import annotations

from dataclasses import dataclass, replace

from apex_fpl.assurance.reference_solver_planning_exchange import (
    build_planning_reference_solver_certificate,
    build_planning_reference_solver_request,
    store_planning_reference_solver_certificate,
    store_planning_reference_solver_request,
    store_planning_reference_solver_run,
)
from apex_fpl.assurance.worker_authorization import create_reference_solver_authorization
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.control.reference_solver_planning_qualification import (
    derive_planning_reference_solver_algorithmic_qualification,
    store_planning_reference_solver_algorithmic_qualification,
    store_planning_reference_solver_qualification_case,
    store_planning_reference_solver_qualification_corpus,
)
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.core.reference_solver_planning_io import REFERENCE_SOLVER_PLANNING_CONTRACT
from apex_fpl.core.reference_solver_planning_qualification import (
    PlanningReferenceSolverQualificationCase,
    PlanningReferenceSolverQualificationCorpus,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request


@dataclass(frozen=True, slots=True)
class SyntheticPlanningParityMaterial:
    planning_result_id: str
    certificate_artifact_id: str
    certificate_id: str
    authorization_artifact_id: str
    authorization_id: str
    qualification_artifact_id: str
    registry_artifact_id: str

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return (
            self.planning_result_id,
            self.certificate_id,
            self.authorization_id,
        )

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return (
            self.certificate_artifact_id,
            self.authorization_artifact_id,
        )


@dataclass(frozen=True, slots=True)
class _CachedParityTemplate:
    material: SyntheticPlanningParityMaterial
    artifacts: tuple[tuple[str, bytes], ...]


# Test-only immutable cache. The cache never short-circuits production replay: it only avoids
# rebuilding the exact same synthetic qualification/authorization artifacts in every isolated
# test ArtifactStore. Content identities are checked again when bytes are reinserted.
_PARITY_TEMPLATE_CACHE: dict[str, _CachedParityTemplate] = {}


def _restore_cached_template(*, store, cached: _CachedParityTemplate) -> SyntheticPlanningParityMaterial:
    for artifact_id, raw in cached.artifacts:
        restored = store.put_bytes(raw)
        if restored.artifact_id != artifact_id:
            raise ValueError("cached synthetic planning parity artifact identity drifted")
    return cached.material


def synthetic_planning_parity_material(*, store, fixture) -> SyntheticPlanningParityMaterial:
    """Build mechanism-only replay-valid planning parity authority for tests.

    The first construction for a semantic production-planning bundle intentionally goes through
    the same sealed request, corpus replay, worker qualification, champion registry, solver
    certificate, and authorization machinery that production cutover verifies. Subsequent tests
    restore those exact immutable bytes into their isolated stores; production verification still
    independently replays the retained qualification and authorization on every cutover.

    This is synthetic test evidence only and never production qualification evidence.
    """

    cache_key = str(fixture.bundle.bundle_id)
    cached = _PARITY_TEMPLATE_CACHE.get(cache_key)
    if cached is not None:
        return _restore_cached_template(store=store, cached=cached)

    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
    policy = verified.decision_policy
    if policy.continuation_value_artifact_id is None:
        raise ValueError("synthetic planning policy lacks continuation support")
    if policy.chip_option_value_artifact_id is None:
        raise ValueError("synthetic planning policy lacks chip-option support")
    if policy.price_policy_artifact_id is None:
        raise ValueError("synthetic planning policy lacks price support")
    if policy.candidate_policy_artifact_id is None:
        raise ValueError("synthetic planning policy lacks candidate support")

    continuation = load_continuation_value_policy(
        policy.continuation_value_artifact_id,
        store=store,
    )
    chip_option = load_chip_option_value_policy(
        policy.chip_option_value_artifact_id,
        store=store,
    )
    price = load_price_policy(policy.price_policy_artifact_id, store=store)
    candidate = load_candidate_policy(policy.candidate_policy_artifact_id, store=store)

    request = build_planning_reference_solver_request(
        result=verified.decision,
        manager_state=verified.manager_state,
        forecast=verified.forecast,
        candidate_universe=verified.candidate_universe,
        ruleset=verified.ruleset,
        decision_policy=policy,
        continuation_policy=continuation,
        chip_option_policy=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        max_search_nodes=5_000,
    )
    stored_request = store_planning_reference_solver_request(request, store=store)

    case = PlanningReferenceSolverQualificationCase(
        request_artifact_id=stored_request.artifact_id,
        expected_planning_result_artifact_id=fixture.bundle.planning_result_artifact_id,
        candidate_universe_artifact_id=fixture.bundle.candidate_universe_artifact_id,
    )
    case_artifact_id = store_planning_reference_solver_qualification_case(case, store=store)
    corpus = PlanningReferenceSolverQualificationCorpus(
        season=fixture.bundle.season,
        max_horizon_gameweeks=policy.horizon_gameweeks,
        case_artifact_ids=(case_artifact_id,),
    )
    corpus_artifact_id = store_planning_reference_solver_qualification_corpus(
        corpus,
        store=store,
    )

    worker_code_artifact_id = store.put_bytes(
        b"synthetic planning reference worker v2"
    ).artifact_id
    shadow_worker = ReferenceSolverWorkerArtifact(
        worker_name="synthetic-planning-reference-worker",
        worker_version="2",
        solver_contract=REFERENCE_SOLVER_PLANNING_CONTRACT,
        code_artifact_id=worker_code_artifact_id,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=(fixture.bundle.season,),
        first_available_at="2026-08-01T00:00:00Z",
        max_horizon_gameweeks=policy.horizon_gameweeks,
    )
    qualification = derive_planning_reference_solver_algorithmic_qualification(
        shadow_worker,
        corpus_artifact_id=corpus_artifact_id,
        store=store,
    )
    qualification_artifact_id = store_planning_reference_solver_algorithmic_qualification(
        qualification,
        store=store,
    )
    qualified_worker = replace(
        shadow_worker,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification_artifact_id,
    )
    registry = ReferenceSolverRegistry(
        season=fixture.bundle.season,
        workers=(qualified_worker,),
        champion_worker_id=qualified_worker.worker_id,
    )

    run = solve_planning_reference_request(request)
    stored_run = store_planning_reference_solver_run(run, store=store)
    certificate = build_planning_reference_solver_certificate(
        request_artifact_id=stored_request.artifact_id,
        run_artifact_id=stored_run.artifact_id,
        worker_name=qualified_worker.worker_name,
        worker_version=qualified_worker.worker_version,
        worker_code_artifact_id=qualified_worker.code_artifact_id,
        store=store,
    )
    stored_certificate = store_planning_reference_solver_certificate(certificate, store=store)
    authorization = create_reference_solver_authorization(
        certificate,
        worker_registry=registry,
        registry_artifact_id=None,
        store=store,
        season=fixture.bundle.season,
        decision_cutoff=verified.forecast.feature_cutoff,
        horizon_gameweeks=policy.horizon_gameweeks,
    )

    material = SyntheticPlanningParityMaterial(
        planning_result_id=str(verified.decision.planning_result_id),
        certificate_artifact_id=stored_certificate.artifact_id,
        certificate_id=str(certificate.certificate_id),
        authorization_artifact_id=authorization.artifact_id,
        authorization_id=authorization.authorization.authorization_id,
        qualification_artifact_id=qualification_artifact_id,
        registry_artifact_id=authorization.authorization.registry_artifact_id,
    )
    parity_artifact_ids = (
        stored_request.artifact_id,
        case_artifact_id,
        corpus_artifact_id,
        worker_code_artifact_id,
        qualification_artifact_id,
        authorization.authorization.registry_artifact_id,
        stored_run.artifact_id,
        stored_certificate.artifact_id,
        authorization.artifact_id,
    )
    cached_artifacts = tuple(
        (artifact_id, store.read_bytes(artifact_id)) for artifact_id in parity_artifact_ids
    )
    _PARITY_TEMPLATE_CACHE[cache_key] = _CachedParityTemplate(
        material=material,
        artifacts=cached_artifacts,
    )
    return material
