import pandas as pd

from apex_fpl.optimisation.transfers import _next_ft, optimise_transfer_plan


def _pool():
    rows = []
    pid = 1
    for team in range(1, 9):
        for pos, count in [("GK", 1), ("DEF", 2), ("MID", 2), ("FWD", 1)]:
            for j in range(count):
                rows.append({
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team_name": f"T{team}",
                    "team": team,
                    "position": pos,
                    "price": 4.0 + (pid % 4) * 0.5,
                    "horizon_xp": 20 + pid / 10,
                })
                pid += 1
    return pd.DataFrame(rows)


def test_ft_transition_rule():
    assert _next_ft(1, 0) == 2
    assert _next_ft(5, 0) == 5
    assert _next_ft(3, 1) == 3
    assert _next_ft(3, 3) == 1
    assert _next_ft(2, 4) == 1


def test_multiweek_transfer_plan_is_legal():
    players = _pool()
    # Construct a legal but deliberately weak initial squad.
    current = set()
    for pos, need in {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}.items():
        for _, r in players[players.position == pos].head(need).iterrows():
            current.add(int(r.player_id))
    gws = [1, 2]
    proj = pd.DataFrame([
        {"player_id": int(r.player_id), "gw": gw, "risk_adjusted_xp": 2.0 + r.player_id / 20 + gw / 10}
        for _, r in players.iterrows() for gw in gws
    ])
    plan = optimise_transfer_plan(players, proj, gws, current, bank=20.0, free_transfers=2, candidate_limit=60)
    assert plan.status == "Optimal"
    assert len(plan.weeks) == 2
    for week in plan.weeks:
        squad = pd.DataFrame(week["squad"])
        xi = pd.DataFrame(week["xi"])
        assert len(squad) == 15
        assert len(xi) == 11
        assert (squad.groupby("team_name").size() <= 3).all()
        assert squad.position.value_counts().to_dict() == {"MID": 5, "DEF": 5, "FWD": 3, "GK": 2}
