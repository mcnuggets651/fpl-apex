"""Proof-driven promotion from SHADOW to QUALIFIED source capability."""

from __future__ import annotations

from dataclasses import dataclass, replace

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.source_registry import RegisteredSourceCapability
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.sources import SourceAdmissionState


def _bps(value: int, *, label: str, signed: bool = False) -> int:
    low = -10_000 if signed else 0
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= 10_000:
        raise ValueError(f"{label} must be integer basis points in [{low}, 10000]")
    return value


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


@dataclass(frozen=True, slots=True)
class ShadowQualificationReport:
    source_id: str
    capability: str
    observation_count: int
    overlap_count: int
    timeliness_bps: int
    schema_stability_bps: int
    outcome_consistency_bps: int
    marginal_value_bps: int
    security_incident_count: int
    evidence_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in ("source_id", "capability"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"{label} cannot be empty")
            object.__setattr__(self, label, value)
        for label in ("observation_count", "overlap_count", "security_incident_count"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a nonnegative integer")
        if self.overlap_count > self.observation_count:
            raise ValueError("shadow overlap_count cannot exceed observation_count")
        object.__setattr__(self, "timeliness_bps", _bps(self.timeliness_bps, label="timeliness_bps"))
        object.__setattr__(self, "schema_stability_bps", _bps(self.schema_stability_bps, label="schema_stability_bps"))
        object.__setattr__(self, "outcome_consistency_bps", _bps(self.outcome_consistency_bps, label="outcome_consistency_bps"))
        object.__setattr__(self, "marginal_value_bps", _bps(self.marginal_value_bps, label="marginal_value_bps", signed=True))
        artifacts = tuple(sorted({_artifact_id(item, label="shadow evidence artifact") for item in self.evidence_artifact_ids}))
        if not artifacts:
            raise ValueError("shadow qualification report requires immutable evidence artifacts")
        object.__setattr__(self, "evidence_artifact_ids", artifacts)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "capability": self.capability,
            "observation_count": self.observation_count,
            "overlap_count": self.overlap_count,
            "timeliness_bps": self.timeliness_bps,
            "schema_stability_bps": self.schema_stability_bps,
            "outcome_consistency_bps": self.outcome_consistency_bps,
            "marginal_value_bps": self.marginal_value_bps,
            "security_incident_count": self.security_incident_count,
            "evidence_artifact_ids": list(self.evidence_artifact_ids),
        }

    @property
    def report_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-shadow-source-report", "schema_version": 1, **self.semantic_payload()})


@dataclass(frozen=True, slots=True)
class SourceAdmissionPolicy:
    policy_id: str
    minimum_observations: int
    minimum_overlap: int
    minimum_timeliness_bps: int
    minimum_schema_stability_bps: int
    minimum_outcome_consistency_bps: int
    minimum_marginal_value_bps: int
    maximum_security_incidents: int
    policy_artifact_id: str

    def __post_init__(self) -> None:
        policy_id = str(self.policy_id).strip()
        if not policy_id:
            raise ValueError("source admission policy_id cannot be empty")
        object.__setattr__(self, "policy_id", policy_id)
        for label in ("minimum_observations", "minimum_overlap", "maximum_security_incidents"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a nonnegative integer")
        object.__setattr__(self, "minimum_timeliness_bps", _bps(self.minimum_timeliness_bps, label="minimum_timeliness_bps"))
        object.__setattr__(self, "minimum_schema_stability_bps", _bps(self.minimum_schema_stability_bps, label="minimum_schema_stability_bps"))
        object.__setattr__(self, "minimum_outcome_consistency_bps", _bps(self.minimum_outcome_consistency_bps, label="minimum_outcome_consistency_bps"))
        object.__setattr__(self, "minimum_marginal_value_bps", _bps(self.minimum_marginal_value_bps, label="minimum_marginal_value_bps", signed=True))
        object.__setattr__(self, "policy_artifact_id", _artifact_id(self.policy_artifact_id, label="source admission policy artifact"))


@dataclass(frozen=True, slots=True)
class SourceQualificationDecision:
    qualified: bool
    reasons: tuple[str, ...]
    decision_artifact_id: str
    promoted: RegisteredSourceCapability | None = None


def evaluate_shadow_promotion(
    registered: RegisteredSourceCapability,
    report: ShadowQualificationReport,
    policy: SourceAdmissionPolicy,
    *,
    store: ArtifactStore,
) -> SourceQualificationDecision:
    if registered.capability.admission_state is not SourceAdmissionState.SHADOW:
        raise ValueError("only SHADOW source capabilities can be promoted")
    if (registered.capability.source_id, registered.capability.capability) != (
        report.source_id,
        report.capability,
    ):
        raise ValueError("shadow report does not match registered source capability")
    if not store.verify(policy.policy_artifact_id):
        raise ValueError("source admission policy artifact is missing/corrupt")
    for artifact in report.evidence_artifact_ids:
        if not store.verify(artifact):
            raise ValueError("shadow qualification evidence artifact is missing/corrupt")

    checks = {
        "observation_count": report.observation_count >= policy.minimum_observations,
        "overlap_count": report.overlap_count >= policy.minimum_overlap,
        "timeliness": report.timeliness_bps >= policy.minimum_timeliness_bps,
        "schema_stability": report.schema_stability_bps >= policy.minimum_schema_stability_bps,
        "outcome_consistency": report.outcome_consistency_bps >= policy.minimum_outcome_consistency_bps,
        "marginal_value": report.marginal_value_bps >= policy.minimum_marginal_value_bps,
        "security_incidents": report.security_incident_count <= policy.maximum_security_incidents,
    }
    reasons = tuple(sorted(name for name, passed in checks.items() if not passed))
    qualified = not reasons
    decision_payload = {
        "schema_name": "apex-source-qualification-decision",
        "schema_version": 1,
        "registered_capability_id": registered.capability.capability_id,
        "report_id": report.report_id,
        "policy_id": policy.policy_id,
        "policy_artifact_id": policy.policy_artifact_id,
        "checks": checks,
        "qualified": qualified,
        "failed_checks": list(reasons),
    }
    decision_ref = store.put_bytes(
        canonical_json_bytes(decision_payload),
        media_type="application/json",
        schema_name="apex-source-qualification-decision",
        schema_version="1",
    )
    promoted = None
    if qualified:
        promoted = RegisteredSourceCapability(
            capability=replace(
                registered.capability,
                admission_state=SourceAdmissionState.QUALIFIED,
            ),
            allowed_hosts=registered.allowed_hosts,
            qualification_artifact_id=decision_ref.artifact_id,
        )
    return SourceQualificationDecision(
        qualified=qualified,
        reasons=reasons,
        decision_artifact_id=decision_ref.artifact_id,
        promoted=promoted,
    )
