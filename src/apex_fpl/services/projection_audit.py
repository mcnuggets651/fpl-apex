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


def reprice_apex_for_fixture_shadow(
    production_apex: pd.DataFrame,
    production_fx: pd.DataFrame,
    shadow_fx: pd.DataFrame,
    player_teams: pd.DataFrame,
) -> pd.DataFrame:
    """Reprice transparent Apex xP under a shadow fixture surface.

    The fixture model enters the current player projection only through the attack
    multiplier and clean-sheet probability. Repricing those two components from
    the already-computed production projection is therefore exact for a pure
    fixture-surface challenger and avoids rebuilding players from the deliberately
    slim report-facing pipeline output.
    """
    if production_apex.empty:
        return production_apex.copy()
    required_projection = {
        "player_id",
        "gw",
        "opponent",
        "is_home",
        "apex_xp",
        "xp_attack",
        "xp_clean_sheet",
    }
    missing = required_projection - set(production_apex.columns)
    if missing:
        raise ValueError(f"shadow repricing missing projection columns: {sorted(missing)}")
    if not {"player_id", "team"}.issubset(player_teams.columns):
        raise ValueError("player-team map must contain player_id and team")

    keys = ["gw", "team", "opponent", "is_home"]
    fixture_cols = [*keys, "attack_multiplier", "clean_sheet_prob"]
    for label, frame in [("production", production_fx), ("shadow", shadow_fx)]:
        missing_fx = set(fixture_cols) - set(frame.columns)
        if missing_fx:
            raise ValueError(
                f"{label} fixture surface missing columns: {sorted(missing_fx)}"
            )

    teams = player_teams[["player_id", "team"]].drop_duplicates("player_id")
    d = production_apex.merge(
        teams,
        on="player_id",
        how="left",
        validate="many_to_one",
    )
    if d["team"].isna().any():
        raise ValueError("shadow repricing could not map every projected player to a team")

    prod = production_fx[fixture_cols].rename(
        columns={
            "attack_multiplier": "production_attack_multiplier",
            "clean_sheet_prob": "production_clean_sheet_prob",
        }
    )
    shadow = shadow_fx[fixture_cols].rename(
        columns={
            "attack_multiplier": "shadow_attack_multiplier",
            "clean_sheet_prob": "shadow_clean_sheet_prob",
        }
    )
    d = d.merge(prod, on=keys, how="left", validate="many_to_one")
    d = d.merge(shadow, on=keys, how="left", validate="many_to_one")

    fixture_rows = d["opponent"].notna()
    needed = [
        "production_attack_multiplier",
        "production_clean_sheet_prob",
        "shadow_attack_multiplier",
        "shadow_clean_sheet_prob",
    ]
    if d.loc[fixture_rows, needed].isna().any().any():
        raise ValueError("shadow repricing fixture coverage is incomplete")

    prod_attack_mult = _numeric(d, "production_attack_multiplier", 1.0).clip(lower=1e-9)
    shadow_attack_mult = _numeric(d, "shadow_attack_multiplier", 1.0)
    prod_cs = _numeric(d, "production_clean_sheet_prob", 0.30).clip(lower=1e-9)
    shadow_cs = _numeric(d, "shadow_clean_sheet_prob", 0.30)

    original_attack = _numeric(d, "xp_attack")
    original_clean = _numeric(d, "xp_clean_sheet")
    d["xp_attack"] = original_attack * (shadow_attack_mult / prod_attack_mult)
    d["xp_clean_sheet"] = original_clean * (shadow_cs / prod_cs)

    unchanged = [
        "xp_appearance",
        "xp_defensive_contribution",
        "xp_saves",
        "xp_bonus_prior",
        "xp_set_piece_prior",
    ]
    d["apex_xp"] = d["xp_attack"] + d["xp_clean_sheet"]
    for col in unchanged:
        d["apex_xp"] += _numeric(d, col)

    drop_cols = ["team", *needed]
    return d.drop(columns=[col for col in drop_cols if col in d.columns])


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
