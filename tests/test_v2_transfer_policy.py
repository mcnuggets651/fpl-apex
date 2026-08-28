from apex.domain.models import *
from apex.decision.transfers import optimise_transfer_horizon

def setup():
    players = []
    pid = 1
    specs = [(Position.GK, 2), (Position.DEF, 5), (Position.MID, 5), (Position.FWD, 3)]
    for pos, count in specs:
        for i in range(count):
            players.append(OfficialPlayer(pid, f'P{pid}', 1 + i % 5, pos, 50, 'a', True))
            pid += 1
    for pos in Position:
        for i in range(4):
            players.append(OfficialPlayer(pid, f'A{pid}', 6 + i % 2, pos, 50, 'a', True))
            pid += 1
    o = OfficialSnapshot(1, '2026-2027', '2026-08-28T10:00:00Z', 's', tuple(players), (), {2: '2026-08-29T10:00:00Z', 3: '2026-09-05T10:00:00Z'})
    squad = tuple(range(1, 16))
    team = TeamState(1, 1, 1, squad, 0, 1, {p: 50 for p in squad}, {p: 50 for p in squad}, None, True)
    rows = []
    for p in players:
        rows.append(ProjectionRow(p.element_id, 2, 1, 10 if p.element_id > 15 else 3))
        rows.append(ProjectionRow(p.element_id, 3, 2, 10 if p.element_id > 15 else 3))
    surf = ProductionProjectionSurface(1, 'p', 'v', '2026-08-28T10:00:00Z', o.season, o.source_hash, '2026-2027', (1, 2), tuple(rows))
    return (o, team, surf)

def test_h1_only_withholds_discretionary_transfer():
    o, t, s = setup()
    r = optimise_transfer_horizon(o, s, t, max_horizon=1)
    assert r.status == 'WITHHELD_H1_ONLY'
    assert r.decision.transfers_in == ()


def test_h2_uses_transfer_when_multiweek_ev_beats_hit_and_cash():
    o, team, surface = setup()
    result = optimise_transfer_horizon(o, surface, team, max_horizon=2)
    assert result.status == "OPTIMAL"
    assert result.decision is not None
    assert len(result.weeks) == 2
    assert len(result.decision.transfers_in) == len(result.decision.transfers_out)
