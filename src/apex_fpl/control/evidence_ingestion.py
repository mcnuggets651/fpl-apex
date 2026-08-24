"""Constrained evidence ingestion from retained raw source bytes.

Raw internet content is intentionally opaque at this boundary. An extractor may submit
only this fixed schema; source text cannot supply executable instructions, source
identity, admission state, player identity rules or optimisation parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reliability_registry import ReliabilityRegistry
from apex_fpl.control.source_registry import SourceRegistry
from apex_fpl.core.evidence import (
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConflictState,
    EvidencePolarity,
)
from apex_fpl.core.identity import IdentityRegistry, OfficialPlayerId
from apex_fpl.core.reliability import ReliabilityQualification
from apex_fpl.core.sources import SourceAdmissionState


class EvidenceAdmissionMode(str, Enum):
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True, slots=True)
class StructuredEvidenceInput:
    player_id: int
    claim_type: EvidenceClaimType
    source_id: str
    source_capability: str
    statement: str
    polarity: EvidencePolarity
    confidence_bps: int
    source_url: str
    raw_artifact_id: str
    first_known_at: str
    observed_at: str
    ingested_at: str
    horizon_gameweeks: int
    recency_bucket: str
    source_event_at: str | None = None
    effective_from: str | None = None
    expires_at: str | None = None
    supersedes_claim_id: str | None = None
    conflict_state: EvidenceConflictState = EvidenceConflictState.NONE

    def __post_init__(self) -> None:
        if isinstance(self.player_id, bool) or not isinstance(self.player_id, int) or self.player_id <= 0:
            raise ValueError("structured evidence player_id must be a positive Official integer ID")
        statement = str(self.statement).strip()
        if not statement or len(statement) > 2_000:
            raise ValueError("structured evidence statement must contain 1..2000 characters")
        if any(ord(char) < 32 and char not in "\n\t" for char in statement):
            raise ValueError("structured evidence statement contains disallowed control characters")
        object.__setattr__(self, "statement", statement)


@dataclass(frozen=True, slots=True)
class IngestedEvidence:
    claim: EvidenceClaim
    admission_mode: EvidenceAdmissionMode
    reasons: tuple[str, ...]

    @property
    def production_eligible(self) -> bool:
        return self.admission_mode is EvidenceAdmissionMode.PRODUCTION


def ingest_structured_evidence(
    payload: StructuredEvidenceInput,
    *,
    sources: SourceRegistry,
    reliability: ReliabilityRegistry,
    identities: IdentityRegistry,
    store: ArtifactStore,
) -> IngestedEvidence:
    """Validate one typed extraction without interpreting its raw source text."""

    player_id = OfficialPlayerId(payload.player_id)
    if identities.get(player_id) is None:
        raise ValueError(f"structured evidence references unknown Official player {player_id}")
    registered = sources.get(payload.source_id, payload.source_capability)
    if registered is None:
        raise ValueError("structured evidence source/capability is not registered")
    if registered.capability.admission_state in {
        SourceAdmissionState.SUSPENDED,
        SourceAdmissionState.RETIRED,
    }:
        raise ValueError("structured evidence source/capability is not admissible")
    if not registered.permits_url(payload.source_url):
        raise ValueError("structured evidence URL host does not match registered source identity")
    if not store.verify(payload.raw_artifact_id):
        raise ValueError("structured evidence raw artifact is missing or corrupt")
    if registered.capability.admission_state is SourceAdmissionState.QUALIFIED:
        artifact = registered.qualification_artifact_id
        if artifact is None or not store.verify(artifact):
            raise ValueError("structured evidence source qualification artifact is missing/corrupt")

    context = reliability.lookup(
        source_id=payload.source_id,
        claim_type=payload.claim_type.value,
        horizon_gameweeks=payload.horizon_gameweeks,
        recency_bucket=payload.recency_bucket,
    )
    if context.qualification is ReliabilityQualification.QUALIFIED:
        artifact = context.qualification_artifact_id
        if artifact is None or not store.verify(artifact):
            raise ValueError("structured evidence reliability qualification artifact is missing/corrupt")

    claim = EvidenceClaim(
        player_id=player_id,
        claim_type=payload.claim_type,
        source_id=payload.source_id,
        source_capability=payload.source_capability,
        statement=payload.statement,
        polarity=payload.polarity,
        confidence_bps=payload.confidence_bps,
        reliability=context,
        raw_artifact_id=payload.raw_artifact_id,
        source_url=payload.source_url,
        first_known_at=payload.first_known_at,
        observed_at=payload.observed_at,
        ingested_at=payload.ingested_at,
        source_event_at=payload.source_event_at,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        supersedes_claim_id=payload.supersedes_claim_id,
        conflict_state=payload.conflict_state,
    )

    reasons: list[str] = []
    production = True
    if registered.capability.admission_state is not SourceAdmissionState.QUALIFIED:
        production = False
        reasons.append("source capability is not V2-qualified")
    if not claim.eligible_for_weighting:
        production = False
        reasons.append("contextual reliability is unqualified")
    return IngestedEvidence(
        claim=claim,
        admission_mode=(
            EvidenceAdmissionMode.PRODUCTION if production else EvidenceAdmissionMode.SHADOW
        ),
        reasons=tuple(reasons),
    )
