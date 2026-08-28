from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from typing import Any
import requests
from apex.domain.models import OfficialFixture, OfficialPlayer, OfficialSnapshot, Position
BASE_URL = 'https://fantasy.premierleague.com/api'
_POSITION = {1: Position.GK, 2: Position.DEF, 3: Position.MID, 4: Position.FWD}

def _canonical_hash(*payloads: Any) -> str:
    return hashlib.sha256(json.dumps(payloads, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def fetch_official_snapshot(*, season='2026-2027', session: requests.Session | None=None, timeout: float=20.0):
    http = session or requests.Session()
    b = http.get(f'{BASE_URL}/bootstrap-static/', timeout=timeout)
    b.raise_for_status()
    f = http.get(f'{BASE_URL}/fixtures/', timeout=timeout)
    f.raise_for_status()
    bootstrap = b.json()
    fixtures_raw = f.json()
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get('elements'), list):
        raise ValueError('Official FPL bootstrap payload malformed')
    if not isinstance(fixtures_raw, list):
        raise ValueError('Official FPL fixtures payload malformed')
    players = []
    for r in bootstrap['elements']:
        eid = int(r['id'])
        typ = int(r['element_type'])
        if typ not in _POSITION:
            raise ValueError(f'unknown Official FPL element_type {typ} for {eid}')
        players.append(OfficialPlayer(eid, str(r.get('web_name', eid)), int(r['team']), _POSITION[typ], int(r['now_cost']), str(r.get('status', '')), bool(r.get('can_transact', True))))
    if len({p.element_id for p in players}) != len(players):
        raise ValueError('Official FPL duplicate element IDs')
    fixtures = tuple((OfficialFixture(int(r['id']), int(r['event']) if r.get('event') is not None else None, int(r['team_h']), int(r['team_a']), str(r['kickoff_time']) if r.get('kickoff_time') else None) for r in fixtures_raw))
    deadlines = {int(e['id']): str(e['deadline_time']) for e in bootstrap.get('events', []) if e.get('id') is not None and e.get('deadline_time')}
    acquired = datetime.now(timezone.utc).isoformat()
    digest = _canonical_hash(bootstrap, fixtures_raw)
    return (OfficialSnapshot(1, season, acquired, digest, tuple(players), fixtures, deadlines), {'bootstrap': bootstrap, 'fixtures': fixtures_raw})
