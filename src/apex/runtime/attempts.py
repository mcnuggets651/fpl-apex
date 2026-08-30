from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

@dataclass(frozen=True)
class AttemptAudit:
    intents: tuple[str, ...]
    finals: tuple[str, ...]
    missing_finals: tuple[str, ...]
    in_progress: tuple[str, ...]

def _created(row):
    value = row.get('created_at') or row.get('published_at')
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def audit_release_tags(releases: list[dict], prefix='apex-v2', *, grace_hours: float=4, now: datetime | None=None) -> AttemptAudit:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    intents = {}
    finals = {}
    for r in releases:
        tag = str(r.get('tag_name', ''))
        if tag.startswith(f'{prefix}/intent/'):
            intents[tag.split('/intent/', 1)[1]] = (tag, _created(r))
        elif tag.startswith(f'{prefix}/final/'):
            finals[tag.split('/final/', 1)[1]] = tag
    missing = []
    progress = []
    for key, (tag, created) in intents.items():
        if key in finals:
            continue
        (progress if now - created < timedelta(hours=grace_hours) else missing).append(tag)
    return AttemptAudit(tuple(sorted((t for t, _ in intents.values()))), tuple(sorted(finals.values())), tuple(sorted(missing)), tuple(sorted(progress)))
