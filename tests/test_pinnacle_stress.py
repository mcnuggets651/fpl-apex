import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.squad import optimise_squad


def _player(pid, pos, team, price=4.5, gw1=2.0, horizon=8.0):
    return {
        "player_id": pid,
        "web_name": f"P{pid}",
        "team": team,
        "team_name": f"T{team}",
        "position": pos,
        "price": price,
        "gw1_xp": gw1,
        "horizon_xp": horizon,
        "appearance_probability": 0.95,
        "projection_confidence": 0.8,
    }


def _base_pool():
    rows = []
    pid = 1
    # Exact non-DEF requirements so the only meaningful squad decision can be
    # isolated inside the defender pool below.
    for pos, count, price in [("GK", 2, 4.0), ("MID", 5, 5.0), ("FWD", 3, 5.0)]:
        for j in range(count):
            rows.append(_player(pid, pos, team=(pid % 8) + 1, price=price, gw1=3.0, horizon=12.0))
            pid += 1

    # Four dominant defenders are automatic. The fifth slot is an adversarial
    # choice between A (GW1 spike) and B (superior multi-GW rotation value).
    for j in range(4):
        rows.append(_player(pid, "DEF", team=(pid % 8) + 1, price=4.0, gw1=7.0, horizon=28.0))
        pid += 1
    a = pid
    rows.append(_player(a, "DEF", team=7, price=4.0, gw1=10.0, horizon=10.0))
    pid += 1
    b = pid
    rows.append(_player(b, "DEF", team=8, price=4.0, gw1=6.0, horizon=24.0))
    return pd.DataFrame(rows), a, b


def _projection_table(players, a, b):
    rows = []
    for pid in players.player_id:
        for gw in [1, 2, 3, 4]:
            if pid == a:
                xp = 10.0 if gw == 1 else 0.0
            elif pid == b:
                xp = 6.0
            else:
                xp = 3.0
            rows.append({"player_id": int(pid), "gw": gw, "risk_adjusted_xp": xp})
    return pd.DataFrame(rows)


def test_full_horizon_optimizer_beats_gw1_weighting_on_adversarial_rotation_case():
    players, spike_defender, horizon_defender = _base_pool()
    projections = _projection_table(players, spike_defender, horizon_defender)

    legacy = optimise_squad(players, budget=100.0)
    pinnacle = optimise_initial_horizon(
        players,
        projections,
        [1, 2, 3, 4],
        budget=100.0,
        decay=1.0,
        bench_weight=0.0,
    )

    assert legacy.status == "Optimal"
    assert pinnacle.status == "Optimal"
    # This is the failure mode the stress test is designed to expose: a large
    # one-week spike can beat a clearly superior season-opening rotation asset in
    # the legacy aggregate heuristic.
    assert spike_defender in set(legacy.squad.player_id)
    assert horizon_defender not in set(legacy.squad.player_id)
    assert horizon_defender in set(pinnacle.squad.player_id)
    assert spike_defender not in set(pinnacle.squad.player_id)


def test_horizon_optimizer_respects_all_fpl_squad_and_xi_constraints():
    players, a, b = _base_pool()
    projections = _projection_table(players, a, b)
    sol = optimise_initial_horizon(players, projections, [1, 2, 3, 4], budget=100.0)

    assert sol.status == "Optimal"
    assert len(sol.squad) == 15
    assert len(sol.xi) == 11
    assert len(sol.captain) == 1
    assert len(sol.vice_captain) == 1
    assert float(sol.squad.price.sum()) <= 100.0 + 1e-8
    assert sol.squad.groupby("team_name").size().max() <= 3
    assert sol.squad.position.value_counts().to_dict() == {
        "MID": 5,
        "DEF": 5,
        "FWD": 3,
        "GK": 2,
    }
    xi_counts = sol.xi.position.value_counts().to_dict()
    assert xi_counts.get("GK", 0) == 1
    assert 3 <= xi_counts.get("DEF", 0) <= 5
    assert 2 <= xi_counts.get("MID", 0) <= 5
    assert 1 <= xi_counts.get("FWD", 0) <= 3


def test_locked_and_banned_players_survive_horizon_optimisation_contract():
    players, a, b = _base_pool()
    projections = _projection_table(players, a, b)
    sol = optimise_initial_horizon(
        players,
        projections,
        [1, 2, 3, 4],
        budget=100.0,
        locked={a},
        banned={b},
    )
    assert sol.status == "Optimal"
    ids = set(sol.squad.player_id)
    assert a in ids
    assert b not in ids
