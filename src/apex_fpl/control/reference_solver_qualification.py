"""Immutable replay-derived algorithmic qualification for isolated V2 reference solvers."""

from __future__ import annotations

from dataclasses import replace
import json

from apex_fpl.assurance.reference_solver_exchange import load_reference_solver_request
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.reference_solver_io import ReferenceSolverRunStatus
from apex_fpl.core.reference_solver_qualification import (
    REFERENCE_SOLVER_REQUIRED_COVERAGE,
    ReferenceSolverAlgorithmicQualificationCertificate,
    ReferenceSolverQualificationCase,
    ReferenceSolverQualificationCorpus,
    reference_solver_worker_subject_id,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.decision.store import load_decision_result
from apex_fpl.workers.reference_solver import solve_reference_request


def _object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be object")
    if canonical_json_bytes(payload) != raw:
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def store_reference_solver_qualification_case(
    case: ReferenceSolverQualificationCase,
    *,
    store: ArtifactStore,
) -> str:
    store.read_bytes(case.request_artifact_id)
    store.read_bytes(case.expected_decision_artifact_id)
    return store.put_bytes(
        canonical_json_bytes(case.semantic_payload()),
        media_type="application/json",
        schema_name="apex-reference-solver-qualification-case",
        schema_version="1",
    ).artifact_id


def load_reference_solver_qualification_case(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReferenceSolverQualificationCase:
    payload = _object(store.read_bytes(artifact_id), label="reference solver qualification case")
    if payload.get("schema_name") != "apex-reference-solver-qualification-case":
        raise ValueError("not a reference solver qualification case")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported reference solver qualification case schema")
    case = ReferenceSolverQualificationCase(
        request_artifact_id=str(payload.get("request_artifact_id") or ""),
        expected_decision_artifact_id=str(
            payload.get("expected_decision_artifact_id") or ""
        ),
    )
    if case.case_id != artifact_id:
        raise ValueError("reference solver qualification case semantic identity mismatch")
    store.read_bytes(case.request_artifact_id)
    store.read_bytes(case.expected_decision_artifact_id)
    return case


def store_reference_solver_qualification_corpus(
    corpus: ReferenceSolverQualificationCorpus,
    *,
    store: ArtifactStore,
) -> str:
    for artifact_id in corpus.case_artifact_ids:
        load_reference_solver_qualification_case(artifact_id, store=store)
    return store.put_bytes(
        canonical_json_bytes(corpus.semantic_payload()),
        media_type="application/json",
        schema_name="apex-reference-solver-qualification-corpus",
        schema_version="1",
    ).artifact_id


def load_reference_solver_qualification_corpus(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReferenceSolverQualificationCorpus:
    payload = _object(store.read_bytes(artifact_id), label="reference solver qualification corpus")
    if payload.get("schema_name") != "apex-reference-solver-qualification-corpus":
        raise ValueError("not a reference solver qualification corpus")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported reference solver qualification corpus schema")
    case_ids = payload.get("case_artifact_ids")
    if not isinstance(case_ids, list) or any(not isinstance(item, str) for item in case_ids):
        raise ValueError("qualification corpus case_artifact_ids must be strings")
    corpus = ReferenceSolverQualificationCorpus(
        season=str(payload.get("season") or ""),
        horizon_gameweeks=payload.get("horizon_gameweeks"),  # type: ignore[arg-type]
        solver_contract=str(payload.get("solver_contract") or ""),
        case_artifact_ids=tuple(case_ids),
    )
    if corpus.corpus_id != artifact_id:
        raise ValueError("reference solver qualification corpus semantic identity mismatch")
    for case_id in corpus.case_artifact_ids:
        load_reference_solver_qualification_case(case_id, store=store)
    return corpus


def _shadow_subject(worker: ReferenceSolverWorkerArtifact) -> ReferenceSolverWorkerArtifact:
    """Normalize only qualification fields before computing stable subject identity."""

    return replace(
        worker,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
    )


def _rows(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _derived_case_coverage(request, expected) -> set[str]:
    """Derive exercised solver semantics from retained request/result bytes only."""

    coverage: set[str] = set()
    selected = expected.selected_action
    selected_xi = {int(player_id) for player_id in selected.xi_ids}

    forecast_rows = _rows(request.forecast.get("rows"), label="qualification forecast rows")
    selected_fixture_counts: dict[tuple[int, int], int] = {}
    for row in forecast_rows:
        target = row.get("target")
        distribution = row.get("minutes_distribution")
        if not isinstance(target, dict) or not isinstance(distribution, list):
            raise ValueError("qualification forecast row is structurally invalid")
        player_id = target.get("player_id")
        gameweek = target.get("gameweek")
        if isinstance(player_id, bool) or not isinstance(player_id, int):
            raise ValueError("qualification forecast player_id must be integer")
        if isinstance(gameweek, bool) or not isinstance(gameweek, int):
            raise ValueError("qualification forecast gameweek must be integer")
        if player_id not in selected_xi:
            continue
        key = (gameweek, player_id)
        selected_fixture_counts[key] = selected_fixture_counts.get(key, 0) + 1
        for support in distribution:
            if (
                isinstance(support, list)
                and len(support) == 2
                and support[0] == 0
                and isinstance(support[1], int)
                and not isinstance(support[1], bool)
                and support[1] > 0
            ):
                coverage.add("PROBABILISTIC_AUTOSUB")
                break
    if any(count > 1 for count in selected_fixture_counts.values()):
        coverage.add("DOUBLE_GAMEWEEK")

    if selected.transfers:
        coverage.add("TRANSFER_FINANCE")
        outgoing_ids = {int(move.outgoing_player_id) for move in selected.transfers}
        squad_rows = _rows(request.manager_state.get("squad"), label="qualification manager squad")
        for row in squad_rows:
            player_id = row.get("player_id")
            if player_id not in outgoing_ids:
                continue
            purchase = row.get("purchase_basis_tenths")
            current = row.get("current_price_tenths")
            selling = row.get("selling_price_tenths")
            if (
                isinstance(purchase, int)
                and not isinstance(purchase, bool)
                and isinstance(current, int)
                and not isinstance(current, bool)
                and isinstance(selling, int)
                and not isinstance(selling, bool)
                and purchase != current
                and selling != current
            ):
                coverage.add("SELLING_PRICE_RESOURCE")
                break
    if selected.mechanics.hit_points > 0:
        coverage.add("PAID_HIT")

    chips = request.decision_input.get("chips_considered")
    if not isinstance(chips, list) or any(not isinstance(item, str) for item in chips):
        raise ValueError("qualification DecisionInput chips_considered must be strings")
    chip_tags = {
        "TRIPLE_CAPTAIN": "TRIPLE_CAPTAIN_SURFACE",
        "BENCH_BOOST": "BENCH_BOOST_SURFACE",
        "WILDCARD": "WILDCARD_SURFACE",
        "FREE_HIT": "FREE_HIT_SURFACE",
    }
    for chip, tag in chip_tags.items():
        if chip in chips:
            coverage.add(tag)

    selected_objective = selected.mechanics.objective_points
    if any(
        alternative.action_id != selected.action_id
        and alternative.mechanics.objective_points == selected_objective
        for alternative in expected.alternatives
    ):
        coverage.add("TIE_BREAK_PARITY")
    return coverage


def derive_reference_solver_algorithmic_qualification(
    worker: ReferenceSolverWorkerArtifact,
    *,
    corpus_artifact_id: str,
    store: ArtifactStore,
) -> ReferenceSolverAlgorithmicQualificationCertificate:
    """Replay every sealed corpus case and require exact parity plus mandatory coverage."""

    if not store.verify(worker.code_artifact_id):
        raise ValueError("reference solver worker code artifact is missing/corrupt")
    corpus = load_reference_solver_qualification_corpus(corpus_artifact_id, store=store)
    if worker.solver_contract != corpus.solver_contract:
        raise ValueError("reference solver worker/corpus solver contract mismatch")
    if corpus.season not in worker.valid_seasons:
        raise ValueError("reference solver qualification corpus season outside worker scope")
    if corpus.horizon_gameweeks > worker.max_horizon_gameweeks:
        raise ValueError("reference solver qualification corpus horizon outside worker scope")

    passed = 0
    coverage: set[str] = set()
    for case_artifact_id in corpus.case_artifact_ids:
        case = load_reference_solver_qualification_case(case_artifact_id, store=store)
        request = load_reference_solver_request(case.request_artifact_id, store=store).request
        expected = load_decision_result(
            case.expected_decision_artifact_id,
            store=store,
        ).result
        if request.decision_input_id != str(expected.decision_input.decision_input_id):
            raise ValueError("qualification request/expected DecisionInput identity mismatch")
        if request.candidate_universe_id != str(expected.decision_input.candidate_universe_id):
            raise ValueError("qualification request/expected CandidateUniverse identity mismatch")
        if request.decision_policy_id != str(expected.decision_input.decision_policy_id):
            raise ValueError("qualification request/expected DecisionPolicy identity mismatch")
        policy_horizon = request.decision_policy.get("horizon_gameweeks")
        if policy_horizon != corpus.horizon_gameweeks:
            raise ValueError("qualification request horizon does not match corpus scope")
        run = solve_reference_request(request)
        if run.solver_status is not ReferenceSolverRunStatus.OPTIMAL:
            raise ValueError(
                "reference solver qualification case did not terminate OPTIMAL: "
                f"{run.solver_status.value}"
            )
        expected_objective = expected.selected_action.mechanics.objective_points
        if run.best_objective is None or (
            run.best_objective.numerator != expected_objective.numerator
            or run.best_objective.denominator != expected_objective.denominator
        ):
            raise ValueError("reference solver qualification objective parity failed")
        if run.selected_action_id != expected.selected_action.action_id:
            raise ValueError("reference solver qualification action parity failed")
        coverage.update(_derived_case_coverage(request, expected))
        passed += 1

    required = set(REFERENCE_SOLVER_REQUIRED_COVERAGE)
    missing = sorted(required - coverage)
    if missing:
        raise ValueError(
            "reference solver qualification corpus lacks mandatory derived coverage: "
            + ",".join(missing)
        )

    subject = _shadow_subject(worker)
    return ReferenceSolverAlgorithmicQualificationCertificate(
        worker_subject_id=reference_solver_worker_subject_id(subject.semantic_payload()),
        worker_name=worker.worker_name,
        worker_version=worker.worker_version,
        worker_code_artifact_id=worker.code_artifact_id,
        solver_contract=worker.solver_contract,
        season=corpus.season,
        max_horizon_gameweeks=corpus.horizon_gameweeks,
        corpus_artifact_id=corpus_artifact_id,
        corpus_id=corpus.corpus_id,
        passed_case_count=passed,
        coverage_tags=tuple(sorted(coverage)),
    )


def store_reference_solver_algorithmic_qualification(
    certificate: ReferenceSolverAlgorithmicQualificationCertificate,
    *,
    store: ArtifactStore,
) -> str:
    store.read_bytes(certificate.worker_code_artifact_id)
    load_reference_solver_qualification_corpus(certificate.corpus_artifact_id, store=store)
    return store.put_bytes(
        canonical_json_bytes(certificate.semantic_payload()),
        media_type="application/json",
        schema_name="apex-reference-solver-algorithmic-qualification-certificate",
        schema_version="1",
    ).artifact_id


def _load_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReferenceSolverAlgorithmicQualificationCertificate:
    payload = _object(
        store.read_bytes(artifact_id),
        label="reference solver algorithmic qualification certificate",
    )
    if payload.get("schema_name") != "apex-reference-solver-algorithmic-qualification-certificate":
        raise ValueError("not a reference solver algorithmic qualification certificate")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported reference solver qualification certificate schema")
    coverage = payload.get("coverage_tags")
    if not isinstance(coverage, list) or any(not isinstance(item, str) for item in coverage):
        raise ValueError("reference solver qualification coverage_tags must be strings")
    certificate = ReferenceSolverAlgorithmicQualificationCertificate(
        worker_subject_id=str(payload.get("worker_subject_id") or ""),
        worker_name=str(payload.get("worker_name") or ""),
        worker_version=str(payload.get("worker_version") or ""),
        worker_code_artifact_id=str(payload.get("worker_code_artifact_id") or ""),
        solver_contract=str(payload.get("solver_contract") or ""),
        season=str(payload.get("season") or ""),
        max_horizon_gameweeks=payload.get("max_horizon_gameweeks"),  # type: ignore[arg-type]
        corpus_artifact_id=str(payload.get("corpus_artifact_id") or ""),
        corpus_id=str(payload.get("corpus_id") or ""),
        passed_case_count=payload.get("passed_case_count"),  # type: ignore[arg-type]
        coverage_tags=tuple(coverage),
        replay_algorithm_id=str(payload.get("replay_algorithm_id") or ""),
    )
    if certificate.certificate_id != artifact_id:
        raise ValueError("reference solver qualification certificate semantic identity mismatch")
    return certificate


def verify_reference_solver_algorithmic_qualification(
    worker: ReferenceSolverWorkerArtifact,
    *,
    qualification_artifact_id: str,
    store: ArtifactStore,
    season: str,
    horizon_gameweeks: int,
) -> ReferenceSolverAlgorithmicQualificationCertificate:
    """Re-run the sealed corpus and require exact derivation of the stored certificate."""

    stored = _load_certificate(qualification_artifact_id, store=store)
    replayed = derive_reference_solver_algorithmic_qualification(
        worker,
        corpus_artifact_id=stored.corpus_artifact_id,
        store=store,
    )
    if replayed.semantic_payload() != stored.semantic_payload():
        raise ValueError("reference solver qualification certificate failed replay derivation")
    subject = _shadow_subject(worker)
    expected_subject = reference_solver_worker_subject_id(subject.semantic_payload())
    if stored.worker_subject_id != expected_subject:
        raise ValueError("reference solver qualification subject mismatch")
    if stored.worker_code_artifact_id != worker.code_artifact_id:
        raise ValueError("reference solver qualification code artifact mismatch")
    if stored.solver_contract != worker.solver_contract:
        raise ValueError("reference solver qualification solver contract mismatch")
    if stored.season != season:
        raise ValueError("reference solver qualification season mismatch")
    if horizon_gameweeks > stored.max_horizon_gameweeks:
        raise ValueError("reference solver qualification horizon does not cover decision")
    return stored