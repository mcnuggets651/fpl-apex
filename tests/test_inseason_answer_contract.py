from datetime import datetime, timezone

from apex_fpl.services.answer_context import build_answer_context


NOW = datetime(2026, 8, 22, 10, tzinfo=timezone.utc)


def _payloads():
    snapshot = {
        "snapshot_id": "snapshot",
        "retrieved_at": "2026-08-22T09:30:00+00:00",
        "bootstrap_sha256": "bootstrap",
        "fixtures_sha256": "fixtures",
    }
    squad = [
        {
            "player_id": player_id,
            "web_name": f"P{player_id}",
            "team_name": "Club",
            "position": "MID",
            "price": 5.0,
            "current_gw_xp": 4.0,
        }
        for player_id in range(1, 16)
    ]
    dossiers = [
        {
            "player_id": player_id,
            "web_name": f"P{player_id}",
            "expected_minutes": 72.0,
            "start_probability": 0.8,
            "minutes_confidence": 0.8,
            "tactical_role": "attacking role",
            "role_source": "statistical_inference",
            "role_confidence": 0.7,
            "has_current_decision_evidence": player_id == 1,
            "has_decision_grade_evidence": player_id == 1,
            "current_evidence_count": 1 if player_id == 1 else 0,
            "evidence": [],
        }
        for player_id in range(1, 16)
    ]
    action_now = {
        "gw": 2,
        "squad": [dict(row) for row in squad],
        "xi": [dict(row) for row in squad[:11]],
        "captain": [dict(squad[0])],
        "vice_captain": [dict(squad[1])],
        "bench_gk": dict(squad[11]),
        "outfield_bench_order": [dict(row) for row in squad[12:15]],
        "exact_expected_total_points": 50.0,
        "mechanics_authority": "independent_exact_current_gameweek_rescore",
        "mechanics_reconciled": True,
    }
    canonical = {
        "contract": "apex-strategy-recommendation-v3",
        "strategy_stage": "final_validated",
        "ready_to_act": True,
        "blockers": [],
        "official_snapshot": snapshot,
        "decision_bundle_id": "bundle",
        "all_player_truth": {
            "contract": "apex-player-truth-v1",
            "ready": True,
            "player_count": 604,
            "hard_fact_coverage": 1.0,
            "canonical_projection_pair_coverage": 1.0,
            "airsenal_projection_pair_coverage": 1.0,
            "warnings": [
                "AIrsenal raw coverage is partial; all source-absent pairs use the governed fallback"
            ],
        },
        "final_selected_player_evidence": {
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
            "dossiers": dossiers,
        },
        "recommendation": {
            "selector": "receding_horizon_current_team_maximum_ev",
            "squad": squad,
            "xi": squad[:11],
            "captain": "P1",
            "captain_id": 1,
            "vice_captain": "P2",
            "vice_captain_id": 2,
            "bench_gk": "P12",
            "bench_gk_id": 12,
            "outfield_bench_order": ["P13", "P14", "P15"],
            "outfield_bench_order_ids": [13, 14, 15],
            "gw1_expected_total_with_mechanics": 50.0,
            "action_now": action_now,
        },
    }
    pinnacle = {
        "contract": "pinnacle-v1",
        "pinnacle_ready": True,
        "official_snapshot": snapshot,
        "decision_bundle_id": "bundle",
        "sources": [
            {
                "name": "news_feeds",
                "ok": True,
                "configured": True,
                "checked_at": "2026-08-22T09:35:00+00:00",
                "version": "news",
            }
        ],
        "robust_cvar_scenarios": {"unrestricted": {"status": "Optimal"}},
        "selection_regret": [{"player_id": 1, "regret": 0.1}],
        "solver_parity": {
            "comparison_surface": "pinnacle_ev",
            "decision_bundle_id": "bundle",
            "official_snapshot": {
                "bootstrap_sha256": "bootstrap",
                "fixtures_sha256": "fixtures",
            },
        },
        "weekly_strategy": {
            "status": "optimal",
            "state_transition_reconciled": True,
        },
        "pinnacle_gate": {"warnings": []},
        "data_quality": {"warnings": []},
    }
    return canonical, pinnacle


def test_compact_inseason_squad_uses_sealed_dossier_forecast_provenance():
    canonical, pinnacle = _payloads()

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is True
    assert context["production_result"] is not None
    first = context["selected_player_reasons"][0]
    assert first["expected_minutes"] == 72.0
    assert first["start_probability"] == 0.8
    assert first["tactical_role"] == "attacking role"
    assert first["role_source"] == "statistical_inference"
    assert not any("lacks expected-minutes" in row for row in context["blockers"])
    assert not any("lacks role provenance" in row for row in context["blockers"])


def test_compact_inseason_squad_still_fails_closed_when_dossier_forecast_is_missing():
    canonical, pinnacle = _payloads()
    canonical["final_selected_player_evidence"]["dossiers"][0]["expected_minutes"] = None

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("selected player lacks expected-minutes forecast: P1" == row for row in context["blockers"])


def test_compact_inseason_squad_still_fails_closed_when_dossier_role_provenance_is_missing():
    canonical, pinnacle = _payloads()
    canonical["final_selected_player_evidence"]["dossiers"][0]["role_source"] = None

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("selected player lacks role provenance: P1" == row for row in context["blockers"])


def test_receding_action_must_match_exact_rescored_captain():
    canonical, pinnacle = _payloads()
    canonical["recommendation"]["action_now"]["captain"] = [
        canonical["recommendation"]["squad"][1]
    ]

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("action_now captain" in row for row in context["blockers"])


def test_receding_action_requires_exact_mechanics_authority_marker():
    canonical, pinnacle = _payloads()
    canonical["recommendation"]["action_now"]["mechanics_reconciled"] = False
    canonical["recommendation"]["action_now"].pop("mechanics_authority")

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("not independently reconciled" in row for row in context["blockers"])
    assert any("mechanics authority" in row for row in context["blockers"])


def test_receding_action_must_match_exact_bench_order_and_points():
    canonical, pinnacle = _payloads()
    canonical["recommendation"]["action_now"]["outfield_bench_order"] = list(
        reversed(canonical["recommendation"]["action_now"]["outfield_bench_order"])
    )
    canonical["recommendation"]["action_now"]["exact_expected_total_points"] = 49.0

    context = build_answer_context(canonical, pinnacle, now=NOW)

    assert context["safe_to_act"] is False
    assert context["production_result"] is None
    assert any("outfield bench order" in row for row in context["blockers"])
    assert any("exact expected points" in row for row in context["blockers"])
