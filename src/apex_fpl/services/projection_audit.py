from __future__ import annotations

import numpy as np
import pandas as pd


APEX_COMPONENTS = {
    "appearance": "xp_appearance",
    "attack": "xp_attack",
    "clean_sheet": "xp_clean_sheet",
    "defcon": "xp_defensive_contribution",
    "saves": "xp_saves",
    "bonus": "xp_bonus_prior",
    "set_piece": "xp_set_piece_prior",
}

EXPERT_CONTRIBUTIONS = {
    "official": "xp_expert_official_ep",
    "apex": "xp_expert_apex_model",
    "airsenal": "xp_expert_airsenal",
    "market": "xp_expert_market",
}


def _numeric(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def build_projection_decomposition(
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    decay: float = 0.90,
) -> pd.DataFrame:
    """Explain canonical xP by expert and transparent Apex component.

    Expert contribution columns are exact additive shares of canonical ``xp``.
    Transparent Apex components are scaled by the Apex expert's effective ensemble
    share, so their sum equals the Apex expert contribution (up to floating error).
    This keeps explanations faithful to the actual canonical objective rather than
    presenting the standalone Apex model as if it were the final ensemble.
    """
    if projections.empty:
        return pd.DataFrame()
    required = {"player_id", "gw", "xp"}
    missing = required - set(projections.columns)
    if missing:
        raise ValueError(f"projection decomposition missing columns: {sorted(missing)}")

    d = projections[projections["gw"].isin([int(gw) for gw in gameweeks])].copy()
    if d.empty:
        return pd.DataFrame()
    order = {int(gw): idx for idx, gw in enumerate(gameweeks)}
    d["horizon_discount"] = d["gw"].map(
        lambda gw: float(decay) ** order.get(int(gw), len(order))
    )

    for label, col in EXPERT_CONTRIBUTIONS.items():
        d[f"canonical_{label}_contribution"] = _numeric(d, col) * d["horizon_discount"]
    d["canonical_xp_discounted"] = _numeric(d, "xp") * d["horizon_discount"]

    apex_xp = _numeric(d, "apex_xp")
    apex_contrib = _numeric(d, "xp_expert_apex_model")
    apex_scale = np.divide(
        apex_contrib,
        apex_xp,
        out=np.zeros(len(d), dtype=float),
        where=np.abs(apex_xp.to_numpy(float)) > 1e-12,
    )
    for label, col in APEX_COMPONENTS.items():
        d[f"canonical_apex_{label}"] = (
            _numeric(d, col).to_numpy(float)
            * apex_scale
            * d["horizon_discount"].to_numpy(float)
        )

    aggregations: dict[str, tuple[str, str]] = {
        "horizon_canonical_xp": ("canonical_xp_discounted", "sum"),
        "horizon_official_contribution": ("canonical_official_contribution", "sum"),
        "horizon_apex_contribution": ("canonical_apex_contribution", "sum"),
        "horizon_airsenal_contribution": ("canonical_airsenal_contribution", "sum"),
        "horizon_market_contribution": ("canonical_market_contribution", "sum"),
    }
    for label in APEX_COMPONENTS:
        aggregations[f"horizon_apex_{label}"] = (f"canonical_apex_{label}", "sum")

    out = d.groupby("player_id", as_index=False).agg(**aggregations)
    gw1 = d[d["gw"] == int(gameweeks[0])].groupby("player_id", as_index=False).agg(
        gw1_canonical_xp=("xp", "sum"),
        gw1_apex_xp=("apex_xp", "sum"),
        gw1_official_contribution=("xp_expert_official_ep", "sum"),
        gw1_apex_contribution=("xp_expert_apex_model", "sum"),
        gw1_airsenal_contribution=("xp_expert_airsenal", "sum"),
        gw1_market_contribution=("xp_expert_market", "sum"),
    )
    out = out.merge(gw1, on="player_id", how="left", validate="one_to_one")
    return out.sort_values("horizon_canonical_xp", ascending=False).reset_index(drop=True)


def build_fixture_shadow_comparison(
    production_fx: pd.DataFrame,
    shadow_fx: pd.DataFrame,
) -> pd.DataFrame:
    """Compare production and shadow team-goal/clean-sheet assumptions."""
    keys = ["gw", "team", "opponent", "is_home"]
    metrics = [
        "expected_team_goals",
        "expected_goals_against",
        "clean_sheet_prob",
        "attack_multiplier",
        "defence_multiplier",
    ]
    if production_fx.empty or shadow_fx.empty:
        return pd.DataFrame(columns=keys)
    left_cols = [*keys, *[c for c in metrics if c in production_fx.columns]]
    right_cols = [*keys, *[c for c in metrics if c in shadow_fx.columns]]
    left = production_fx[left_cols].copy().rename(
        columns={c: f"production_{c}" for c in metrics if c in production_fx.columns}
    )
    right = shadow_fx[right_cols].copy().rename(
        columns={c: f"shadow_{c}" for c in metrics if c in shadow_fx.columns}
    )
    out = left.merge(right, on=keys, how="inner", validate="one_to_one")
    for metric in metrics:
        prod = f"production_{metric}"
        shadow = f"shadow_{metric}"
        if prod in out.columns and shadow in out.columns:
            out[f"delta_{metric}"] = _numeric(out, shadow) - _numeric(out, prod)
    return out.sort_values(["gw", "team"]).reset_index(drop=True)


def build_player_shadow_comparison(
    production_apex: pd.DataFrame,
    shadow_apex: pd.DataFrame,
    gameweeks: list[int],
    *,
    decay: float = 0.90,
) -> pd.DataFrame:
    """Compare transparent player xP under production vs shadow fixture surfaces."""
    keys = ["player_id", "gw"]
    cols = [
        "apex_xp",
        "xp_attack",
        "xp_clean_sheet",
        "xp_defensive_contribution",
        "xp_bonus_prior",
        "xp_set_piece_prior",
    ]
    left = production_apex[[*keys, *[c for c in cols if c in production_apex.columns]]].copy()
    right = shadow_apex[[*keys, *[c for c in cols if c in shadow_apex.columns]]].copy()
    left = left.rename(columns={c: f"production_{c}" for c in cols if c in left.columns})
    right = right.rename(columns={c: f"shadow_{c}" for c in cols if c in right.columns})
    d = left.merge(right, on=keys, how="inner")
    if d.empty:
        return pd.DataFrame()
    order = {int(gw): idx for idx, gw in enumerate(gameweeks)}
    d["discount"] = d["gw"].map(lambda gw: float(decay) ** order.get(int(gw), len(order)))
    for col in cols:
        pcol, scol = f"production_{col}", f"shadow_{col}"
        if pcol in d.columns and scol in d.columns:
            d[f"discounted_production_{col}"] = _numeric(d, pcol) * d["discount"]
            d[f"discounted_shadow_{col}"] = _numeric(d, scol) * d["discount"]

    agg: dict[str, tuple[str, str]] = {}
    for col in cols:
        pcol, scol = f"discounted_production_{col}", f"discounted_shadow_{col}"
        if pcol in d.columns and scol in d.columns:
            agg[f"production_{col}"] = (pcol, "sum")
            agg[f"shadow_{col}"] = (scol, "sum")
    out = d.groupby("player_id", as_index=False).agg(**agg)
    for col in cols:
        pcol, scol = f"production_{col}", f"shadow_{col}"
        if pcol in out.columns and scol in out.columns:
            out[f"delta_{col}"] = out[scol] - out[pcol]
    if "delta_apex_xp" in out.columns:
        out = out.sort_values("delta_apex_xp", ascending=False)
    return out.reset_index(drop=True)
