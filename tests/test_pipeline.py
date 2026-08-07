import pandas as pd

from apex_fpl.config import Settings
from apex_fpl.data.official import OfficialSnapshot, OfficialFPLClient
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.services.pipeline import run_pipeline
from apex_fpl.services.pipeline import _decision_gameweeks


def _snapshot():
    teams = pd.DataFrame([
        {
            "id": t,
            "name": f"Team {t}",
            "strength": 1000 + t * 5,
            "strength_attack_home": 1000 + t * 5,
            "strength_defence_home": 1000 + t * 5,
            "strength_attack_away": 995 + t * 5,
            "strength_defence_away": 995 + t * 5,
        }
        for t in range(1, 9)
    ])
    rows = []
    pid = 1
    for t in range(1, 9):
        for pos_id, pos, count in [(1, "GK", 2), (2, "DEF", 3), (3, "MID", 3), (4, "FWD", 2)]:
            for j in range(count):
                name = "Haaland" if (t == 1 and pos == "FWD" and j == 0) else f"P{pid}"
                rows.append({
                    "id": pid,
                    "player_id": pid,
                    "web_name": name,
                    "first_name": name,
                    "second_name": name,
                    "team": t,
                    "team_name": f"Team {t}",
                    "element_type": pos_id,
                    "position": pos,
                    "now_cost": 45 + (pid % 30),
                    "price": (45 + (pid % 30)) / 10,
                    "status": "a",
                    "chance_of_playing_next_round": None,
                    "ep_next": 3.0 + (pid % 8) / 10,
                    "minutes": 0,
                    "starts": 0,
                    "expected_goals_per_90": 0.05 + (0.25 if pos in {"MID", "FWD"} else 0),
                    "expected_assists_per_90": 0.08 + (0.15 if pos in {"DEF", "MID"} else 0),
                    "defensive_contribution_per_90": 9 if pos == "DEF" else 6,
                })
                pid += 1
    players = pd.DataFrame(rows)
    events = pd.DataFrame([
        {"id": 1, "finished": False},
        {"id": 2, "finished": False},
    ])
    fixtures = []
    for gw in [1, 2]:
        for h, a in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            fixtures.append({"event": gw, "team_h": h, "team_a": a})
    return OfficialSnapshot(players, teams, pd.DataFrame(fixtures), events, {})


def test_pipeline_end_to_end_without_network(monkeypatch, tmp_path):
    snap = _snapshot()
    monkeypatch.setattr(OfficialFPLClient, "snapshot", lambda self, force=False: snap)
    monkeypatch.setattr(
        FPLCoreClient,
        "playerstats",
        lambda self, force=False: pd.DataFrame({"player_id": snap.players.player_id}),
    )
    monkeypatch.setattr(
        FPLCoreClient,
        "preseason_friendlies",
        lambda self, force=False: pd.DataFrame(),
    )
    # Keep this unit test network-free now that the live pipeline also consumes
    # FPL Core Elo fixture context.
    monkeypatch.setattr(
        FPLCoreClient,
        "fixture_elos",
        lambda self, gameweeks, force=False: pd.DataFrame(),
    )
    settings = Settings(
        horizon=2,
        cache_dir=tmp_path / "cache",
        snapshot_dir=tmp_path / "snapshots",
        report_dir=tmp_path / "reports",
        current_squad_path=tmp_path / "missing.csv",
        team_state_path=tmp_path / "missing.yaml",
        airsenal_csv=None,
        required_sources=[],
    )
    out = run_pipeline(settings, horizon=2, scenario="both", plan_transfers=False)
    assert set(out.scenarios) == {"unrestricted", "haaland", "no-haaland"}
    assert all(sol.status == "Optimal" for sol in out.scenarios.values())
    assert len(out.gameweeks) == 2
    assert (tmp_path / "reports" / "latest.json").exists()
    assert (tmp_path / "reports" / "sources.csv").exists()
    assert (tmp_path / "reports" / "scenario_comparison.json").exists()
    assert len(out.players) > 15


def test_decision_gameweeks_never_fabricates_past_season_end():
    events = pd.DataFrame(
        [
            {"id": 37, "finished": True},
            {"id": 38, "finished": False},
        ]
    )
    assert _decision_gameweeks(events, 8) == [38]
