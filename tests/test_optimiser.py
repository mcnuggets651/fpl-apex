import pandas as pd

from apex_fpl.optimisation.squad import optimise_squad


def make_players():
    rows=[]
    pid=1
    prices={"GK":4.5,"DEF":4.5,"MID":6.0,"FWD":7.0}
    for pos,n in {"GK":5,"DEF":10,"MID":10,"FWD":7}.items():
        for j in range(n):
            rows.append({"player_id":pid,"web_name":f"P{pid}","team_name":f"T{j%10}","team":j%10+1,
                         "position":pos,"price":prices[pos],"gw1_xp":8-j*.1,"horizon_xp":40-j*.2})
            pid+=1
    return pd.DataFrame(rows)


def test_optimiser_returns_legal_squad():
    sol=optimise_squad(make_players(), budget=100)
    assert sol.status == "Optimal"
    assert len(sol.squad)==15
    assert len(sol.xi)==11
    assert len(sol.captain)==1
    assert len(sol.vice_captain)==1
    assert int(sol.vice_captain.iloc[0].player_id) != int(sol.captain.iloc[0].player_id)
    assert int(sol.vice_captain.iloc[0].player_id) in set(sol.xi.player_id)
    assert sol.squad.groupby("team_name").size().max() <= 3
    counts=sol.squad.groupby("position").size().to_dict()
    assert counts == {"DEF":5,"FWD":3,"GK":2,"MID":5}
