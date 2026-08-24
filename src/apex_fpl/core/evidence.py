"""Dependency-free structured evidence and append-only supersession contracts.

External text is data, never executable instruction.  A fact may enter Apex only as a
constrained claim tied to an exact Official FPL player ID, immutable raw evidence,
bitemporal timestamps and contextual reliability.  Unqualified reliability remains
UNKNOWN and cannot be converted into a guessed coefficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlparse

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .reliability import ReliabilityContext


class EvidenceClaimType(str, Enum):
    AVAILABILITY = "AVAILABILITY"
    INJURY = "INJURY"
    SUSPENSION = "SUSPENSION"
    EXPECTED_START = "EXPECTED_START"
    EXPECTED_MINUTES = "EXPECTED_MINUTES"
    TACTICAL_ROLE = "TACTICAL_ROLE"
    TRANSFER = "TRANSFER"
    PENALTY_ORDER = "PENALTY_ORDER"
    DIRECT_FREE_KICK_ORDER = "DIRECT_FREE_KICK_ORDER"
    CORNER_ORDER = "CORNER_ORDER"
    SET_PIECE_ROLE = "SET_PIECE_ROLE"
    SQUAD_HIERARCHY = "SQUAD_HIERARCHY"
    MANAGER_STATEMENT = "MANAGER_STATEMENT"


class EvidencePolarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class EvidenceConflictState(str, Enum):
    NONE = "NONE"
    CORROBORATED = "CORROBORATED"
    CONFLICTING = "CONFLICTING"


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"invalid evidence artifact ID: {value!r}")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"invalid evidence artifact digest: {value!r}") from exc
    return text


def _aware_iso(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _optional_time(value: str | None, *, label: str) -> str | None:
    return None if value is None else _aware_iso(value, label=label)


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bps(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{label} must be integer basis points in [0, 10000]")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    player_id: OfficialPlayerId
    claim_type: EvidenceClaimType
    source_id: str
    source_capability: str
    statement: str
    polarity: EvidencePolarity
    confidence_bps: int
    reliability: ReliabilityContext
    raw_artifact_id: str
    source_url: str
    first_known_at: str
    observed_at: str
    ingested_at: str
    source_event_at: str | None = None
    effective_from: str | None = None
    expires_at: str | None = None
    supersedes_claim_id: str | None = None
    conflict_state: EvidenceConflictState = EvidenceConflictState.NONE
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported EvidenceClaim schema_version")
        for label in ("source_id", "source_capability", "statement"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"{label} cannot be empty")
            object.__setattr__(self, label, value)
        source_url = str(self.source_url).strip()
        parsed_url = urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        object.__setattr__(self, "source_url", source_url)
        if self.reliability.source_id != self.source_id:
            raise ValueError("evidence reliability source does not match claim source")
        if self.reliability.claim_type != self.claim_type.value:
            raise ValueError("evidence reliability claim type does not match claim type")
        object.__setattr__(self, "confidence_bps", _bps(self.confidence_bps, label="confidence_bps"))
        object.__setattr__(self, "raw_artifact_id", _artifact_id(self.raw_artifact_id))

        first_known = _aware_iso(self.first_known_at, label="first_known_at")
        observed = _aware_iso(self.observed_at, label="observed_at")
        ingested = _aware_iso(self.ingested_at, label="ingested_at")
        source_event = _optional_time(self.source_event_at, label="source_event_at")
        effective = _optional_time(self.effective_from, label="effective_from")
        expires = _optional_time(self.expires_at, label="expires_at")
        if _point(observed) > _point(ingested):
            raise ValueError("observed_at cannot be after ingested_at")
        if _point(first_known) > _point(ingested):
            raise ValueError("first_known_at cannot be after ingested_at")
        if source_event is not None and _point(source_event) > _point(observed):
            raise ValueError("source_event_at cannot be after observed_at")
        if expires is not None:
            start = effective or first_known
            if _point(expires) <= _point(start):
                raise ValueError("expires_at must be after evidence start")
        if self.supersedes_claim_id is not None:
            supersedes = str(self.supersedes_claim_id).strip()
            if len(supersedes) != 64:
                raise ValueError("supersedes_claim_id must be a SHA-256 semantic claim ID")
            try:
                int(supersedes, 16)
            except ValueError as exc:
                raise ValueError("supersedes_claim_id digest is invalid") from exc
            object.__setattr__(self, "supersedes_claim_id", supersedes)
        object.__setattr__(self, "first_known_at", first_known)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "ingested_at", ingested)
        object.__setattr__(self, "source_event_at", source_event)
        object.__setattr__(self, "effective_from", effective)
        object.__setattr__(self, "expires_at", expires)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-evidence-claim",
            "schema_version": self.schema_version,
            "player_id": int(self.player_id),
            "claim_type": self.claim_type.value,
            "source_id": self.source_id,
            "source_capability": self.source_capability,
            "statement": self.statement,
            "polarity": self.polarity.value,
            "confidence_bps": self.confidence_bps,
            "reliability": self.reliability.semantic_payload(),
            "raw_artifact_id": self.raw_artifact_id,
            "source_url": self.source_url,
            "first_known_at": self.first_known_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "source_event_at": self.source_event_at,
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "supersedes_claim_id": self.supersedes_claim_id,
            "conflict_state": self.conflict_state.value,
        }

    @property
    def claim_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def eligible_for_weighting(self) -> bool:
        return self.reliability.usable_for_weighting

    def known_by(self, cutoff: str) -> bool:
        return _point(self.first_known_at) <= _point(_aware_iso(cutoff, label="cutoff"))

    def active_at(self, cutoff: str) -> bool:
        cutoff_iso = _aware_iso(cutoff, label="cutoff")
        point = _point(cutoff_iso)
        if not self.known_by(cutoff_iso):
            return False
        if self.effective_from is not None and point < _point(self.effective_from):
            return False
        if self.expires_at is not None and point >= _point(self.expires_at):
            return False
        return True


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    claims: tuple[EvidenceClaim, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported EvidenceLedger schema_version")
        claims = tuple(self.claims)
        by_id: dict[str, EvidenceClaim] = {}
        for claim in claims:
            if claim.claim_id in by_id:
                raise ValueError("EvidenceLedger cannot contain duplicate semantic claims")
            if claim.supersedes_claim_id is not None:
                prior = by_id.get(claim.supersedes_claim_id)
                if prior is None:
                    raise ValueError("evidence correction may supersede only an earlier ledger claim")
                if (
                    prior.player_id != claim.player_id
                    or prior.claim_type is not claim.claim_type
                    or prior.source_id != claim.source_id
                ):
                    raise ValueError("evidence supersession must correct the same source/player/claim type")
                if _point(claim.first_known_at) < _point(prior.first_known_at):
                    raise ValueError("evidence correction cannot become known before the claim it supersedes")
            by_id[claim.claim_id] = claim
        object.__setattr__(self, "claims", claims)

    @property
    def ledger_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-evidence-ledger",
                "schema_version": self.schema_version,
                "claim_ids": [claim.claim_id for claim in self.claims],
            }
        )

    def append(self, claim: EvidenceClaim) -> "EvidenceLedger":
        return EvidenceLedger(self.claims + (claim,), schema_version=self.schema_version)

    def active_claims(self, cutoff: str) -> tuple[EvidenceClaim, ...]:
        superseded = {
            claim.supersedes_claim_id
            for claim in self.claims
            if claim.supersedes_claim_id is not None and claim.known_by(cutoff)
        }
        return tuple(
            claim
            for claim in self.claims
            if claim.claim_id not in superseded and claim.active_at(cutoff)
        )
