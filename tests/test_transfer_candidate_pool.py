import pandas as pd

import apex_fpl.optimisation.transfer_views as transfer_views
from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.optimisation.transfer_views import _pinnacle_candidate_ids


def test_candidate_pool_does_not_prune_low_absolute_xp_goalkeepers_or_enablers():
    rows = []
    projections = []
    pid = 1
    for pos, base_xp in [("GK", 2.0), ("DEF", 4.0), ("MID", 7.0), ("FWD", 8.0)]:
        for j in range(40):
            price = 4.0 + (j % 10) * 0.5
            xp = base_xp + j / 100
            rows.append(
                {
                    "player_id": pid,
                    "position": pos,
                    "price": price,
                    "team_name": f"T{pid % 20}",
                }
            )
            projections.append({"player_id": pid, "gw": 1, "xp": xp})
            pid += 1
    players = pd.DataFrame(rows)
    px = pd.DataFrame(projections)
    current = set(players.head(15).player_id.astype(int))

    ids = _pinnacle_candidate_ids(
        players,
        px,
        [1],
        current,
        projection_col="xp",
        target_size=40,
    )
    assert current.issubset(ids)
    # Global top-40 would contain almost no GK, but the positional layer must.
    gk_ids = set(players[players.position == "GK"].player_id.astype(int))
    assert len(ids & gk_ids) >= 18
    # The cheapest price band in every position must remain represented.
    for pos in ("GK", "DEF", "MID", "FWD"):
        cheap = set(
            players[(players.position == pos) & (players.price == 4.0)]
            .player_id.astype(int)
        )
        assert ids & cheap


def test_candidate_pool_preserves_required_ids_without_spending_discretionary_slots_on_unprojected_players():
    rows = []
    projections = []
    pid = 1
    unprojected: set[int] = set()
    for pos in ("GK", "DEF", "MID", "FWD"):
        for j in range(24):
            rows.append(
                {
                    "player_id": pid,
                    "position": pos,
                    "price": 4.0 + (j % 8) * 0.5,
                    "team_name": f"T{pid % 20}",
                }
            )
            if j < 20:
                projections.append({"player_id": pid, "gw": 2, "xp": 3.0 + j / 10})
            else:
                unprojected.add(pid)
            pid += 1
    players = pd.DataFrame(rows)
    px = pd.DataFrame(projections)
    required = {max(unprojected)}

    ids = _pinnacle_candidate_ids(
        players,
        px,
        [2],
        set(),
        projection_col="xp",
        target_size=40,
        required_ids=required,
    )

    projected_ids = set(px.player_id.astype(int))
    assert required.issubset(ids)
    assert (ids - required).issubset(projected_ids)


def _large_pool_fixture():
    rows = []
    projections = []
    pid = 1
    for pos in ("GK", "DEF", "MID", "FWD"):
        for j in range(50):
            rows.append(
                {
                    "player_id": pid,
                    "position": pos,
                    "price": 4.0 + (j % 8) * 0.5,
                    "team_name": f"T{pid % 20}",
                }
            )
            projections.append({"player_id": pid, "gw": 2, "xp": 2.0 + j / 10})
            pid += 1
    players = pd.DataFrame(rows)
    px = pd.DataFrame(projections)
    current = set(players.head(15).player_id.astype(int))
    return players, px, current


def test_transfer_view_retries_full_universe_after_bounded_nonoptimal(monkeypatch):
    players, px, current = _large_pool_fixture()
    calls: list[tuple[int, int]] = []

    def fake_optimise(players_arg, projections_arg, gameweeks, current_squad, **kwargs):
        calls.append((len(players_arg), int(kwargs["candidate_limit"])))
        if len(calls) == 1:
            return TransferPlan("Infeasible", float("nan"), [])
        return TransferPlan("Optimal", 123.0, [{"gw": 2}])

    monkeypatch.setattr(transfer_views, "optimise_transfer_plan", fake_optimise)

    plan = transfer_views.optimise_transfer_plan_view(
        players,
        px,
        [2],
        current,
        candidate_limit=40,
    )

    assert plan.status == "Optimal"
    assert len(calls) == 2
    assert calls[0][0] < len(players)
    assert calls[1][0] == len(players)
    assert calls[1][1] >= players.player_id.nunique()


def test_transfer_view_does_not_escalate_solver_limit_to_full_universe(monkeypatch):
    players, px, current = _large_pool_fixture()
    calls: list[int] = []

    def fake_optimise(players_arg, projections_arg, gameweeks, current_squad, **kwargs):
        calls.append(len(players_arg))
        return TransferPlan(
            "SolverLimit",
            120.0,
            [],
            solver_status_code=1,
            solver_message="Time limit reached",
            objective_upper_bound=125.0,
            mip_gap=0.04,
        )

    monkeypatch.setattr(transfer_views, "optimise_transfer_plan", fake_optimise)

    plan = transfer_views.optimise_transfer_plan_view(
        players,
        px,
        [2],
        current,
        candidate_limit=40,
    )

    assert plan.status == "SolverLimit"
    assert len(calls) == 1
    assert calls[0] < len(players)
