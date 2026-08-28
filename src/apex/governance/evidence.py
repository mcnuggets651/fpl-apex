from __future__ import annotations
from datetime import datetime, timezone
from apex.domain.models import EvidenceEffect, EvidenceRecord, OfficialSnapshot
TRUSTED_HARD_TIERS = {'official_club', 'official_league'}

def validate_evidence(records: tuple[EvidenceRecord, ...], official: OfficialSnapshot, *, now: datetime | None=None) -> tuple[str, ...]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors = []
    for r in records:
        if r.element_id not in official.player_ids:
            errors.append(f'{r.evidence_id}: unknown Official FPL id')
        if r.effect == EvidenceEffect.HARD_EXCLUDE and r.source_tier not in TRUSTED_HARD_TIERS:
            errors.append(f'{r.evidence_id}: hard exclusion requires official source tier')
        if not r.source_url.startswith(('https://', 'http://')):
            errors.append(f'{r.evidence_id}: invalid source URL')
        try:
            pub = datetime.fromisoformat(r.published_at.replace('Z', '+00:00'))
            exp = datetime.fromisoformat(r.expires_at.replace('Z', '+00:00'))
            pub = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
            exp = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
            if exp <= pub or now > exp:
                errors.append(f'{r.evidence_id}: evidence expired/invalid')
        except Exception:
            errors.append(f'{r.evidence_id}: invalid evidence timestamps')
        if len(r.content_hash) != 64:
            errors.append(f'{r.evidence_id}: invalid content hash')
    return tuple(errors)

def hard_exclusions(records: tuple[EvidenceRecord, ...], gameweek: int) -> frozenset[int]:
    return frozenset((r.element_id for r in records if r.effect == EvidenceEffect.HARD_EXCLUDE and int(r.gameweek) == int(gameweek)))
