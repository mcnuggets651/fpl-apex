import pandas as pd

from apex_fpl.services.selection_reality import audit_selected_squad_reality


def _players():
    return pd.DataFrame(
        [
            {"player_id": 1, "web_name": "Starter", "appearance_probability": 0.96, "start_probability": 0.90},
            {"player_id": 2, "web_name": "BenchOne", "appearance_probability": 0.82, "start_probability": 0.55},
            {"player_id": 3, "web_name": "BenchTwo", "appearance_probability": 0.68, "start_probability": 0.42},
            {"player_id": 4, "web_name": "BenchThree", "appearance_probability": 0.25, "start_probability": 0.10},
        ]
    )


def test_high_confidence_requires_two_playable_outfield_bench_players():
    result = audit_selected_squad_reality(
        _players(),
        selected_ids={1, 2, 3, 4},
        xi_ids={1},
        bench_ids=[2, 3, 4],
    )
    assert result.ready_for_high_confidence is True
    assert result.playable_outfield_bench == 2
    assert result.blockers == ()


def test_academy_or_u21_selected_bench_player_blocks_high_confidence():
    hierarchy = pd.DataFrame(
        [{"player_id": 2, "hierarchy_status": "u21"}]
    )
    result = audit_selected_squad_reality(
        _players(),
        selected_ids={1, 2, 3, 4},
        xi_ids={1},
        bench_ids=[2, 3, 4],
        hierarchy_evidence=hierarchy,
    )
    assert result.ready_for_high_confidence is False
    assert any("BenchOne" in blocker and "u21" in blocker for blocker in result.blockers)


def test_two_specialists_agreeing_against_selected_player_blocks_until_resolved():
    specialist = pd.DataFrame(
        [
            {
                "player_id": 1,
                "review_priority": "high",
                "review_reason": "two specialist predicted-XI sources expect a benching",
            }
        ]
    )
    result = audit_selected_squad_reality(
        _players(),
        selected_ids={1, 2, 3, 4},
        xi_ids={1},
        bench_ids=[2, 3, 4],
        specialist_report=specialist,
    )
    assert result.ready_for_high_confidence is False
    assert any("Starter" in blocker for blocker in result.blockers)


def test_high_transfer_risk_blocks_selected_player_without_mutating_projection():
    players = _players()
    before = players.copy(deep=True)
    transfer = pd.DataFrame(
        [
            {
                "player_id": 1,
                "review_priority": "high",
                "review_reason": "agreement/medical-level transfer report requires official resolution",
            }
        ]
    )
    result = audit_selected_squad_reality(
        players,
        selected_ids={1, 2, 3, 4},
        xi_ids={1},
        bench_ids=[2, 3, 4],
        transfer_report=transfer,
    )
    assert result.ready_for_high_confidence is False
    pd.testing.assert_frame_equal(players, before)


def test_first_bench_must_be_more_reliable_than_generic_playable_threshold():
    players = _players()
    players.loc[players.player_id.eq(2), "appearance_probability"] = 0.65
    result = audit_selected_squad_reality(
        players,
        selected_ids={1, 2, 3, 4},
        xi_ids={1},
        bench_ids=[2, 3, 4],
    )
    assert result.ready_for_high_confidence is False
    assert any("first outfield bench" in blocker for blocker in result.blockers)
