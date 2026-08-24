"""Content-addressed append-only storage for the V2 EvidenceLedger."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.evidence import (
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConflictState,
    EvidenceLedger,
    EvidencePolarity,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.reliability import ReliabilityContext, ReliabilityQualification


LEDGER_SCHEMA = "apex-evidence-ledger-envelope"
LEDGER_SCHEMA_VERSION = 1


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("evidence ledger artifact ID must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("evidence ledger artifact digest is invalid") from exc
    return text


def _claim_from_payload(payload: dict[str, object]) -> EvidenceClaim:
    reliability = payload.get("reliability")
    if not isinstance(reliability, dict):
        raise ValueError("stored evidence claim is missing reliability context")
    return EvidenceClaim(
        player_id=OfficialPlayerId(int(payload["player_id"])),
        claim_type=EvidenceClaimType(str(payload["claim_type"])),
        source_id=str(payload["source_id"]),
        source_capability=str(payload["source_capability"]),
        statement=str(payload["statement"]),
        polarity=EvidencePolarity(str(payload["polarity"])),
        confidence_bps=int(payload["confidence_bps"]),
        reliability=ReliabilityContext(
            source_id=str(reliability["source_id"]),
            claim_type=str(reliability["claim_type"]),
            horizon_gameweeks=int(reliability["horizon_gameweeks"]),
            recency_bucket=str(reliability["recency_bucket"]),
            qualification=ReliabilityQualification(str(reliability["qualification"])),
            reliability_bps=(
                None
                if reliability.get("reliability_bps") is None
                else int(reliability["reliability_bps"])
            ),
            sample_count=int(reliability.get("sample_count", 0)),
            qualification_artifact_id=(
                None
                if reliability.get("qualification_artifact_id") is None
                else str(reliability["qualification_artifact_id"])
            ),
        ),
        raw_artifact_id=str(payload["raw_artifact_id"]),
        source_url=str(payload["source_url"]),
        first_known_at=str(payload["first_known_at"]),
        observed_at=str(payload["observed_at"]),
        ingested_at=str(payload["ingested_at"]),
        source_event_at=(
            None if payload.get("source_event_at") is None else str(payload["source_event_at"])
        ),
        effective_from=(
            None if payload.get("effective_from") is None else str(payload["effective_from"])
        ),
        expires_at=None if payload.get("expires_at") is None else str(payload["expires_at"]),
        supersedes_claim_id=(
            None
            if payload.get("supersedes_claim_id") is None
            else str(payload["supersedes_claim_id"])
        ),
        conflict_state=EvidenceConflictState(str(payload.get("conflict_state", "NONE"))),
        schema_version=int(payload.get("schema_version", -1)),
    )


@dataclass(frozen=True, slots=True)
class StoredEvidenceLedger:
    ledger: EvidenceLedger
    artifact_id: str
    parent_artifact_id: str | None


def store_evidence_ledger(
    ledger: EvidenceLedger,
    *,
    store: ArtifactStore,
    parent_artifact_id: str | None = None,
) -> StoredEvidenceLedger:
    parent = None if parent_artifact_id is None else _artifact_id(parent_artifact_id)
    if parent is not None and not store.verify(parent):
        raise ValueError("evidence ledger parent artifact is missing/corrupt")
    envelope = {
        "schema_name": LEDGER_SCHEMA,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger.ledger_id,
        "parent_artifact_id": parent,
        "claims": [claim.semantic_payload() for claim in ledger.claims],
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=LEDGER_SCHEMA,
        schema_version=str(LEDGER_SCHEMA_VERSION),
    )
    return StoredEvidenceLedger(ledger, ref.artifact_id, parent)


def load_evidence_ledger(artifact_id: str, *, store: ArtifactStore) -> StoredEvidenceLedger:
    current = _artifact_id(artifact_id)
    raw = store.read_bytes(current)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("evidence ledger artifact is not UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_name") != LEDGER_SCHEMA:
        raise ValueError("not an Apex evidence ledger artifact")
    if int(payload.get("schema_version", -1)) != LEDGER_SCHEMA_VERSION:
        raise ValueError("unsupported stored evidence ledger schema_version")
    rows = payload.get("claims")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("stored evidence ledger claims are invalid")
    ledger = EvidenceLedger(tuple(_claim_from_payload(dict(row)) for row in rows))
    if str(payload.get("ledger_id") or "") != ledger.ledger_id:
        raise ValueError("stored evidence ledger semantic identity mismatch")
    parent = payload.get("parent_artifact_id")
    parent_id = None if parent is None else _artifact_id(str(parent))
    if parent_id is not None and not store.verify(parent_id):
        raise ValueError("stored evidence ledger parent is missing/corrupt")
    return StoredEvidenceLedger(ledger, current, parent_id)


def append_evidence_claim(
    parent_artifact_id: str,
    claim: EvidenceClaim,
    *,
    store: ArtifactStore,
) -> StoredEvidenceLedger:
    parent = load_evidence_ledger(parent_artifact_id, store=store)
    child = parent.ledger.append(claim)
    stored = store_evidence_ledger(
        child,
        store=store,
        parent_artifact_id=parent.artifact_id,
    )
    if stored.ledger.claims[:-1] != parent.ledger.claims:
        raise AssertionError("append-only evidence ledger prefix changed")
    return stored
