from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.shrinkage import position_price_tier_groups, shrink_player_rates


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def build_shadow(projections: pd.DataFrame, players: pd.DataFrame):
    prepared = players.copy()
    prepared["shrinkage_group"] = position_price_tier_groups(prepared)
    shrunk = shrink_player_rates(prepared).reset_index(drop=True)

    cols = [c for c in ["player_id", "web_name", "position", "price"] if c in prepared.columns]
    audit = prepared[cols].reset_index(drop=True)
    for col in [
        "shrunk_xg90", "shrunk_xa90", "raw_xg90", "raw_xa90",
        "xg90_reliability", "xa90_reliability",
        "xg90_combined_effective_evidence_minutes",
        "xa90_combined_effective_evidence_minutes",
    ]:
        audit[col] = shrunk[col].to_numpy()

    lookup = audit.drop_duplicates("player_id").set_index("player_id")
    out = projections.copy()
    pid = out["player_id"].astype(int)
    old_xg = numeric(out, "model_xg90")
    old_xa = numeric(out, "model_xa90")
    new_xg = pid.map(lookup["shrunk_xg90"]).fillna(old_xg)
    new_xa = pid.map(lookup["shrunk_xa90"]).fillna(old_xa)
    position = pid.map(lookup["position"]).fillna("MID")
    goal_points = position.map({"GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}).fillna(5.0)

    old_score = old_xg * goal_points + old_xa * 3.0
    new_score = new_xg * goal_points + new_xa * 3.0
    old_attack = numeric(out, "xp_attack")
    ratio = np.divide(
        new_score.to_numpy(float),
        old_score.to_numpy(float),
        out=np.ones(len(out), dtype=float),
        where=old_score.to_numpy(float) > 1e-12,
    )
    new_attack = old_attack * ratio
    raw_apex = numeric(out, "apex_xp")
    shrunk_apex = (raw_apex - old_attack + new_attack).clip(lower=0.0)
    effective = numeric(out, "effective_weight_apex_model")
    old_contribution = numeric(out, "xp_expert_apex_model")

    out["raw_apex_xp"] = raw_apex
    out["shrunk_apex_xp"] = shrunk_apex
    out["shrunk_blended_xp"] = (
        numeric(out, "xp") - old_contribution + shrunk_apex * effective
    ).clip(lower=0.0)
    return prepared, audit, out


def horizon_gaps(shadow: pd.DataFrame, audit: pd.DataFrame, gameweeks: list[int], decay: float):
    discounts = {int(gw): float(decay) ** i for i, gw in enumerate(gameweeks)}
    frame = shadow.copy()
    frame["discount"] = frame["gw"].map(discounts).fillna(0.0)
    frame["raw_h"] = numeric(frame, "raw_apex_xp") * frame["discount"]
    frame["shrunk_h"] = numeric(frame, "shrunk_apex_xp") * frame["discount"]
    frame["air_h"] = numeric(frame, "airsenal_xp") * frame["discount"]
    gaps = frame.groupby("player_id", as_index=False).agg(
        raw_apex=("raw_h", "sum"),
        shrunk_apex=("shrunk_h", "sum"),
        airsenal=("air_h", "sum"),
    )
    gaps = gaps.merge(audit, on="player_id", how="left")
    gaps["raw_gap"] = (gaps["raw_apex"] - gaps["airsenal"]).abs()
    gaps["shrunk_gap"] = (gaps["shrunk_apex"] - gaps["airsenal"]).abs()
    gaps["evidence_minutes"] = gaps[[
        "xg90_combined_effective_evidence_minutes",
        "xa90_combined_effective_evidence_minutes",
    ]].max(axis=1)
    return gaps
