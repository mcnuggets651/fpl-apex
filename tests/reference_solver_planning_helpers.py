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
    PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE,
    PlanningReferenceSolverQualificationCase,
    PlanningReferenceSolverQualificationCorpus,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request

from reference_solver_planning_finance_case import store_finance_qualification_case


# The independent planning solver's dedicated exact-parity contract is certified at this
# budget in test_v2_reference_solver_planning.py. Authority qualification must exercise the
# same declared exact surface instead of silently imposing a lower, non-contractual cap.
PLANNING_REFERENCE_EXACT_SEARCH_NODES = 5_000


@dataclass(frozen=True, slots=True)
class SyntheticPlanningParityMaterial:
    planning_result_id: str
    certificate_artifact_id: str
    certificate_id: str
    authorization_artifact_id: str
    authorization_id: str
    qualification_artifact_id: str
    registry_artifact_id: str
    corpus_artifact_id: str | None = None
    worker_code_artifact_id: str | None = None

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


def synthetic_planning_parity_material(*, store, fixture) -> SyntheticPlanningParityMaterial:
    """Build mechanism-only replay-valid planning parity authority for tests.

    Qualification deliberately uses two focused retained cases instead of one combinatorial
    mega-case:

    * the exact publication fixture proves the FULL_OFFICIAL chip/action surface;
    * a focused GW6-7 case proves FT banking plus realised transfer finance.

    Coverage is derived from sealed requests/results and aggregated across the corpus. The
    qualification must pass both cases and every mandatory derived coverage tag before any
    publication certificate/authorization is created. Both cases use the same 5,000-node exact
    search budget already certified by the dedicated independent-planner parity contract. This is
    synthetic mechanism evidence only and never production qualification evidence.
    """

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
        max_search_nodes=PLANNING_REFERENCE_EXACT_SEARCH_NODES,
    )
    stored_request = store_planning_reference_solver_request(request, store=store)

    publication_case = PlanningReferenceSolverQualificationCase(
        request_artifact_id=stored_request.artifact_id,
        expected_planning_result_artifact_id=fixture.bundle.planning_result_artifact_id,
        candidate_universe_artifact_id=fixture.bundle.candidate_universe_artifact_id,
    )
    publication_case_artifact_id = store_planning_reference_solver_qualification_case(
        publication_case,
        store=store,
    )
    finance_case_artifact_id = store_finance_qualification_case(
        store=store,
        verified=verified,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        max_search_nodes=PLANNING_REFERENCE_EXACT_SEARCH_NODES,
    )
    corpus = PlanningReferenceSolverQualificationCorpus(
        season=fixture.bundle.season,
        max_horizon_gameweeks=policy.horizon_gameweeks,
        case_artifact_ids=tuple(
            sorted((publication_case_artifact_id, finance_case_artifact_id))
        ),
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
    if qualification.passed_case_count != 2:
        raise AssertionError("planning qualification must retain both publication and finance cases")
    missing_coverage = set(PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE) - set(
        qualification.coverage_tags
    )
    if missing_coverage:
        raise AssertionError(
            "planning qualification lost mandatory coverage: " + ",".join(sorted(missing_coverage))
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
    if (
        not run.search_complete
        or run.gap is None
        or run.gap.numerator != 0
        or run.solver_status.value != "OPTIMAL"
    ):
        raise AssertionError("publication planning reference certificate must be exact and zero-gap")
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

    return SyntheticPlanningParityMaterial(
        planning_result_id=str(verified.decision.planning_result_id),
        certificate_artifact_id=stored_certificate.artifact_id,
        certificate_id=str(certificate.certificate_id),
        authorization_artifact_id=authorization.artifact_id,
        authorization_id=authorization.authorization.authorization_id,
        qualification_artifact_id=qualification_artifact_id,
        registry_artifact_id=authorization.authorization.registry_artifact_id,
        corpus_artifact_id=corpus_artifact_id,
        worker_code_artifact_id=worker_code_artifact_id,
    )
