from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "certify_release_generation.py"
SPEC = spec_from_file_location("certify_release_generation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _payloads():
    squad = [{"player_id": pid, "web_name": f"P{pid}"} for pid in range(1, 16)]
    recommendation = {
        "selector": "receding_horizon_current_team_maximum_ev",
        "squad": squad,
        "xi": squad[:11],
        "captain_id": 1,
        "vice_captain_id": 2,
        "bench_gk_id": 12,
        "outfield_bench_order_ids": [13, 14, 15],
        "gw1_expected_total_with_mechanics": 50.0,
        "action_now": {
            "squad": [dict(row) for row in squad],
            "xi": [dict(row) for row in squad[:11]],
            "captain": [dict(squad[0])],
            "vice_captain": [dict(squad[1])],
            "bench_gk": dict(squad[11]),
            "outfield_bench_order": [dict(row) for row in squad[12:15]],
            "exact_expected_total_points": 50.0,
            "mechanics_authority": "independent_exact_current_gameweek_rescore",
            "mechanics_reconciled": True,
        },
    }
    canonical = {
        "decision_bundle_id": "bundle",
        "strategy_stage": "final_validated",
        "strategy_base_ready": True,
        "ready_to_act": True,
        "all_player_truth": {
            "ready": True,
            "blockers": [],
            "player_count": 604,
            "hard_fact_coverage": 1.0,
            "canonical_projection_pair_coverage": 1.0,
            "airsenal_projection_pair_coverage": 1.0,
        },
        "final_selected_player_evidence": {
            "contract": "apex-player-evidence-v2",
            "coverage": {"ready": True},
            "dossiers": [dict(row) for row in squad],
        },
        "recommendation": recommendation,
    }
    answer = {
        "decision_bundle_id": "bundle",
        "safe_to_act": True,
        "ready_to_act": True,
        "blockers": [],
    }
    pinnacle = {"decision_bundle_id": "bundle", "pinnacle_ready": True}
    parity = {"decision_bundle_id": "bundle", "comparison_surface": "pinnacle_ev"}
    adversarial = {
        "decision_bundle_id": "bundle",
        "summary": {
            "audit_complete": True,
            "search_surface_defect_signals": [],
            "ban_solve_errors": [],
        },
    }
    bench = {
        "decision_bundle_id": "bundle",
        "fixed_submission": True,
        "bench_reordered_with_hindsight": False,
    }
    manifest = {"bundle_id": "bundle"}
    return canonical, answer, pinnacle, parity, adversarial, bench, manifest


def _validate(payloads):
    canonical, answer, pinnacle, parity, adversarial, bench, manifest = payloads
    return MODULE.validate_release_payloads(
        recommendation_payload=canonical,
        answer_context=answer,
        pinnacle=pinnacle,
        parity=parity,
        adversarial=adversarial,
        bench_stress=bench,
        manifest=manifest,
    )


def test_complete_release_certificate_accepts_one_coherent_generation():
    payloads = _payloads()
    certificate = _validate(payloads)
    assert certificate["decision_bundle_id"] == "bundle"
    assert certificate["selector"] == "receding_horizon_current_team_maximum_ev"
    assert certificate["mechanics"]["action_captain_id"] == 1
    assert certificate["mechanics"]["outfield_bench_order_ids"] == [13, 14, 15]


def test_release_certificate_rejects_action_captain_drift():
    payloads = _payloads()
    canonical = payloads[0]
    canonical["recommendation"]["action_now"]["captain"] = [
        canonical["recommendation"]["squad"][1]
    ]
    with pytest.raises(ValueError, match="action_now captain"):
        _validate(payloads)


def test_release_certificate_rejects_cross_artifact_bundle_drift():
    payloads = _payloads()
    payloads[3]["decision_bundle_id"] = "different-bundle"
    with pytest.raises(ValueError, match="decision_bundle_id"):
        _validate(payloads)


def test_release_certificate_rejects_adversarial_or_bench_shortcuts():
    payloads = _payloads()
    payloads[4]["summary"]["search_surface_defect_signals"] = ["candidate-space defect"]
    with pytest.raises(ValueError, match="defect signals"):
        _validate(payloads)

    payloads = _payloads()
    payloads[5]["bench_reordered_with_hindsight"] = True
    with pytest.raises(ValueError, match="hindsight"):
        _validate(payloads)
