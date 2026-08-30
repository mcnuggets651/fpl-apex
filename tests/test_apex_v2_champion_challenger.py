from apex.governance.tournament import (
    assess_promotion,
    build_model_neutral_decision_surface,
    disagreement_material,
    independent_challenger_consensus,
    paired_error_summaries,
)


def test_disagreement_requires_both_absolute_and_relative_thresholds():
    assert disagreement_material(4.0, 3.0) is True
    assert disagreement_material(7.0, 6.0) is False
    assert disagreement_material(9.0, 7.5) is False
    assert disagreement_material(2.0, 1.0) is True


def test_correlated_openfpl_lineage_counts_as_one_family():
    consensus = independent_challenger_consensus(
        "airsenal",
        {"airsenal": 7.0, "dastan": 4.0, "openfpl": 8.0, "pitchside": 10.0},
    )
    assert consensus == 8.0


def test_all_pairwise_scoring_preserves_same_observation_set_per_pair():
    result = paired_error_summaries(
        {
            "airsenal": {1: 5.0, 2: 4.0, 3: 8.0},
            "dastan": {1: 4.0, 2: 2.0},
            "pitchside": {1: 3.0, 3: 7.0},
        },
        decision_surface=frozenset({1, 2, 3}),
        actual={1: 3.0, 2: 5.0, 3: 7.0},
    )
    assert result["airsenal::dastan"]["paired_rows"] == 2
    assert result["airsenal::dastan"]["provider_a_absolute_error_sum"] == 3.0
    assert result["airsenal::dastan"]["provider_b_absolute_error_sum"] == 4.0
    assert result["dastan::pitchside"]["paired_rows"] == 1


def test_model_neutral_surface_is_union_across_models_and_manager_state():
    manager = {
        "team_state": {"squad_ids": [1, 2]},
        "system_decision": {
            "squad_ids": [1, 2],
            "xi_ids": [1],
            "bench_order": [2],
            "captain_id": 1,
            "vice_captain_id": 2,
            "transfers_in": [3],
            "transfers_out": [2],
        },
        "transfer_plan": [
            {"squad_ids": [1, 3], "transfers_in": [3], "transfers_out": [2]}
        ],
        "canonical_forecast": {
            "official": {
                "players": [
                    {"element_id": 1, "position": "MID", "can_transact": True},
                    {"element_id": 2, "position": "DEF", "can_transact": True},
                    {"element_id": 3, "position": "FWD", "can_transact": True},
                    {"element_id": 4, "position": "MID", "can_transact": True},
                    {"element_id": 5, "position": "DEF", "can_transact": True},
                    {"element_id": 6, "position": "FWD", "can_transact": False},
                ]
            }
        },
    }
    surfaces = {
        "providers/airsenal.json": {
            "provider_id": "airsenal",
            "rows": [
                {"element_id": 1, "gameweek": 3, "horizon": 1, "expected_points": 5.0},
                {"element_id": 4, "gameweek": 3, "horizon": 1, "expected_points": 7.0},
                {"element_id": 5, "gameweek": 3, "horizon": 1, "expected_points": 6.0},
                {"element_id": 6, "gameweek": 3, "horizon": 1, "expected_points": 9.0},
            ],
        },
        "providers/dastan.json": {
            "provider_id": "dastan",
            "rows": [
                {"element_id": 3, "gameweek": 3, "horizon": 1, "expected_points": 8.0},
                {"element_id": 4, "gameweek": 3, "horizon": 1, "expected_points": 4.0},
            ],
        },
    }
    result = build_model_neutral_decision_surface(
        manager,
        surfaces,
        gameweek=3,
        shadow_candidate_ids_by_provider={"pitchside": [99]},
    )
    assert {1, 2, 3, 4, 5, 6, 99}.issubset(result)


def test_promotion_requires_fixed_checkpoint_and_five_percent_edge():
    passed = assess_promotion(
        gameweek=8,
        completed_gameweeks=8,
        paired_observations=150,
        coverage=0.99,
        champion_expanding_mae=2.0,
        challenger_expanding_mae=1.88,
        champion_recent_mae=2.0,
        challenger_recent_mae=1.95,
        horizon_compatible=True,
        operationally_reliable=True,
        decision_quality_passed=True,
    )
    assert passed.eligible is True

    too_small = assess_promotion(
        gameweek=8,
        completed_gameweeks=8,
        paired_observations=150,
        coverage=0.99,
        champion_expanding_mae=2.0,
        challenger_expanding_mae=1.92,
        champion_recent_mae=2.0,
        challenger_recent_mae=1.95,
        horizon_compatible=True,
        operationally_reliable=True,
        decision_quality_passed=True,
    )
    assert too_small.eligible is False
    assert "expanding-window MAE improvement below 5%" in too_small.reasons

    wrong_week = assess_promotion(
        gameweek=9,
        completed_gameweeks=9,
        paired_observations=200,
        coverage=1.0,
        champion_expanding_mae=2.0,
        challenger_expanding_mae=1.8,
        champion_recent_mae=2.0,
        challenger_recent_mae=1.8,
        horizon_compatible=True,
        operationally_reliable=True,
        decision_quality_passed=True,
    )
    assert wrong_week.eligible is False
    assert "not a scheduled promotion review checkpoint" in wrong_week.reasons
