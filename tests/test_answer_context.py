from datetime import datetime, timezone

from apex_fpl.services.answer_context import build_answer_context, route_question


NOW = datetime(2026, 8, 11, 8, tzinfo=timezone.utc)


def _payloads():
    snapshot = {
        "snapshot_id": "snapshot",
        "retrieved_at": "2026-08-11T07:00:00+00:00",
        "bootstrap_sha256": "a",
        "fixtures_sha256": "b",
    }
    player = {
        "player_id": 1,
        "web_name": "Foden",
        "expected_minutes": 72,
        "start_probability": 0.8,
        "projection_confidence": 0.7,
        "tactical_role": "advanced midfielder / winger",
        "tactical_role_source": "official_manager",
        "horizon_xp": 30,
    }
    canonical = {
        "contract": "canonical-v1",
        "ready_to_act": True,
        "blockers": [],
        "official_snapshot": snapshot,
        "decision_bundle_id": "bundle-a",
        "recommendation": {"squad": [player]},
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
        "selection_regret": [{"player_id": 1, "regret": 1.2, "alternative_name": "Saka"}],
        "solver_parity": {
            "comparison_surface": "pinnacle_ev",
            "decision_bundle_id": "bundle-a",
            "official_snapshot": {"bootstrap_sha256": "a", "fixtures_sha256": "b"},
        },
        "weekly_strategy": {"status": "Optimal"},
    }
    return canonical, pinnacle


def test_complete_context_is_only_green_answer_contract():
    canonical, pinnacle = _payloads()
    context = build_answer_context(canonical, pinnacle, now=NOW)
    assert context["safe_to_act"] is True
    assert context["only_input_for_apex_answers"] is True
    assert context["production_result"] is not None
    assert context["decision_bundle_id"] == "bundle-a"
    assert context["selected_player_reasons"][0]["alternative"] == "Saka"
    surfaces = context["diagnostics"]["captain_surfaces"]
    assert surfaces["production"]["authority"] is True
    assert surfaces["cvar_diagnostic"]["authority"] is False
    assert "Only maximum_ev_production" in surfaces["interpretation"]


def test_captain_and_regret_surfaces_follow_producer_schemas():
    canonical, pinnacle = _payloads()
    pinnacle["selection_regret"] = [
        {
            "player_id": 1,
            "objective_regret": 0.25,
            "added_player_names": ["Saka"],
            "removed_player_names": ["Foden"],
        }
    ]
    pinnacle["robust_cvar_scenarios"]["unrestricted"]["captain"] = [
        {"player_id": 9, "web_name": "Haaland"}
    ]
    pinnacle["solver_parity"].update(
        {"apex_captain": 8, "external_captain": 7}
    )

    context = build_answer_context(canonical, pinnacle, now=NOW)
    surfaces = context["diagnostics"]["captain_surfaces"]
    assert context["selected_player_reasons"][0]["alternative"] == "Saka"
    assert surfaces["cvar_diagnostic"]["captain_id"] == 9
    assert surfaces["cvar_diagnostic"]["captain"] == "Haaland"
    assert surfaces["independent_parity_diagnostic"]["captain_id"] == 7
    assert surfaces["independent_parity_diagnostic"]["apex_captain_id"] == 8


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


def test_snapshot_mismatch_and_missing_minutes_block():
    canonical, pinnacle = _payloads()
    pinnacle["official_snapshot"] = dict(pinnacle["official_snapshot"], fixtures_sha256="other")
    canonical["recommendation"]["squad"][0]["expected_minutes"] = None
    context = build_answer_context(canonical, pinnacle, now=NOW)
    assert context["safe_to_act"] is False
    assert any("hashes do not match" in blocker for blocker in context["blockers"])
    assert any("expected-minutes" in blocker for blocker in context["blockers"])


def test_bundle_identity_is_required_and_must_match():
    canonical, pinnacle = _payloads()
    pinnacle["decision_bundle_id"] = "bundle-b"
    context = build_answer_context(canonical, pinnacle, now=NOW)
    assert context["safe_to_act"] is False
    assert any("bundle identities do not match" in row for row in context["blockers"])


def test_router_requires_the_correct_artifact():
    assert route_question("Will Foden start?").required_artifact == "player_evidence_dossier"
    assert route_question("Foden vs Saka").required_artifact == "same_snapshot_player_dossier"
    assert route_question("What transfer should I make?").mode == "transfer"
    assert route_question("Give me the best team").mode == "canonical_team"
    assert route_question("Project status on GitHub").mode == "project_status"


def test_optional_degraded_source_does_not_override_validated_quality_fallback():
    canonical, pinnacle = _payloads()
    pinnacle["sources"].append(
        {
            "name": "official_team_strength",
            "ok": False,
            "configured": True,
            "checked_at": "2026-08-11T07:30:00+00:00",
            "version": "snapshot",
        }
    )
    context = build_answer_context(canonical, pinnacle, now=NOW)
    assert context["safe_to_act"] is True


def test_diagnostic_and_inferred_role_warnings_reach_answer_contract():
    canonical, pinnacle = _payloads()
    canonical["recommendation"]["squad"][0]["tactical_role_source"] = "statistical_inference"
    pinnacle["pinnacle_gate"] = {"warnings": ["captain stability is provisional"]}
    pinnacle["data_quality"] = {"warnings": ["team strength fallback active"]}
    context = build_answer_context(canonical, pinnacle, now=NOW)
    assert any("captain stability" in warning for warning in context["warnings"])
    assert any("team strength fallback" in warning for warning in context["warnings"])
    assert any("statistical inference" in warning for warning in context["warnings"])
