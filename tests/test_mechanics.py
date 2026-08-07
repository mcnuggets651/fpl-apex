import pandas as pd

from apex_fpl.optimisation.mechanics import (
    best_captain_vice,
    expected_autosub_points,
    optimise_gameweek_mechanics,
)


def _squad():
    rows = []
    pid = 1
    for pos, count in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for _ in range(count):
            rows.append({"player_id": pid, "position": pos, "web_name": f"P{pid}"})
            pid += 1
    return pd.DataFrame(rows)


def test_captain_vice_accounts_for_captain_no_show():
    xi = pd.DataFrame({"player_id": [1, 2, 3]})
    xp = {1: 8.0, 2: 7.8, 3: 7.0}
    appearance = {1: 0.55, 2: 0.99, 3: 0.99}
    captain, vice, bonus = best_captain_vice(xi, xp, appearance)
    # Player 1 still has the best direct xP, but a reliable high-xP vice materially
    # protects the no-show state.
    assert captain == 1
    assert vice == 2
    assert bonus > 8.0


def test_three_defender_formation_blocks_midfield_autosub():
    squad = _squad()
    # 3-4-3: GK1, DEF3-5, MID8-11, FWD13-15.
    xi_ids = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    xi = squad[squad.player_id.isin(xi_ids)].copy()
    bench = squad[~squad.player_id.isin(xi_ids)].copy()

    # Defender 3 is guaranteed to miss. First bench MID12 cannot replace him in a
    # submitted three-defender formation, while DEF6 can.
    appearance = {int(pid): 1.0 for pid in squad.player_id}
    appearance[3] = 0.0
    xp = {int(pid): 4.0 for pid in squad.player_id}
    xp[6] = 6.0
    xp[12] = 20.0

    value = expected_autosub_points(
        xi,
        bench,
        xp,
        appearance,
        outfield_order=(12, 6, 7),
    )
    assert abs(value - 6.0) < 1e-9


def test_mechanics_returns_legal_bench_order_and_pair():
    squad = _squad()
    xi_ids = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    xi = squad[squad.player_id.isin(xi_ids)].copy()
    xp = {int(pid): 3.0 + int(pid) / 10 for pid in squad.player_id}
    appearance = {int(pid): 0.9 for pid in squad.player_id}
    out = optimise_gameweek_mechanics(squad, xi, xp, appearance)
    assert out.captain_id in set(xi_ids)
    assert out.vice_captain_id in set(xi_ids)
    assert out.captain_id != out.vice_captain_id
    assert set(out.outfield_bench_order) == {6, 7, 12}
    assert out.bench_gk_id == 2
    assert out.expected_total_points > out.expected_xi_points


def test_mechanics_restricts_captain_and_vice_to_evidence_eligible_players():
    squad = _squad()
    xi_ids = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    xi = squad[squad.player_id.isin(xi_ids)].copy()
    xp = {int(pid): 3.0 for pid in squad.player_id}
    xp[13] = 30.0
    xp[14] = 20.0
    xp[8] = 8.0
    xp[9] = 7.0
    appearance = {int(pid): 0.95 for pid in squad.player_id}
    out = optimise_gameweek_mechanics(
        squad,
        xi,
        xp,
        appearance,
        captain_eligible={8, 9},
    )
    assert out.captain_id == 8
    assert out.vice_captain_id == 9
