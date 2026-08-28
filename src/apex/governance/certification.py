from __future__ import annotations

from datetime import datetime, timezone

from apex.decision.validate import validate_system_decision
from apex.domain.models import (
    CertificationResult,
    CertificationState,
    OfficialSnapshot,
    ProviderStatus,
    ReasonCode,
    SystemDecision,
)


def certify(
    *,
    official: OfficialSnapshot | None,
    serving: ProviderStatus | None,
    decision: SystemDecision | None,
    hard_evidence_conflict: bool = False,
    degraded_warnings: tuple[str, ...] = (),
    shadow_warnings: tuple[str, ...] = (),
    valid_until: str | None = None,
) -> CertificationResult:
    reasons: list[ReasonCode] = []
    warnings = list(degraded_warnings)
    # Shadow failures are diagnostics only by construction. They may appear in the
    # report but cannot create a blocking reason.
    warnings.extend(shadow_warnings)
    if official is None or not official.players:
        reasons.append(ReasonCode.OFFICIAL_TRUTH_INVALID)
    if serving is None:
        reasons.append(ReasonCode.CHAMPION_UNAVAILABLE)
    if hard_evidence_conflict:
        reasons.append(ReasonCode.HARD_EVIDENCE_CONFLICT)
    if official is not None and decision is not None:
        decision_errors = validate_system_decision(official, decision)
        if decision_errors:
            reasons.append(ReasonCode.DECISION_ILLEGAL)
            warnings.extend(decision_errors)
    elif decision is None:
        reasons.append(ReasonCode.DECISION_ILLEGAL)

    if valid_until:
        expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry.astimezone(timezone.utc):
            return CertificationResult(
                schema_version=1,
                state=CertificationState.EXPIRED,
                actionable=False,
                reasons=tuple(dict.fromkeys(reasons)),
                warnings=tuple(warnings),
                valid_until=valid_until,
            )

    if reasons:
        return CertificationResult(
            schema_version=1,
            state=CertificationState.BLOCKED,
            actionable=False,
            reasons=tuple(dict.fromkeys(reasons)),
            warnings=tuple(warnings),
            valid_until=valid_until,
        )
    state = CertificationState.DEGRADED if warnings else CertificationState.CERTIFIED
    return CertificationResult(
        schema_version=1,
        state=state,
        actionable=True,
        reasons=(),
        warnings=tuple(warnings),
        valid_until=valid_until,
    )
