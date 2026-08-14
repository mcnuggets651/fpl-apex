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

    Identity reconciliation is hierarchical rather than player-specific:
    1. unique exact normalised official full name;
    2. for still-unmatched players, unique official ``web_name`` matched to a
       unique Understat display name, with same-team corroboration when both
       sources expose a team label.

    Ambiguous identities are always excluded. No manual player alias table is used.
    """
    required_core = {"player_id", "first_name", "second_name"}
    missing_core = sorted(required_core - set(core_players.columns))
    if missing_core:
        raise ValueError(f"current FPL Core players missing columns: {missing_core}")
    required_us = {"player_name", "understat_xg90", "understat_xa90"}
    missing_us = sorted(required_us - set(understat_players.columns))
    if missing_us:
        raise ValueError(f"Understat players missing columns: {missing_us}")

    core_cols = ["player_id", "first_name", "second_name"]
    for optional in ("web_name", "team_name"):
        if optional in core_players.columns:
            core_cols.append(optional)
    core = core_players[core_cols].copy()
    core["player_id"] = pd.to_numeric(core["player_id"], errors="coerce")
    core = core.dropna(subset=["player_id"]).copy()
    core["player_id"] = core["player_id"].astype(int)
    core["player_name"] = (
        core["first_name"].fillna("").astype(str).str.strip()
        + " "
        + core["second_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    core["full_name_key"] = core["player_name"].map(normalise_player_name)
    core["web_name_key"] = (
        core["web_name"].map(normalise_player_name)
        if "web_name" in core.columns
        else ""
    )
    core["team_key"] = (
        core["team_name"].map(normalise_player_name)
        if "team_name" in core.columns
        else ""
    )

    us_cols = ["player_name", "understat_xg90", "understat_xa90"]
    if "team_name" in understat_players.columns:
        us_cols.append("team_name")
    us = understat_players[us_cols].copy().reset_index(drop=True)
    us["_understat_row"] = us.index.astype(int)
    us["name_key"] = us["player_name"].map(normalise_player_name)
    us["team_key"] = (
        us["team_name"].map(normalise_player_name)
        if "team_name" in us.columns
        else ""
    )
    for col in ["understat_xg90", "understat_xa90"]:
        us[col] = pd.to_numeric(us[col], errors="coerce")

    def unique_matches(
        left: pd.DataFrame,
        left_key: str,
        right: pd.DataFrame,
        *,
        method: str,
        require_team_if_present: bool = False,
    ) -> pd.DataFrame:
        left = left[left[left_key].astype(str).ne("")].copy()
        right = right[right["name_key"].astype(str).ne("")].copy()
        left_counts = left.groupby(left_key).size()
        right_counts = right.groupby("name_key").size()
        valid = set(left_counts[left_counts == 1].index) & set(
            right_counts[right_counts == 1].index
        )
        if not valid:
            return pd.DataFrame()
        matched = left[left[left_key].isin(valid)].merge(
            right[right["name_key"].isin(valid)],
            left_on=left_key,
            right_on="name_key",
            how="inner",
            validate="one_to_one",
            suffixes=("_core", "_understat"),
        )
        if require_team_if_present:
            core_team = matched.get("team_key_core", pd.Series("", index=matched.index)).fillna("")
            us_team = matched.get("team_key_understat", pd.Series("", index=matched.index)).fillna("")
            both_present = core_team.astype(str).ne("") & us_team.astype(str).ne("")
            matched = matched[~both_present | core_team.eq(us_team)].copy()
        matched["understat_match_method"] = method
        return matched

    exact = unique_matches(core, "full_name_key", us, method="full_name")
    matched_core_ids = set(pd.to_numeric(exact.get("player_id"), errors="coerce").dropna().astype(int))
    matched_us_rows = set(pd.to_numeric(exact.get("_understat_row"), errors="coerce").dropna().astype(int))

    fallback = pd.DataFrame()
    if "web_name" in core.columns:
        remaining_core = core[~core["player_id"].isin(matched_core_ids)].copy()
        remaining_us = us[~us["_understat_row"].isin(matched_us_rows)].copy()
        fallback = unique_matches(
            remaining_core,
            "web_name_key",
            remaining_us,
            method="web_name_team",
            require_team_if_present=True,
        )

    pieces = [frame for frame in (exact, fallback) if not frame.empty]
    if not pieces:
        return pd.DataFrame(
            columns=[
                "player_id",
                "understat_xg90",
                "understat_xa90",
                "understat_match_method",
            ]
        )
    out = pd.concat(pieces, ignore_index=True)
    if out["player_id"].duplicated().any():
        raise ValueError("Understat reconciliation mapped a current player more than once")
    return out[
        [
            "player_id",
            "understat_xg90",
            "understat_xa90",
            "understat_match_method",
        ]
    ].reset_index(drop=True)


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

    if "apex_sd" in d.columns:
        em = pd.to_numeric(d["expected_minutes"], errors="coerce").fillna(0.0)
        min_share = np.clip(em / 90.0, 0.0, 1.0)
        variance = np.maximum(0.8, 0.45 * d["apex_xp"] + (1.0 - min_share) * 2.2)
        d["apex_sd"] = np.sqrt(variance)

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
    zero_players_all = d.loc[zero_base_unrepriced, ["player_id"]].drop_duplicates()
    zero_players_outfield = d.loc[
        zero_base_unrepriced & ~d["position"].eq("GK"), ["player_id"]
    ].drop_duplicates()
    diagnostics = {
        "player_rows": int(len(unique_players)),
        "matched_players": int(len(matched_players)),
        "matched_player_rate": float(len(matched_players) / len(unique_players)) if len(unique_players) else 0.0,
        "zero_base_unrepriced_players": int(len(zero_players_outfield)),
        "zero_base_unrepriced_players_all_positions": int(len(zero_players_all)),
        "zero_base_gate_scope": "outfield_only; goalkeeper zero attacking baselines are structurally valid",
        "xg_understat_weight": float(xg_weight),
        "xa_understat_weight": float(xa_weight),
        "bonus_prior_policy": "held_fixed_to_isolate_direct_validated_attacking_signal",
    }
    return challenger, diagnostics
