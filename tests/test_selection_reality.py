import pandas as pd

from apex_fpl.services.selection_reality import audit_selected_squad_reality


def _players():
    return pd.DataFrame(
        [
            {"player_id": 1, "web_name": "Starter", "expected_minutes": 82.0, "appearance_probability": 0.96, "start_probability": 0.90},
            {"player_id": 2, "web_name": "BenchOne", "expected_minutes": 45.0, "appearance_probability": 0.82, "start_probability": 0.55},
            {"player_id": 3, "web_name": "BenchTwo", "expected_minutes": 28.0, "appearance_probability": 0.68, "start_probability": 0.42},
            {"player_id": 4, "web_name": "BenchThree", "expected_minutes": 9.0, "appearance_probability": 0.25, "start_probability": 0.10},
        ]
    )


def test_high_confidence_requires_two_playable_outfield_bench_players():
    result = audit_selected_squad_reality(_players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4])
    assert result.ready_for_high_confidence is True
    assert result.playable_outfield_bench == 2
    assert result.blockers == ()


def test_academy_or_u21_selected_bench_player_blocks_high_confidence():
    hierarchy = pd.DataFrame([{"player_id": 2, "hierarchy_status": "u21"}])
    result = audit_selected_squad_reality(_players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4], hierarchy_evidence=hierarchy)
    assert result.ready_for_high_confidence is False
    assert any("BenchOne" in blocker and "u21" in blocker for blocker in result.blockers)


def test_hierarchy_evidence_can_resolve_by_name_without_guessing_fpl_id():
    hierarchy = pd.DataFrame([{"web_name": "BenchOne", "hierarchy_status": "fringe"}])
    result = audit_selected_squad_reality(_players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4], hierarchy_evidence=hierarchy)
    assert result.ready_for_high_confidence is False
    assert any("BenchOne" in blocker and "fringe" in blocker for blocker in result.blockers)


def test_two_specialists_agreeing_against_selected_player_blocks_until_resolved():
    specialist = pd.DataFrame([{"player_id": 1, "review_priority": "high", "review_reason": "two specialist predicted-XI sources expect a benching"}])
    result = audit_selected_squad_reality(_players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4], specialist_report=specialist)
    assert result.ready_for_high_confidence is False
    assert any("Starter" in blocker for blocker in result.blockers)


def test_high_transfer_risk_blocks_selected_player_without_mutating_projection():
    players = _players()
    before = players.copy(deep=True)
    transfer = pd.DataFrame([{"player_id": 1, "review_priority": "high", "review_reason": "agreement/medical-level transfer report requires official resolution"}])
    result = audit_selected_squad_reality(players, selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4], transfer_report=transfer)
    assert result.ready_for_high_confidence is False
    pd.testing.assert_frame_equal(players, before)


def test_first_bench_must_be_more_reliable_than_generic_playable_threshold():
    players = _players()
    players.loc[players.player_id.eq(2), "appearance_probability"] = 0.65
    result = audit_selected_squad_reality(players, selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4])
    assert result.ready_for_high_confidence is False
    assert any("first outfield bench" in blocker for blocker in result.blockers)


def test_neave_shape_cannot_be_published_as_first_bench():
    players = _players()
    players.loc[players.player_id.eq(2), ["web_name", "expected_minutes", "appearance_probability", "start_probability"]] = ["Neave", 13.269, 0.0, 0.1484]
    result = audit_selected_squad_reality(players, selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4])
    assert result.ready_for_high_confidence is False
    assert any("Neave" in blocker and "expected minutes 13.3" in blocker for blocker in result.blockers)


def test_production_evidence_mode_records_missing_manual_corroboration_as_warning_not_blocker():
    result = audit_selected_squad_reality(
        _players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4], require_current_evidence=True
    )
    assert result.ready_for_high_confidence is True
    assert result.blockers == ()
    assert any("manual squad-hierarchy corroboration" in row for row in result.warnings)
    assert any("0/2 governed specialist sources" in row for row in result.warnings)
    assert any("manual transfer-state corroboration" in row for row in result.warnings)


def test_production_evidence_mode_passes_cleanly_with_complete_selected_coverage():
    hierarchy = pd.DataFrame([{"player_id": pid, "hierarchy_status": "senior_starter"} for pid in range(1, 5)])
    specialist = pd.DataFrame([{"player_id": pid, "specialist_source_count": 2, "review_priority": "none", "review_reason": ""} for pid in range(1, 5)])
    transfer = pd.DataFrame([{"player_id": pid, "review_priority": "none", "review_reason": ""} for pid in range(1, 5)])
    result = audit_selected_squad_reality(
        _players(), selected_ids={1, 2, 3, 4}, xi_ids={1}, bench_ids=[2, 3, 4],
        hierarchy_evidence=hierarchy, specialist_report=specialist, transfer_report=transfer, require_current_evidence=True,
    )
    assert result.ready_for_high_confidence is True
    assert result.blockers == ()
    assert result.warnings == ()
