from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.shrinkage import position_price_tier_groups, shrink_player_rates
from apex_fpl.services.enrichment import add_preseason_features, coalesce_context
from apex_fpl.services.integrity import reconcile
from apex_fpl.services.provenance import load_upstream_pins


def num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def opt(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def blend(base: pd.Series, pre: pd.Series, premins: pd.Series) -> pd.Series:
    b = pd.to_numeric(base, errors="coerce").fillna(0.0)
    p = pd.to_numeric(pre, errors="coerce")
    m = pd.to_numeric(premins, errors="coerce").fillna(0.0)
    w = np.clip(m / 270.0, 0.0, 0.35) * p.notna().astype(float)
    return b * (1.0 - w) + p.fillna(0.0) * w


def load_projection_evidence_players(settings) -> pd.DataFrame:
    """Rebuild the exact pre-projection statistical surface from cached sources."""
    http = CachedHttp(settings.cache_dir)
    official = OfficialFPLClient(http).snapshot(force=False)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    if not core_pin:
        raise ValueError("projection evidence parity requires a pinned FPL Core commit")

    core_client = FPLCoreClient(http, settings.season, ref=core_pin)
    core = core_client.playerstats(force=False)
    previous = core_client.previous_season_playerstats(force=False)
    friendlies = core_client.preseason_friendlies(force=False)

    players, _ = reconcile(official.players, core)
    if not previous.empty:
        players = players.merge(
            previous.drop_duplicates("player_id"),
            on="player_id",
            how="left",
            validate="one_to_one",
        )
    players = coalesce_context(players)
    players = add_preseason_features(players, friendlies)
    return players


def parity_shadow(projections: pd.DataFrame, players: pd.DataFrame):
    p = players.copy()
    p["shrinkage_group"] = position_price_tier_groups(p)
    s = shrink_player_rates(p).reset_index(drop=True)
    premins = num(p, "preseason_minutes")
    raw_xg = blend(num(p, "expected_goals_per_90"), opt(p, "preseason_xg90"), premins)
    raw_xa = blend(num(p, "expected_assists_per_90"), opt(p, "preseason_xa90"), premins)
    new_xg = blend(s["shrunk_xg90"], opt(p, "preseason_xg90"), premins)
    new_xa = blend(s["shrunk_xa90"], opt(p, "preseason_xa90"), premins)
    audit = p[[c for c in ["player_id", "web_name", "position", "price"] if c in p.columns]].copy()
    audit["raw_model_xg90"] = raw_xg.to_numpy()
    audit["raw_model_xa90"] = raw_xa.to_numpy()
    audit["shrunk_model_xg90"] = new_xg.to_numpy()
    audit["shrunk_model_xa90"] = new_xa.to_numpy()
    audit["evidence_minutes"] = s[[
        "xg90_combined_effective_evidence_minutes",
        "xa90_combined_effective_evidence_minutes",
    ]].max(axis=1).to_numpy()
    audit["previous_minutes"] = num(p, "previous_minutes").to_numpy()
    lookup = audit.drop_duplicates("player_id").set_index("player_id")
    out = projections.copy()
    pid = out["player_id"].astype(int)
    model_xg = num(out, "model_xg90")
    model_xa = num(out, "model_xa90")
    pxg = pid.map(lookup["raw_model_xg90"]).fillna(model_xg)
    pxa = pid.map(lookup["raw_model_xa90"]).fillna(model_xa)
    max_error = max(float((pxg - model_xg).abs().max()), float((pxa - model_xa).abs().max()))
    if max_error > 1e-9:
        raise ValueError(f"production input parity failed: max rate error={max_error:.6g}")
    nxg = pid.map(lookup["shrunk_model_xg90"]).fillna(model_xg)
    nxa = pid.map(lookup["shrunk_model_xa90"]).fillna(model_xa)
    pos = pid.map(lookup["position"]).fillna("MID")
    gp = pos.map({"GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}).fillna(5.0)
    old_score = model_xg * gp + model_xa * 3.0
    new_score = nxg * gp + nxa * 3.0
    ratio = np.divide(
        new_score,
        old_score,
        out=np.ones(len(out)),
        where=old_score.to_numpy() > 1e-12,
    )
    old_attack = num(out, "xp_attack")
    shrunk_apex = (
        num(out, "apex_xp") - old_attack + old_attack * ratio
    ).clip(lower=0.0)
    out["shrunk_blended_xp_v2"] = (
        num(out, "xp")
        - num(out, "xp_expert_apex_model")
        + shrunk_apex * num(out, "effective_weight_apex_model")
    ).clip(lower=0.0)
    return audit, out
