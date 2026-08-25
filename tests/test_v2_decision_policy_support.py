from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_registry import DecisionPolicyRegistry
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
    store_decision_policy_support,
)
from apex_fpl.core.decision_policy import (
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    ChipOptionValuePolicy,
    ContinuationValuePolicy,
    ExactPolicyValue,
    PricePolicy,
)
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID

from empirical_qualification_helpers import synthetic_supported_qualification_artifact


SEASON = "2026-2027"
AVAILABLE = "2026-08-01T00:00:00Z"
AS_OF = "2026-08-25T06:00:00Z"


def _supports(store: FileSystemArtifactStore, *, horizon: int = 3, available: str = AVAILABLE):
    continuation = ContinuationValuePolicy(
        season=SEASON,
        horizon_gameweeks=horizon,
        first_available_at=available,
        gameweek_weights=tuple(
            ExactPolicyValue(1, 1) if index == 0 else ExactPolicyValue(1, 2)
            for index in range(horizon)
        ),
    )
    chip_option = ChipOptionValuePolicy(
        season=SEASON,
        horizon_gameweeks=horizon,
        first_available_at=available,
        option_values=(
            ("TRIPLE_CAPTAIN", ExactPolicyValue(5, 1)),
            ("BENCH_BOOST", ExactPolicyValue(4, 1)),
            ("WILDCARD", ExactPolicyValue(6, 1)),
            ("FREE_HIT", ExactPolicyValue(3, 1)),
        ),
    )
    price = PricePolicy(season=SEASON, first_available_at=available)
    candidate = CandidatePolicy(season=SEASON, first_available_at=available)
    objects = (continuation, chip_option, price, candidate)
    return objects, tuple(store_decision_policy_support(item, store=store) for item in objects)


def _shadow_policy(
    support_ids: tuple[str, str, str, str],
    *,
    horizon: int = 3,
    first_available_at: str = "2026-08-02T00:00:00Z",
) -> DecisionPolicy:
    continuation, chip_option, price, candidate = support_ids
    return DecisionPolicy(
        policy_name="typed-receding-policy",
        policy_version="1",
        season=SEASON,
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at=first_available_at,
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=horizon,
        continuation_value_artifact_id=continuation,
        chip_option_value_artifact_id=chip_option,
        price_policy_artifact_id=price,
        candidate_policy_artifact_id=candidate,
        tie_break_policy=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
        numeric_policy_id=DECISION_NUMERIC_POLICY_ID,
    )


def _qualified_policy(store: FileSystemArtifactStore) -> DecisionPolicy:
    _, support_ids = _supports(store)
    shadow = _shadow_policy(support_ids)
    qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=shadow.semantic_payload(),
        subject_kind="apex.decision-policy",
        proof_id="PO-DECISION-POLICY-QUALIFICATION-001",
        season=SEASON,
    )
    return replace(
        shadow,
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=qualification,
    )


def test_support_artifacts_round_trip_under_exact_content_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    objects, artifact_ids = _supports(store)
    loaded = (
        load_continuation_value_policy(artifact_ids[0], store=store, as_of=AVAILABLE),
        load_chip_option_value_policy(artifact_ids[1], store=store, as_of=AVAILABLE),
        load_price_policy(artifact_ids[2], store=store, as_of=AVAILABLE),
        load_candidate_policy(artifact_ids[3], store=store, as_of=AVAILABLE),
    )
    assert loaded == objects
    assert artifact_ids == tuple(item.policy_id for item in objects)


def test_receding_policy_requires_every_support_and_canonical_semantics(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    _, support_ids = _supports(store)
    with pytest.raises(ValueError, match="requires policy artifacts"):
        _shadow_policy((support_ids[0], support_ids[1], support_ids[2], None))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="numeric policy"):
        replace(_shadow_policy(support_ids), numeric_policy_id="floating-point-magic-v1")
    with pytest.raises(ValueError, match="tie-break"):
        replace(_shadow_policy(support_ids), tie_break_policy="unimplemented-tie-break")


