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
    """Audit activated shrinkage against an independently rebuilt raw counterfactual.

    Production is now the evidence-qualified shrunk surface.  The audit therefore
    reconstructs both raw and qualified rates from the full evidence frame, proves
    that production equals the qualified reconstruction, and builds a raw
    counterfactual for the A/B solve.  It never shrinks the production rates again.
    """
    p = players.copy()
    p["shrinkage_group"] = position_price_tier_groups(p)
    s = shrink_player_rates(p).reset_index(drop=True)
    premins = num(p, "preseason_minutes")

    raw_xg = blend(num(p, "expected_goals_per_90"), opt(p, "preseason_xg90"), premins)
    raw_xa = blend(num(p, "expected_assists_per_90"), opt(p, "preseason_xa90"), premins)

    xg_evidence = pd.to_numeric(
        s["xg90_combined_effective_evidence_minutes"], errors="coerce"
    ).fillna(0.0)
    xa_evidence = pd.to_numeric(
        s["xa90_combined_effective_evidence_minutes"], errors="coerce"
    ).fillna(0.0)
    qualified_xg = blend(s["shrunk_xg90"], opt(p, "preseason_xg90"), premins)
    qualified_xa = blend(s["shrunk_xa90"], opt(p, "preseason_xa90"), premins)

    # A cohort prior is not player-specific evidence. When there is no competitive
    # evidence for a metric, activated production preserves the raw rate.
    xg_prior_only_bypassed = xg_evidence.le(0.0)
    xa_prior_only_bypassed = xa_evidence.le(0.0)
    qualified_xg = qualified_xg.where(~xg_prior_only_bypassed, raw_xg)
    qualified_xa = qualified_xa.where(~xa_prior_only_bypassed, raw_xa)

    audit = p[[c for c in ["player_id", "web_name", "position", "price"] if c in p.columns]].copy()
    audit["raw_model_xg90"] = raw_xg.to_numpy()
    audit["raw_model_xa90"] = raw_xa.to_numpy()
    audit["shrunk_model_xg90"] = qualified_xg.to_numpy()
    audit["shrunk_model_xa90"] = qualified_xa.to_numpy()
    audit["xg90_evidence_minutes"] = xg_evidence.to_numpy()
    audit["xa90_evidence_minutes"] = xa_evidence.to_numpy()
    audit["xg90_prior_only_bypassed"] = xg_prior_only_bypassed.to_numpy()
    audit["xa90_prior_only_bypassed"] = xa_prior_only_bypassed.to_numpy()
    audit["evidence_minutes"] = pd.concat([xg_evidence, xa_evidence], axis=1).max(axis=1).to_numpy()
    audit["previous_minutes"] = num(p, "previous_minutes").to_numpy()

    lookup = audit.drop_duplicates("player_id").set_index("player_id")
    out = projections.copy()
    pid = out["player_id"].astype(int)
    production_xg = num(out, "model_xg90")
    production_xa = num(out, "model_xa90")
    expected_xg = pid.map(lookup["shrunk_model_xg90"]).fillna(production_xg)
    expected_xa = pid.map(lookup["shrunk_model_xa90"]).fillna(production_xa)
    max_error = max(
        float((expected_xg - production_xg).abs().max()),
        float((expected_xa - production_xa).abs().max()),
    )
    if max_error > 1e-9:
        raise ValueError(f"activated production parity failed: max rate error={max_error:.6g}")

    # Build the raw counterfactual from the same production rows.  Only the direct
    # attacking-return component is reversed here; bonus is intentionally held
    # constant so this remains the conservative apples-to-apples diagnostic used by
    # the existing promotion gate.
    counterfactual_xg = pid.map(lookup["raw_model_xg90"]).fillna(production_xg)
    counterfactual_xa = pid.map(lookup["raw_model_xa90"]).fillna(production_xa)
    pos = pid.map(lookup["position"]).fillna("MID")
    gp = pos.map({"GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}).fillna(5.0)
    production_score = production_xg * gp + production_xa * 3.0
    raw_score = counterfactual_xg * gp + counterfactual_xa * 3.0
    ratio = np.divide(
        raw_score,
        production_score,
        out=np.ones(len(out)),
        where=production_score.to_numpy() > 1e-12,
    )
    production_attack = num(out, "xp_attack")
    raw_counterfactual_apex = (
        num(out, "apex_xp") - production_attack + production_attack * ratio
    ).clip(lower=0.0)
    out["raw_counterfactual_blended_xp_v1"] = (
        num(out, "xp")
        - num(out, "xp_expert_apex_model")
        + raw_counterfactual_apex * num(out, "effective_weight_apex_model")
    ).clip(lower=0.0)

    # The activated production surface is already shrunk.  Copying xp here makes
    # double-shrink impossible and gives the runner an explicit named contract.
    out["shrunk_blended_xp_v2"] = num(out, "xp")
    return audit, out
