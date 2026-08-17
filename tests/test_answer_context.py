from datetime import datetime, timezone

from apex_fpl.services.answer_context import build_answer_context, route_question


NOW = datetime(2026, 8, 11, 8, tzinfo=timezone.utc)


def _players() -> list[dict]:
    rows = []
    for player_id in range(1, 16):
        rows.append(
            {
                "player_id": player_id,
                "web_name": f"P{player_id}",
                "expected_minutes": 72,
                "start_probability": 0.8,
                "projection_confidence": 0.7,
                "tactical_role": "attacking role",
                "tactical_role_source": "statistical_inference",
                "horizon_xp": 30,
            }
        )
    return rows


def _payloads():
    snapshot = {
        "snapshot_id": "snapshot",
        "retrieved_at": "2026-08-11T07:00:00+00:00",
        "bootstrap_sha256": "a",
        "fixtures_sha256": "b",
    }
    players = _players()
    evidence = {
        "contract": "apex-player-evidence-v2",
        "coverage": {
            "ready": True,
            "selected_players": 15,
            "selected_players_with_current_evidence": 1,
            "relevant_evidence_rows": 1,
            "captain_id": 1,
            "captain_has_current_evidence": True,
            "captain_has_decision_grade_evidence": True,
            "captain_evidence_eligible": True,
            "selected_xi_ineligible_ids": [],
        },
        "dossiers": [
            {
                "player_id": row["player_id"],
                "has_current_decision_evidence": row["player_id"] == 1,
                "has_decision_grade_evidence": row["player_id"] == 1,
                "current_evidence_count": 1 if row["player_id"] == 1 else 0,
                "evidence": [],
            }
            for row in players
        ],
    }
    canonical = {
        "contract": "apex-strategy-recommendation-v3",
        "strategy_stage": "final_validated",
        "ready_to_act": True,
        "blockers": [],
        "official_snapshot": snapshot,
        "decision_bundle_id": "bundle-a",
        "all_player_truth": {
            "contract": "apex-player-truth-v1",
            "ready": True,
            "player_count": 587,
            "hard_fact_coverage": 1.0,
            "canonical_projection_pair_coverage": 1.0,
            "airsenal_projection_pair_coverage": 1.0,
            "warnings": [],
        },
        "final_selected_player_evidence": evidence,
        "recommendation": {
            "selector": "adaptive_gw1_launch_with_transfer_option_value",
            "squad": players,
            "xi": players[:11],
            "captain": "P1",
            "captain_id": 1,
            "vice_captain": "P2",
            "vice_captain_id": 2,
        },
    }
    pinnacle = {
        "contract": "pinnacle-v1",
        "pinnacle_ready": True,
        "official_snapshot": snapshot,
        "decision_bundle_id": "bundle-a",
        "sources": [
            {
                "name": "news_feeds",
                "ok": True,
                "configured": True,
                "checked_at": "2026-08-11T07:30:00+00:00",
                "version": "news-1",
            }
        ],
        "robust_cvar_scenarios": {"unrestricted": {"status": "Optimal"}},
        "selection_regret": [{"player_id": 1, "regret": 1.2}],
        "solver_parity": {
            "comparison_surface": "pinnacle_ev",
            "decision_bundle_id": "bundle-a",
            "official_snapshot": {"bootstrap_sha256": "a", "fixtures_sha256": "b"},
        },
        "weekly_strategy": {"status": "Optimal"},
        "pinnacle_gate": {"warnings": []},
        "data_quality": {"warnings": []},
    }
    return canonical, pinnacle


def test_complete_final_context_is_only_green_answer_contract():
    canonical, pinnacle = _payloads()
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is True
    assert context["only_input_for_apex_answers"] is True
    assert context["production_result"] is not None
    assert context["decision_bundle_id"] == "bundle-a"
    reason = context["selected_player_reasons"][0]
    assert reason["selector"] == "adaptive_gw1_launch_with_transfer_option_value"
    assert reason["selection_regret"] is None
    assert reason["alternative"] is None
    assert "GW1-first" in reason["reason"]
    surfaces = context["diagnostics"]["captain_surfaces"]
    assert surfaces["production"]["authority"] is True
    assert surfaces["production"]["captain_id"] == 1
    assert surfaces["cvar_diagnostic"]["authority"] is False
    assert "Only canonical_final_strategy" in surfaces["interpretation"]
    assert context["news_role_evidence"]["coverage"]["selected_players"] == 15


def test_exact_horizon_diagnostic_does_not_own_final_player_reasons():
    canonical, pinnacle = _payloads()
    pinnacle["authoritative_decision"] = {
        "objective": 100.0,
        "solution": {"squad": [{"player_id": 1}, {"player_id": 2}]},
        "shortlist": {
            "candidates": [
                {
                    "squad_player_ids": [2, 3],
                    "squad_player_names": ["P2", "Other"],
                    "exact_objective": 99.8,
                }
            ]
        },
        "equivalence": {"unique_optimum_proven": False},
    }
    context = build_answer_context(canonical, pinnacle, now=NOW)
    reason = context["selected_player_reasons"][0]

    assert context["safe_to_act"] is True
    assert reason["selection_regret"] is None
    assert reason["alternative"] is None
    assert context["diagnostics"]["static_exact_horizon_is_authoritative"] is False


def test_stale_or_missing_diagnostics_withhold_production_result():
    canonical, pinnacle = _payloads()
    canonical["official_snapshot"]["retrieved_at"] = "2026-08-09T07:00:00+00:00"
    pinnacle["official_snapshot"]["retrieved_at"] = "2026-08-09T07:00:00+00:00"
    pinnacle["solver_parity"] = None
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("stale" in blocker for blocker in context["blockers"])
    assert any("solver parity" in blocker for blocker in context["blockers"])


def test_incomplete_all_player_truth_blocks_answer_contract():
    canonical, pinnacle = _payloads()
    canonical["all_player_truth"]["airsenal_projection_pair_coverage"] = 0.99
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert any("all-player truth coverage" in row for row in context["blockers"])


def test_final_evidence_must_match_the_actual_canonical_15():
    canonical, pinnacle = _payloads()
    canonical["final_selected_player_evidence"]["dossiers"] = canonical[
        "final_selected_player_evidence"
    ]["dossiers"][:-1]
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("full squad" in row or "identities" in row for row in context["blockers"])


def test_non_final_selector_is_never_actionable():
    canonical, pinnacle = _payloads()
    canonical["recommendation"]["selector"] = "exact_horizon_maximum_ev"
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert any("allowed final strategy selector" in row for row in context["blockers"])


def test_router_requires_the_correct_artifact():
    assert route_question("Will Foden start?").required_artifact == "player_evidence_dossier"
    assert route_question("Foden vs Saka").required_artifact == "same_snapshot_player_dossier"
    assert route_question("What transfer should I make?").mode == "transfer"
    assert route_question("Give me the best team").mode == "canonical_team"
    assert route_question("Project status on GitHub").mode == "project_status"


def test_diagnostic_and_inferred_role_warnings_reach_answer_contract():
    canonical, pinnacle = _payloads()
    pinnacle["pinnacle_gate"] = {"warnings": ["captain stability is provisional"]}
    pinnacle["data_quality"] = {"warnings": ["team strength fallback active"]}
    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is True
    assert any("captain stability" in warning for warning in context["warnings"])
    assert any("team strength fallback" in warning for warning in context["warnings"])
    assert any("statistical forecasts" in warning for warning in context["warnings"])
