import json

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.services.pipeline import run_pipeline


def _mean_if(frame, column):
    if column not in frame.columns or frame.empty:
        return None
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).mean())


def test_live_forward_model_probe():
    settings = load_settings()
    out = run_pipeline(settings, horizon=5, scenario="unrestricted", force=True, plan_transfers=False)
    target_ids = [222, 224]
    p = out.projections[out.projections["player_id"].isin(target_ids)].copy()
    players = out.players[out.players["player_id"].isin(target_ids)].copy()

    preferred_projection_cols = [
        "player_id", "web_name", "gw", "opponent", "expected_minutes", "exp_minutes",
        "minutes", "appearance_probability", "start_probability", "canonical_ev_xp", "xp",
        "risk_adjusted_xp", "projection_confidence", "attack_model_xg90", "attack_model_xa90",
        "xg90", "xa90", "xp_attack", "xp_bonus_prior",
    ]
    pcols = [c for c in preferred_projection_cols if c in p.columns]

    preferred_player_cols = [
        "player_id", "web_name", "minutes", "starts", "current_team_matches",
        "expected_minutes", "exp_minutes", "start_probability", "appearance_probability",
        "xg90", "xa90", "expected_goals_per_90", "expected_assists_per_90",
        "previous_start_probability", "previous_minutes_per_match", "role_multiplier",
        "tactical_role", "status", "news",
    ]
    player_cols = [c for c in preferred_player_cols if c in players.columns]

    xp_col = next((c for c in ["canonical_ev_xp", "xp", "risk_adjusted_xp"] if c in p.columns), None)
    minute_col = next((c for c in ["expected_minutes", "exp_minutes", "minutes"] if c in p.columns), None)
    summary = {}
    for pid in target_ids:
        q = p[p["player_id"] == pid]
        summary[str(pid)] = {
            "horizon_xp": float(pd.to_numeric(q[xp_col], errors="coerce").fillna(0).sum()) if xp_col else None,
            "avg_projection_minutes": _mean_if(q, minute_col) if minute_col else None,
            "avg_start_probability": _mean_if(q, "start_probability"),
            "avg_appearance_probability": _mean_if(q, "appearance_probability"),
            "avg_confidence": _mean_if(q, "projection_confidence"),
        }

    payload = {
        "gameweeks": out.gameweeks,
        "safe_to_act": out.safety.safe_to_act,
        "blockers": out.safety.blockers,
        "projection_columns": list(p.columns),
        "summary": summary,
        "projection_rows": p[pcols].to_dict(orient="records"),
        "player_rows": players[player_cols].to_dict(orient="records"),
    }
    raise AssertionError("LIVE_FORWARD_MODEL=" + json.dumps(payload, default=str, sort_keys=True))
