from __future__ import annotations

from datetime import datetime, timezone

from apex.domain.models import EvidenceEffect, EvidenceRecord, OfficialSnapshot

TRUSTED_HARD_TIERS = {"official_club", "official_league"}


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_evidence(
    records: tuple[EvidenceRecord, ...],
    official: OfficialSnapshot,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors = []
    for record in records:
        if record.element_id not in official.player_ids:
            errors.append(f"{record.evidence_id}: unknown Official FPL id")
        if (
            record.effect == EvidenceEffect.HARD_EXCLUDE
            and record.source_tier not in TRUSTED_HARD_TIERS
        ):
            errors.append(
                f"{record.evidence_id}: hard exclusion requires official source tier"
            )
        if not record.source_url.startswith(("https://", "http://")):
            errors.append(f"{record.evidence_id}: invalid source URL")
        try:
            published = _utc(record.published_at)
            retrieved = _utc(record.retrieved_at)
            expires = _utc(record.expires_at)
            if published > now:
                errors.append(f"{record.evidence_id}: published timestamp is in the future")
            if retrieved > now:
                errors.append(f"{record.evidence_id}: retrieved timestamp is in the future")
            if retrieved < published:
                errors.append(
                    f"{record.evidence_id}: retrieved timestamp precedes publication"
                )
            if expires <= published or now > expires:
                errors.append(f"{record.evidence_id}: evidence expired/invalid")
        except (TypeError, ValueError):
            errors.append(f"{record.evidence_id}: invalid evidence timestamps")
        digest = str(record.content_hash)
        if len(digest) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in digest
        ):
            errors.append(f"{record.evidence_id}: invalid content hash")
    return tuple(dict.fromkeys(errors))


def hard_exclusions(
    records: tuple[EvidenceRecord, ...], gameweek: int
) -> frozenset[int]:
    return frozenset(
        record.element_id
        for record in records
        if record.effect == EvidenceEffect.HARD_EXCLUDE
        and int(record.gameweek) == int(gameweek)
    )
