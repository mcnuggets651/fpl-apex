"""Load and verify versioned DecisionPolicy manifests outside the constitutional core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.empirical_qualification_admission import (
    verify_typed_empirical_qualification,
)
from apex_fpl.core.decision_policy import (
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.ids import DecisionPolicyId
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID


@dataclass(frozen=True, slots=True)
class DecisionPolicyRegistry:
    season: str
    policies: tuple[DecisionPolicy, ...]
    champion_policy_id: DecisionPolicyId | None

    def __post_init__(self) -> None:
        policies = tuple(sorted(self.policies, key=lambda row: str(row.decision_policy_id)))
        ids = [row.decision_policy_id for row in policies]
        if len(ids) != len(set(ids)):
            raise ValueError("DecisionPolicy registry contains duplicate policy identities")
        if any(row.season != self.season for row in policies):
            raise ValueError("DecisionPolicy registry season mismatch")
        if self.champion_policy_id is not None:
            champion = next(
                (row for row in policies if row.decision_policy_id == self.champion_policy_id),
                None,
            )
            if champion is None:
                raise ValueError("DecisionPolicy champion is not registered")
            if not champion.production_qualified:
                raise ValueError("DecisionPolicy champion must be production qualified")
        object.__setattr__(self, "policies", policies)

    def get(self, policy_id: DecisionPolicyId) -> DecisionPolicy | None:
        return next(
            (row for row in self.policies if row.decision_policy_id == policy_id),
            None,
        )

    def champion(self) -> DecisionPolicy | None:
        if self.champion_policy_id is None:
            return None
        return self.get(self.champion_policy_id)

    def _verify_receding_supports(
        self,
        policy: DecisionPolicy,
        *,
        store: ArtifactStore,
    ) -> None:
        if policy.evaluation_mode is not DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION:
            return
        support_ids = (
            policy.continuation_value_artifact_id,
            policy.chip_option_value_artifact_id,
            policy.price_policy_artifact_id,
            policy.candidate_policy_artifact_id,
        )
        if any(artifact_id is None for artifact_id in support_ids):
            raise ValueError("receding-horizon DecisionPolicy lacks complete support artifacts")

        continuation = load_continuation_value_policy(
            policy.continuation_value_artifact_id,  # type: ignore[arg-type]
            store=store,
            as_of=policy.first_available_at,
        )
        chip_option = load_chip_option_value_policy(
            policy.chip_option_value_artifact_id,  # type: ignore[arg-type]
            store=store,
            as_of=policy.first_available_at,
        )
        price = load_price_policy(
            policy.price_policy_artifact_id,  # type: ignore[arg-type]
            store=store,
            as_of=policy.first_available_at,
        )
        candidate = load_candidate_policy(
            policy.candidate_policy_artifact_id,  # type: ignore[arg-type]
            store=store,
            as_of=policy.first_available_at,
        )
        supports = (continuation, chip_option, price, candidate)
        if any(support.season != policy.season for support in supports):
            raise ValueError("DecisionPolicy support artifact season mismatch")
        if continuation.horizon_gameweeks != policy.horizon_gameweeks:
            raise ValueError("DecisionPolicy continuation-value horizon mismatch")
        if chip_option.horizon_gameweeks != policy.horizon_gameweeks:
            raise ValueError("DecisionPolicy chip-option horizon mismatch")

    def verify_policy_artifacts(
        self,
        policy: DecisionPolicy,
        *,
        store: ArtifactStore,
        production: bool,
        as_of: str | None = None,
    ) -> None:
        if self.get(policy.decision_policy_id) != policy:
            raise ValueError("DecisionPolicy is not registered under its semantic identity")
        if policy.qualification_artifact_id is not None:
            store.read_bytes(policy.qualification_artifact_id)
        self._verify_receding_supports(policy, store=store)
        if production:
            if not policy.production_qualified:
                raise ValueError("production requires a qualified receding-horizon DecisionPolicy")
            if self.champion_policy_id != policy.decision_policy_id:
                raise ValueError("production DecisionPolicy must be the registered champion")
            if as_of is None:
                raise ValueError("production DecisionPolicy verification requires explicit as_of")
            policy.require_available_for(season=self.season, decision_cutoff=as_of)
            verify_typed_empirical_qualification(
                qualification_artifact_id=policy.qualification_artifact_id,
                subject_payload=policy.semantic_payload(),
                subject_kind="apex.decision-policy",
                proof_id="PO-DECISION-POLICY-QUALIFICATION-001",
                season=self.season,
                as_of=as_of,
                store=store,
            )


def load_decision_policy_registry(path: str | Path) -> DecisionPolicyRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("unsupported DecisionPolicy registry schema")
    season = str(raw.get("season") or "").strip()
    rows = raw.get("policies")
    if not season or not isinstance(rows, list):
        raise ValueError("DecisionPolicy registry requires season and policies list")
    policies: list[DecisionPolicy] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("DecisionPolicy registry rows must be objects")
        policies.append(
            DecisionPolicy(
                policy_name=str(row["policy_name"]),
                policy_version=str(row["policy_version"]),
                season=str(row["season"]),
                qualification_state=DecisionPolicyQualificationState(
                    str(row["qualification_state"])
                ),
                qualification_artifact_id=(
                    None
                    if row.get("qualification_artifact_id") is None
                    else str(row["qualification_artifact_id"])
                ),
                first_available_at=str(row["first_available_at"]),
                evaluation_mode=DecisionEvaluationMode(str(row["evaluation_mode"])),
                objective_policy=DecisionObjectivePolicy(str(row["objective_policy"])),
                horizon_gameweeks=int(row["horizon_gameweeks"]),
                continuation_value_artifact_id=(
                    None
                    if row.get("continuation_value_artifact_id") is None
                    else str(row["continuation_value_artifact_id"])
                ),
                chip_option_value_artifact_id=(
                    None
                    if row.get("chip_option_value_artifact_id") is None
                    else str(row["chip_option_value_artifact_id"])
                ),
                price_policy_artifact_id=(
                    None
                    if row.get("price_policy_artifact_id") is None
                    else str(row["price_policy_artifact_id"])
                ),
                candidate_policy_artifact_id=(
                    None
                    if row.get("candidate_policy_artifact_id") is None
                    else str(row["candidate_policy_artifact_id"])
                ),
                tie_break_policy=str(row["tie_break_policy"]),
                numeric_policy_id=str(
                    row.get("numeric_policy_id") or DECISION_NUMERIC_POLICY_ID
                ),
            )
        )
    champion_raw = raw.get("champion_policy_id")
    champion = None if champion_raw is None else DecisionPolicyId(str(champion_raw))
    return DecisionPolicyRegistry(
        season=season,
        policies=tuple(policies),
        champion_policy_id=champion,
    )
