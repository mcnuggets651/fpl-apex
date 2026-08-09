from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload


def _scenario():
    return {
        "status": "Optimal",
        "squad": [
            {
                "player_id": i,
                "web_name": f"P{i}",
                "expected_minutes": 80,
                "start_probability": 0.90,
                "appearance_probability": 0.97,
                "projection_confidence": 0.80,
            }
            for i in range(15)
        ],
        "xi": [{"player_id": i} for i in range(11)],
    }


def _payload():
    scenarios = {name: _scenario() for name in ("unrestricted", "haaland", "no-haaland")}
    mechanics = {
        name: {
            "captain_id": 1,
            "vice_captain_id": 2,
            "outfield_bench_order": [12, 13, 14],
        }
        for name in scenarios
    }
    return {
        "safe_to_act": True,
        "full_apex_ready": True,
        "gameweeks": [1, 2, 3, 4, 5, 6, 7, 8],
        "data_quality": {"ready": True, "blockers": [], "warnings": [], "checks": []},
        "official_snapshot": {
            "snapshot_id": "test",
            "retrieved_at": "2026-08-07T09:00:00+00:00",
            "bootstrap_sha256": "a" * 64,
            "fixtures_sha256": "b" * 64,
        },
        "sources": [
            {"name": name, "ok": True, "configured": True}
            for name in (
                "official_fpl",
                "fpl_core_playerstats",
                "fixture_model",
                "airsenal",
                "news_feeds",
                "fpl_core_previous_season",
            )
        ],
        "decision_layer": {
            "stochastic_covariance_layer": True,
            "stochastic_scenarios": 256,
            "exact_gw_mechanics": True,
            "captain_eligibility_enforced_in_all_solves": True,
            "receding_horizon_transfers": True,
            "empirical_decision_frequency": True,
            "decision_frequency_solves": 24,
            "fixed_xi_captain_frequency": True,
            "fixed_xi_captain_frequency_solves": 24,
            "covariance_coefficients_walk_forward_calibrated": False,
        },
        "deterministic_scenarios": scenarios,
        "robust_cvar_scenarios": {name: _scenario() for name in scenarios},
        "gw1_mechanics": mechanics,
        "selection_regret": [{"player_id": 1, "objective_regret": 3.0}],
        "decision_frequencies": [
            {
                "player_id": 1,
                "squad_frequency": 1.0,
                "xi_frequency": 1.0,
                "captain_frequency": 0.80,
                "vice_captain_frequency": 0.10,
            }
        ],
        "fixed_xi_captain_frequencies": [
            {
                "player_id": 1,
                "captain_frequency": 0.80,
                "vice_captain_frequency": 0.10,
            }
        ],
        "robustness_comparison": {
            "unrestricted": {
                "squad_overlap": 14,
                "xi_overlap": 10,
                "captain_agrees": True,
            }
        },
        "personal_team": None,
        "initial_squad_contingencies": {
            "status": "Optimal",
            "future_moves_are_contingent": True,
            "weeks": [],
        },
        "initial_chip_policy": {"status": "hold", "recommended_chip": None},
        "solver_parity": {"status": "ok"},
    }


def test_complete_pinnacle_payload_is_ready_with_calibration_warning():
    result = evaluate_pinnacle_payload(_payload())
    assert result.ready
    assert not result.blockers
    assert any("covariance" in warning for warning in result.warnings)


def test_missing_exact_mechanics_blocks_pinnacle():
    payload = _payload()
    payload["decision_layer"]["exact_gw_mechanics"] = False
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("mechanics" in blocker for blocker in result.blockers)


def test_personal_team_requires_weekly_strategy_and_chip_window():
    payload = _payload()
    payload["personal_team"] = {"team_state": {"published_gw": 1}}
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("weekly strategy" in blocker for blocker in result.blockers)
    assert any("chip-window" in blocker for blocker in result.blockers)


def test_pre_gw1_requires_contingency_route_and_conservative_chip_policy():
    payload = _payload()
    payload["initial_squad_contingencies"] = None
    payload["initial_chip_policy"] = None
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("contingency route" in blocker for blocker in result.blockers)
    assert any("chip policy" in blocker for blocker in result.blockers)


def test_unsupported_low_start_low_confidence_captain_blocks_pinnacle():
    payload = _payload()
    captain = payload["deterministic_scenarios"]["unrestricted"]["squad"][1]
    captain.update(
        {
            "web_name": "Unsupported",
            "expected_minutes": 46.2,
            "start_probability": 0.20,
            "appearance_probability": 0.616,
            "projection_confidence": 0.165,
        }
    )
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("captain Unsupported" in blocker for blocker in result.blockers)
    assert any("start probability" in blocker for blocker in result.blockers)
    assert any("projection confidence" in blocker for blocker in result.blockers)


def test_low_fixed_xi_captain_frequency_blocks_publication():
    payload = _payload()
    payload["fixed_xi_captain_frequencies"][0]["captain_frequency"] = 0.49
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("fixed-XI uncertainty re-solves" in blocker for blocker in result.blockers)


def test_whole_decision_frequency_does_not_replace_fixed_xi_captain_audit():
    payload = _payload()
    payload["decision_frequencies"][0]["captain_frequency"] = 0.10
    payload["decision_frequencies"][0]["xi_frequency"] = 0.50
    result = evaluate_pinnacle_payload(payload)
    assert result.ready


def test_missing_fixed_xi_captain_audit_blocks_publication():
    payload = _payload()
    payload["fixed_xi_captain_frequencies"] = []
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("fixed-XI captain-frequency audit" in blocker for blocker in result.blockers)


def test_robust_captain_disagreement_blocks_publication():
    payload = _payload()
    payload["robustness_comparison"]["unrestricted"]["captain_agrees"] = False
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("captains disagree" in blocker for blocker in result.blockers)


def test_pre_gw1_prior_season_failure_blocks_publication():
    payload = _payload()
    previous = next(
        row for row in payload["sources"] if row["name"] == "fpl_core_previous_season"
    )
    previous["ok"] = False
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("prior-season evidence" in blocker for blocker in result.blockers)


def test_failed_embedded_solver_parity_blocks_publication():
    payload = _payload()
    payload["solver_parity"] = {
        "comparison_surface": "pinnacle_ev",
        "squad_overlap": 11,
        "captain_agrees": False,
    }
    result = evaluate_pinnacle_payload(payload)
    assert not result.ready
    assert any("solver squad parity" in blocker for blocker in result.blockers)
    assert any("solver captain parity" in blocker for blocker in result.blockers)
