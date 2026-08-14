from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.evaluation.understat_players import normalise_player_name
from apex_fpl.models.ensemble import FULL_GAMEWEEK_EXPERTS, blend_projection


def map_understat_to_current_ids(
    core_players: pd.DataFrame,
    understat_players: pd.DataFrame,
) -> pd.DataFrame:
    """Map prior-season Understat rates to current official IDs conservatively.

    Current IDs come from the immutable FPL Core identity table already pinned by
    the sealed decision bundle. Only unique normalised full names in both sources
    are accepted; ambiguous identities are excluded rather than guessed.
    """
    required_core = {"player_id", "first_name", "second_name"}
    missing_core = sorted(required_core - set(core_players.columns))
    if missing_core:
        raise ValueError(f"current FPL Core players missing columns: {missing_core}")
    required_us = {"player_name", "understat_xg90", "understat_xa90"}
    missing_us = sorted(required_us - set(understat_players.columns))
    if missing_us:
        raise ValueError(f"Understat players missing columns: {missing_us}")

    core = core_players[["player_id", "first_name", "second_name"]].copy()
    core["player_id"] = pd.to_numeric(core["player_id"], errors="coerce")
    core = core.dropna(subset=["player_id"]).copy()
    core["player_id"] = core["player_id"].astype(int)
    core["player_name"] = (
        core["first_name"].fillna("").astype(str).str.strip()
        + " "
        + core["second_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    core["name_key"] = core["player_name"].map(normalise_player_name)

    us = understat_players[
        ["player_name", "understat_xg90", "understat_xa90"]
    ].copy()
    us["name_key"] = us["player_name"].map(normalise_player_name)
    for col in ["understat_xg90", "understat_xa90"]:
        us[col] = pd.to_numeric(us[col], errors="coerce")

    core_counts = core.groupby("name_key").size()
    us_counts = us.groupby("name_key").size()
    valid = set(core_counts[core_counts == 1].index) & set(us_counts[us_counts == 1].index)
    out = core[core["name_key"].isin(valid)].merge(
        us[us["name_key"].isin(valid)][
            ["name_key", "understat_xg90", "understat_xa90"]
        ],
        on="name_key",
        how="inner",
        validate="one_to_one",
    )
    return out[["player_id", "understat_xg90", "understat_xa90"]].reset_index(drop=True)


def reprice_projection_surface(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    understat_rates: pd.DataFrame,
    weights: dict[str, float],
    risk_penalty: float,
    *,
    xg_weight: float = 0.50,
    xa_weight: float = 0.30,
) -> tuple[pd.DataFrame, dict]:
    """Build a same-snapshot Understat challenger without refetching Apex inputs.

    The challenger changes only the direct player attacking-rate contribution in
    the transparent Apex expert. The existing bonus prior is deliberately held
    fixed in this first production A/B so the test isolates the validated xG/xA
    signal instead of allowing a secondary bonus heuristic to amplify it.
    """
    if not 0 <= xg_weight <= 1 or not 0 <= xa_weight <= 1:
        raise ValueError("Understat blend weights must be between zero and one")
    required = {"player_id", "gw", "apex_xp", "xp_attack", "model_xg90", "model_xa90"}
    missing = sorted(required - set(projections.columns))
    if missing:
        raise ValueError(f"projection surface missing columns: {missing}")

    positions = players[["player_id", "position"]].drop_duplicates("player_id").copy()
    expected_minutes = players[["player_id", "expected_minutes"]].drop_duplicates("player_id").copy()
    d = projections.copy().merge(
        positions,
        on="player_id",
        how="left",
        validate="many_to_one",
    ).merge(
        expected_minutes,
        on="player_id",
        how="left",
        validate="many_to_one",
    ).merge(
        understat_rates.drop_duplicates("player_id"),
        on="player_id",
        how="left",
        validate="many_to_one",
    )

    base_xg = pd.to_numeric(d["model_xg90"], errors="coerce")
    base_xa = pd.to_numeric(d["model_xa90"], errors="coerce")
    us_xg = pd.to_numeric(d["understat_xg90"], errors="coerce")
    us_xa = pd.to_numeric(d["understat_xa90"], errors="coerce")
    matched = base_xg.notna() & base_xa.notna() & us_xg.notna() & us_xa.notna()

    new_xg = base_xg.copy()
    new_xa = base_xa.copy()
    new_xg.loc[matched] = (1.0 - xg_weight) * base_xg.loc[matched] + xg_weight * us_xg.loc[matched]
    new_xa.loc[matched] = (1.0 - xa_weight) * base_xa.loc[matched] + xa_weight * us_xa.loc[matched]

    goal_points = d["position"].map({"GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}).fillna(5.0)
    base_signal = base_xg.fillna(0.0) * goal_points + base_xa.fillna(0.0) * 3.0
    new_signal = new_xg.fillna(0.0) * goal_points + new_xa.fillna(0.0) * 3.0
    base_attack = pd.to_numeric(d["xp_attack"], errors="coerce").fillna(0.0)

    repricable = matched & base_signal.gt(1e-9)
    new_attack = base_attack.copy()
    new_attack.loc[repricable] = (
        base_attack.loc[repricable]
        * new_signal.loc[repricable]
        / base_signal.loc[repricable]
    )
    zero_base_unrepriced = matched & ~repricable & new_signal.gt(1e-9)

    base_apex = pd.to_numeric(d["apex_xp"], errors="coerce").fillna(0.0)
    d["baseline_apex_xp"] = base_apex
    d["baseline_xp_attack"] = base_attack
    d["challenger_model_xg90"] = new_xg
    d["challenger_model_xa90"] = new_xa
    d["challenger_xp_attack"] = new_attack
    d["understat_player_matched"] = matched
    d["understat_zero_base_unrepriced"] = zero_base_unrepriced
    d["apex_xp"] = np.maximum(base_apex - base_attack + new_attack, 0.0)

    # The transparent model variance is a deterministic function of model xP and
    # minutes share. Recompute it so stochastic diagnostics are not left on the
    # baseline variance after changing the Apex mean.
    if "apex_sd" in d.columns:
        em = pd.to_numeric(d["expected_minutes"], errors="coerce").fillna(0.0)
        min_share = np.clip(em / 90.0, 0.0, 1.0)
        variance = np.maximum(0.8, 0.45 * d["apex_xp"] + (1.0 - min_share) * 2.2)
        d["apex_sd"] = np.sqrt(variance)

    # ``blend_projection`` expects full-GW expert values before allocating them
    # across DGW rows. Undo the already-applied allocation from the sealed baseline.
    allocation = pd.to_numeric(
        d.get("expert_allocation_count", pd.Series(1.0, index=d.index)),
        errors="coerce",
    ).fillna(1.0).clip(lower=1.0)
    for col in FULL_GAMEWEEK_EXPERTS:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce") * allocation

    drop_helper = ["position", "expected_minutes", "understat_xg90", "understat_xa90"]
    challenger = blend_projection(d.drop(columns=drop_helper, errors="ignore"), weights, risk_penalty)
    if "decay" in challenger.columns:
        challenger["weighted_xp"] = challenger["xp"] * pd.to_numeric(
            challenger["decay"], errors="coerce"
        ).fillna(1.0)

    unique_players = projections[["player_id"]].drop_duplicates()
    matched_players = d.loc[matched, ["player_id"]].drop_duplicates()
    zero_players = d.loc[zero_base_unrepriced, ["player_id"]].drop_duplicates()
    diagnostics = {
        "player_rows": int(len(unique_players)),
        "matched_players": int(len(matched_players)),
        "matched_player_rate": float(len(matched_players) / len(unique_players)) if len(unique_players) else 0.0,
        "zero_base_unrepriced_players": int(len(zero_players)),
        "xg_understat_weight": float(xg_weight),
        "xa_understat_weight": float(xa_weight),
        "bonus_prior_policy": "held_fixed_to_isolate_direct_validated_attacking_signal",
    }
    return challenger, diagnostics
