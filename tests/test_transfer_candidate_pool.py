import pandas as pd

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