def test_continuation_policy_cannot_collapse_to_tactical_or_hide_terminal_penalty() -> None:
    with pytest.raises(ValueError, match="positive future value"):
        ContinuationValuePolicy(
            season=SEASON,
            horizon_gameweeks=3,
            first_available_at=AVAILABLE,
            gameweek_weights=(
                ExactPolicyValue.one(),
                ExactPolicyValue.zero(),
                ExactPolicyValue.zero(),
            ),
        )
    with pytest.raises(ValueError, match="zero terminal"):
        ContinuationValuePolicy(
            season=SEASON,
            horizon_gameweeks=3,
            first_available_at=AVAILABLE,
            gameweek_weights=(
                ExactPolicyValue.one(),
                ExactPolicyValue(1, 2),
                ExactPolicyValue(1, 2),
            ),
            terminal_value=ExactPolicyValue(-50, 1),
        )


def test_opaque_existing_bytes_cannot_satisfy_receding_support(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    _, support_ids = _supports(store)
    opaque = store.put_bytes(b"opaque-continuation-policy").artifact_id
    policy = _shadow_policy((opaque, *support_ids[1:]))
    registry = DecisionPolicyRegistry(
        season=SEASON,
        policies=(policy,),
        champion_policy_id=None,
    )
    with pytest.raises(ValueError, match="continuation-value policy"):
        registry.verify_policy_artifacts(policy, store=store, production=False)


def test_support_horizon_and_season_are_cross_bound_to_policy(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    _, wrong_horizon_ids = _supports(store, horizon=4)
    policy = _shadow_policy(wrong_horizon_ids, horizon=3)
    registry = DecisionPolicyRegistry(SEASON, (policy,), None)
    with pytest.raises(ValueError, match="horizon mismatch"):
        registry.verify_policy_artifacts(policy, store=store, production=False)

    foreign = PricePolicy(season="2025-2026", first_available_at=AVAILABLE)
    foreign_id = store_decision_policy_support(foreign, store=store)
    _, support_ids = _supports(store)
    policy = _shadow_policy((support_ids[0], support_ids[1], foreign_id, support_ids[3]))
    registry = DecisionPolicyRegistry(SEASON, (policy,), None)
    with pytest.raises(ValueError, match="season mismatch"):
        registry.verify_policy_artifacts(policy, store=store, production=False)


def test_policy_cannot_claim_availability_before_support_semantics(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    _, support_ids = _supports(store, available="2026-08-03T00:00:00Z")
    policy = _shadow_policy(support_ids, first_available_at="2026-08-02T00:00:00Z")
    registry = DecisionPolicyRegistry(SEASON, (policy,), None)
    with pytest.raises(ValueError, match="not available"):
        registry.verify_policy_artifacts(policy, store=store, production=False)


def test_typed_supports_do_not_fabricate_production_authority(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    _, support_ids = _supports(store)
    shadow = _shadow_policy(support_ids)
    registry = DecisionPolicyRegistry(SEASON, (shadow,), None)
    registry.verify_policy_artifacts(shadow, store=store, production=False)
    with pytest.raises(ValueError, match="qualified receding-horizon"):
        registry.verify_policy_artifacts(
            shadow,
            store=store,
            production=True,
            as_of=AS_OF,
        )


def test_exact_typed_empirical_qualification_can_authorize_only_registered_champion(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    policy = _qualified_policy(store)
    non_champion = DecisionPolicyRegistry(SEASON, (policy,), None)
    with pytest.raises(ValueError, match="registered champion"):
        non_champion.verify_policy_artifacts(
            policy,
            store=store,
            production=True,
            as_of=AS_OF,
        )

    champion = DecisionPolicyRegistry(SEASON, (policy,), policy.decision_policy_id)
    champion.verify_policy_artifacts(policy, store=store, production=True, as_of=AS_OF)
