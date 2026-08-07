from apex_fpl.services.chips import chip_availability
from apex_fpl.services.team_state import TeamState


def test_opening_gameweek_disables_wildcard_and_free_hit_only():
    state = TeamState(squad=set(range(1, 16)))
    available = chip_availability(state, 1)
    assert not available["wildcard"]
    assert not available["free_hit"]
    assert available["bench_boost"]
    assert available["triple_captain"]


def test_chip_is_once_per_half_and_refreshes_after_gw19():
    state = TeamState(
        squad=set(range(1, 16)),
        chips_used=[
            {"event": 5, "name": "wildcard"},
            {"event": 8, "name": "bboost"},
            {"event": 12, "name": "3xc"},
        ],
    )
    first_half = chip_availability(state, 15)
    assert not first_half["wildcard"]
    assert not first_half["bench_boost"]
    assert not first_half["triple_captain"]
    assert first_half["free_hit"]

    second_half = chip_availability(state, 20)
    assert all(second_half.values())


def test_free_hit_cannot_be_played_in_consecutive_gameweeks():
    state = TeamState(
        squad=set(range(1, 16)),
        chips_used=[{"event": 19, "name": "freehit"}],
    )
    available = chip_availability(state, 20)
    assert not available["free_hit"]
    assert available["wildcard"]
