from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload


def _scenario():
    return {
        "status": "Optimal",
        "squad": [{"player_id": i} for i in range(15)],
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
        "official_snapshot": {
            "snapshot_id": "test",
            "retrieved_at": "2026-08-07T09:00:00+00:00",
            "bootstrap_sha256": "a" * 64,
            "fixtures_sha256": "b" * 64,
        },
        "sources": [
            {"name": name, "ok": True, "configured": True}
            for name in ("official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds")
        ],
        "decision_layer": {
            "stochastic_covariance_layer": True,
            "stochastic_scenarios": 256,
            "exact_gw_mechanics": True,
            "receding_horizon_transfers": True,
            "covariance_coefficients_walk_forward_calibrated": False,
        },
        "deterministic_scenarios": scenarios,
        "robust_cvar_scenarios": {name: _scenario() for name in scenarios},
        "gw1_mechanics": mechanics,
        "selection_regret": [{"player_id": 1, "objective_regret": 3.0}],
        "robustness_comparison": {"unrestricted": {"squad_overlap": 14}},
        "personal_team": None,
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
