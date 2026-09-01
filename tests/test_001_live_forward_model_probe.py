import json

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.services.pipeline import run_pipeline


def test_live_forward_model_probe():
    settings = load_settings()
    out = run_pipeline(settings, horizon=5, scenario="unrestricted", force=True, plan_transfers=False)
    target_ids = [222, 224]
    p = out.projections[out.projections["player_id"].isin(target_ids)].copy()
    cols = [c for c in [
        "player_id", "web_name", "gw", "opponent", "expected_minutes", "appearance_probability",
        "canonical_ev_xp", "xp", "risk_adjusted_xp", "projection_confidence",
        "attack_model_xg90", "attack_model_xa90", "xp_attack", "xp_bonus_prior",
    ] if c in p.columns]
    rows = p[cols].to_dict(orient="records")
    summary = {}
    xp_col = next((c for c in ["canonical_ev_xp", "xp", "risk_adjusted_xp"] if c in p.columns), None)
    for pid in target_ids:
        q = p[p["player_id"] == pid]
        summary[str(pid)] = {
            "horizon_xp": float(pd.to_numeric(q[xp_col], errors="coerce").fillna(0).sum()) if xp_col else None,
            "avg_expected_minutes": float(pd.to_numeric(q.get("expected_minutes", 0), errors="coerce").fillna(0).mean()) if len(q) else None,
            "avg_confidence": float(pd.to_numeric(q.get("projection_confidence", 0), errors="coerce").fillna(0).mean()) if len(q) else None,
        }
    payload = {
        "gameweeks": out.gameweeks,
        "safe_to_act": out.safety.safe_to_act,
        "blockers": out.safety.blockers,
        "summary": summary,
        "rows": rows,
    }
    raise AssertionError("LIVE_FORWARD_MODEL=" + json.dumps(payload, default=str, sort_keys=True))
