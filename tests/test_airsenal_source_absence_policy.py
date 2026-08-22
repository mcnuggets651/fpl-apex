import math
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.models.ensemble import blend_projection
from apex_fpl.services.player_truth import audit_player_truth


def test_missing_airsenal_uses_explicit_apex_fallback_without_fabricating_source():
    base = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "apex_xp": 4.0,
            "apex_sd": 1.0,
            "official_xp": 5.0,
            "airsenal_xp": np.nan,
            "minutes_confidence": 0.8,
            "role_confidence": 0.8,
        }
    ])
    weights = {"official_ep": 0.2, "apex_model": 0.5, "airsenal": 0.3, "market": 0.0}
    out = blend_projection(base, weights, 0.0).iloc[0]

    # Fixed weights: 20% official + 50% Apex + the missing 30% explicitly
    # delegated to Apex. The absent AIrsenal source itself remains absent.
    assert math.isclose(float(out["canonical_ev_xp"]), 4.2, rel_tol=1e-9)
    assert not bool(out["source_present_airsenal"])
    assert bool(out["airsenal_source_absent"])
    assert math.isclose(float(out["effective_weight_airsenal"]), 0.0, abs_tol=1e-12)
    assert math.isclose(float(out["effective_weight_airsenal_fallback_apex"]), 0.3, rel_tol=1e-9)
    assert math.isclose(float(out["xp_expert_airsenal_fallback_apex"]), 1.2, rel_tol=1e-9)


def test_present_airsenal_keeps_normal_configured_weight():
    base = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "apex_xp": 4.0,
            "apex_sd": 1.0,
            "official_xp": 5.0,
            "airsenal_xp": 6.0,
            "minutes_confidence": 0.8,
            "role_confidence": 0.8,
        }
    ])
    weights = {"official_ep": 0.2, "apex_model": 0.5, "airsenal": 0.3, "market": 0.0}
    out = blend_projection(base, weights, 0.0).iloc[0]
    assert bool(out["source_present_airsenal"])
    assert not bool(out["airsenal_source_absent"])
    assert math.isclose(float(out["effective_weight_airsenal"]), 0.3, rel_tol=1e-9)
    assert math.isclose(float(out["effective_weight_airsenal_fallback_apex"]), 0.0, abs_tol=1e-12)


def _player() -> dict:
    return {
        "player_id": 1,
        "web_name": "New Player",
        "team": 1,
        "team_name": "Club",
        "position": "MID",
        "price": 5.0,
        "status": "a",
        "expected_minutes": 60.0,
        "minutes_confidence": 0.5,
        "role_confidence": 0.5,
    }


def test_truth_contract_accepts_only_explicitly_reconciled_airsenal_absence():
    players = pd.DataFrame([_player()])
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "canonical_ev_xp": 3.0,
            "source_present_airsenal": False,
            "airsenal_source_absent": True,
            "effective_weight_airsenal_fallback_apex": 0.3,
            "xp_expert_airsenal_fallback_apex": 0.9,
            "xp_set_piece_prior": 0.0,
        }
    ])
    audit = audit_player_truth(players, projections, expected_players=1)

    assert audit["ready"]
    # Production consumes certified pair coverage. Raw upstream presence stays
    # separately visible and is never fabricated.
    assert audit["airsenal_projection_pair_coverage"] == 1.0
    assert audit["airsenal_raw_projection_pair_coverage"] == 0.0
    assert audit["airsenal_source_absence_reconciled"] is True
    assert audit["airsenal_source_absent_pair_count"] == 1
    assert audit["airsenal_unreconciled_source_absent_pair_count"] == 0
    assert not audit["blockers"]


def test_truth_contract_rejects_unreconciled_airsenal_absence():
    players = pd.DataFrame([_player()])
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "canonical_ev_xp": 3.0,
            "source_present_airsenal": False,
            "airsenal_source_absent": True,
            "effective_weight_airsenal_fallback_apex": 0.0,
            "xp_expert_airsenal_fallback_apex": 0.0,
            "xp_set_piece_prior": 0.0,
        }
    ])
    audit = audit_player_truth(players, projections, expected_players=1)

    assert not audit["ready"]
    assert audit["airsenal_projection_pair_coverage"] == 0.0
    assert audit["airsenal_raw_projection_pair_coverage"] == 0.0
    assert audit["airsenal_source_absence_reconciled"] is False
    assert audit["airsenal_unreconciled_source_absent_pair_count"] == 1
    assert any("lack explicit fixed-weight Apex fallback" in item for item in audit["blockers"])


def test_truth_contract_reports_raw_presence_separately_when_source_is_present():
    players = pd.DataFrame([_player()])
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "canonical_ev_xp": 3.0,
            "source_present_airsenal": True,
            "airsenal_source_absent": False,
            "effective_weight_airsenal_fallback_apex": 0.0,
            "xp_expert_airsenal_fallback_apex": 0.0,
            "xp_set_piece_prior": 0.0,
        }
    ])
    audit = audit_player_truth(players, projections, expected_players=1)

    assert audit["ready"]
    assert audit["airsenal_projection_pair_coverage"] == 1.0
    assert audit["airsenal_raw_projection_pair_coverage"] == 1.0
    assert audit["airsenal_source_absence_reconciled"] is True


def test_adaptive_release_uses_certified_not_fabricated_airsenal_coverage():
    adaptive = Path(".github/workflows/joint-path-promotion-audit.yml").read_text(
        encoding="utf-8"
    )
    canonical = Path(".github/workflows/adaptive-canonical-diagnostic.yml").read_text(
        encoding="utf-8"
    )
    certifier = Path("scripts/certify_release_generation.py").read_text(encoding="utf-8")

    # Adaptive delegates to the exact Canonical transaction; the shared release
    # certifier consumes certified coverage from player_truth. Raw AIrsenal presence
    # remains a diagnostic field and is never required to be fabricated to 100%.
    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in adaptive
    assert "scripts/certify_release_generation.py" in canonical
    assert '"airsenal_projection_pair_coverage"' in certifier
    assert '"airsenal_raw_projection_pair_coverage"' not in certifier
    assert "certified all-player truth coverage is incomplete" in certifier
