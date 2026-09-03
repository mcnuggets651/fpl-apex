from __future__ import annotations

from datetime import datetime, timezone

from apex.decision.validate import validate_system_decision
from apex.domain.models import (
    CertificationResult,
    CertificationState,
    OfficialSnapshot,
    ProviderHealth,
    ProviderStatus,
    ReasonCode,
    SystemDecision,
    TeamState,
)


def certify(
    *,
    official: OfficialSnapshot | None,
    serving: ProviderStatus | None,
    decision: SystemDecision | None,
    team_state: TeamState | None = None,
    hard_evidence_conflict: bool = False,
    evidence_acquisition_complete: bool = True,
    contingency_model_complete: bool = True,
    degraded_warnings: tuple[str, ...] = (),
    shadow_warnings: tuple[str, ...] = (),
    valid_until: str | None = None,
    now: datetime | None = None,
) -> CertificationResult:
    reasons = []
    warnings = list(degraded_warnings) + list(shadow_warnings)
    if official is None or not official.players:
        reasons.append(ReasonCode.OFFICIAL_TRUTH_INVALID)
    if serving is None:
        reasons.append(ReasonCode.CHAMPION_UNAVAILABLE)
    elif serving.health == ProviderHealth.STALE:
        reasons.append(ReasonCode.CHAMPION_STALE)
    elif serving.health in {ProviderHealth.INCOMPLETE, ProviderHealth.ERROR}:
        reasons.append(ReasonCode.CHAMPION_INCOMPLETE)
    if hard_evidence_conflict:
        reasons.append(ReasonCode.HARD_EVIDENCE_CONFLICT)
    if not evidence_acquisition_complete:
        reasons.append(ReasonCode.EVIDENCE_ACQUISITION_INCOMPLETE)
    if not contingency_model_complete:
        reasons.append(ReasonCode.CONTINGENCY_MODEL_INCOMPLETE)
    if official is not None and decision is not None:
        errs = validate_system_decision(official, decision, team_state)
        if errs:
            reasons.append(ReasonCode.DECISION_ILLEGAL)
            warnings.extend(errs)
    else:
        reasons.append(ReasonCode.DECISION_ILLEGAL)
    if decision and decision.decision_mode == "TRANSFER_HORIZON" and (
        team_state is None or not team_state.state_complete_for_transfers
    ):
        reasons.append(ReasonCode.TEAM_STATE_INCOMPLETE)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if valid_until:
        try:
            expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            reasons.append(ReasonCode.SNAPSHOT_INCOHERENT)
            warnings.append("certification valid_until is not a valid ISO-8601 deadline")
        else:
            if now >= expiry.astimezone(timezone.utc):
                return CertificationResult(
                    1,
                    CertificationState.EXPIRED,
                    False,
                    tuple(dict.fromkeys(reasons)),
                    tuple(dict.fromkeys(warnings)),
                    valid_until,
                )
    if reasons:
        return CertificationResult(
            1,
            CertificationState.BLOCKED,
            False,
            tuple(dict.fromkeys(reasons)),
            tuple(dict.fromkeys(warnings)),
            valid_until,
        )
    state = CertificationState.DEGRADED if warnings else CertificationState.CERTIFIED
    return CertificationResult(
        1,
        state,
        True,
        (),
        tuple(dict.fromkeys(warnings)),
        valid_until,
    )
