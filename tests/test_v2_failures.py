from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from apex.domain.models import *
from apex.domain.rules import calculate_selling_price, validate_squad
from apex.forecast.contract import coverage_errors
from apex.forecast.registry import serving_provider, NoServingProvider
from apex.forecast.qualification import qualify_surface
from apex.runtime.snapshot import SnapshotBuilder, open_frozen_snapshot
from apex.runtime.attempts import audit_release_tags

def official():
    ps = []
    pid = 1
    for t in range(1, 8):
        for pos, count in ((Position.GK, 1), (Position.DEF, 2), (Position.MID, 2), (Position.FWD, 1)):
            for _ in range(count):
                ps.append(OfficialPlayer(pid, f'P{pid}', t, pos, 45, 'a', True))
                pid += 1
    return OfficialSnapshot(1, '2026-2027', '2026-08-28T10:00:00+00:00', 'snap', tuple(ps), (), {2: '2026-08-29T10:00:00Z'})

def surface(o, *, generated='2026-08-28T10:00:00+00:00', missing=(), provider='p'):
    missing = set(missing)
    rows = tuple((ProjectionRow(p.element_id, 2, 1, None if p.element_id in missing else 3.0, coverage_status=CoverageStatus.NO_FORECAST if p.element_id in missing else CoverageStatus.FORECAST, coverage_reason='missing' if p.element_id in missing else None) for p in o.players))
    return ProjectionSurface(1, provider, 'v1', generated, o.season, o.source_hash, '2026-2027', (1,), (), rows)

def test_no_forecast_never_counts_as_coverage():
    o = official()
    s = surface(o, missing={1})
    assert coverage_errors(s, o.decision_universe(), horizon=1)

def test_shadow_never_serves_even_when_authorized():
    o = official()
    s = surface(o)
    p = ProviderStatus('p', ProviderRole.SHADOW, 0, ProviderHealth.HEALTHY, {1: Qualification.QUALIFIED}, s, (), True)
    with pytest.raises(NoServingProvider):
        serving_provider([p], horizon=1, decision_universe=o.decision_universe())

def test_unauthorized_standby_cannot_silently_serve():
    o = official()
    s = surface(o)
    p = ProviderStatus('p', ProviderRole.STANDBY, 0, ProviderHealth.HEALTHY, {1: Qualification.QUALIFIED}, s, (), False)
    with pytest.raises(NoServingProvider):
        serving_provider([p], horizon=1, decision_universe=o.decision_universe())

def test_stale_surface_unqualified():
    o = official()
    s = surface(o, generated='2026-08-20T00:00:00Z')
    q = qualify_surface(s, o, decision_universe=o.decision_universe(), requested_horizons=(1,), max_age_hours=18, now=datetime(2026, 8, 28, 12, tzinfo=timezone.utc))
    assert q.operational == Qualification.UNQUALIFIED
    assert q.health == ProviderHealth.STALE

def test_snapshot_detects_post_freeze_mutation(tmp_path: Path):
    b = SnapshotBuilder()
    b.add_json('x.json', {'a': 1})
    snap = b.freeze(tmp_path)
    (snap.root / 'x.json').write_text('{"a":2}')
    with pytest.raises(RuntimeError):
        open_frozen_snapshot(snap.root)

def test_snapshot_rejects_new_input_after_freeze(tmp_path: Path):
    b = SnapshotBuilder()
    b.add_json('x.json', {'a': 1})
    b.freeze(tmp_path)
    with pytest.raises(RuntimeError):
        b.add_json('y.json', {})

def test_orphaned_intent_detected_after_grace():
    now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    rels = [{'tag_name': 'apex-v2/intent/2026-2027/run1', 'created_at': (now - timedelta(hours=5)).isoformat()}, {'tag_name': 'apex-v2/intent/2026-2027/run2', 'created_at': now.isoformat()}, {'tag_name': 'apex-v2/final/2026-2027/run3', 'created_at': now.isoformat()}]
    a = audit_release_tags(rels, now=now)
    assert a.missing_finals == ('apex-v2/intent/2026-2027/run1',)
    assert a.in_progress == ('apex-v2/intent/2026-2027/run2',)

def test_fpl_selling_price_rounds_down_half_profit():
    assert calculate_selling_price(50, 55) == 52
    assert calculate_selling_price(50, 56) == 53
    assert calculate_selling_price(50, 47) == 47

def test_existing_team_value_over_100m_can_still_be_structurally_legal():
    o = official()
    ids = []
    by = {(p.team_id, p.position): [] for p in o.players}
    for p in o.players:
        by[p.team_id, p.position].append(p.element_id)
    ids = [by[1, Position.GK][0], by[2, Position.GK][0]] + [by[t, Position.DEF][0] for t in range(1, 6)] + [by[t, Position.MID][0] for t in range(1, 6)] + [by[t, Position.FWD][0] for t in range(3, 6)]
    players = {pid: OfficialPlayer(p.element_id, p.web_name, p.team_id, p.position, 80, p.status, p.can_transact) for pid, p in o.player_map().items()}
    assert validate_squad(players, ids, budget_tenths=None) == ()
    assert validate_squad(players, ids, budget_tenths=1000)
