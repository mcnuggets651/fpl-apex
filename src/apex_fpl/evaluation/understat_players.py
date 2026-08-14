from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class UnderstatPlayerAudit:
    calibration: pd.DataFrame
    holdout: dict
    selected_xg_weight: float
    selected_xa_weight: float
    pass_gate: bool


def normalise_player_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def normalise_understat_players(payload: dict, season: int) -> pd.DataFrame:
    rows = payload.get("players")
    if not isinstance(rows, list):
        raise ValueError("Understat league payload has no players list")
    columns = {
        "id": "understat_player_id",
        "player_name": "player_name",
        "team_title": "team_name",
        "time": "minutes",
        "goals": "goals",
        "xG": "xg",
        "assists": "assists",
        "xA": "xa",
        "shots": "shots",
        "key_passes": "key_passes",
        "npxG": "npxg",
        "xGChain": "xg_chain",
        "xGBuildup": "xg_buildup",
    }
    frame = pd.DataFrame(rows)
    missing = sorted({"id", "player_name", "time", "xG", "xA"} - set(frame.columns))
    if missing:
        raise ValueError(f"Understat player payload missing columns: {missing}")
    keep = [col for col in columns if col in frame.columns]
    frame = frame[keep].rename(columns=columns).copy()
    frame["season"] = int(season)
    for col in [
        "understat_player_id",
        "minutes",
        "goals",
        "xg",
        "assists",
        "xa",
        "shots",
        "key_passes",
        "npxg",
        "xg_chain",
        "xg_buildup",
    ]:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["understat_player_id", "player_name", "minutes", "xg", "xa"])
    frame["understat_player_id"] = frame["understat_player_id"].astype(int)
    frame["name_key"] = frame["player_name"].map(normalise_player_name)
    mins = frame["minutes"].clip(lower=1.0)
    frame["understat_xg90"] = frame["xg"] * 90.0 / mins
    frame["understat_xa90"] = frame["xa"] * 90.0 / mins
    if "goals" in frame:
        frame["actual_goals90"] = frame["goals"].fillna(0) * 90.0 / mins
    if "assists" in frame:
        frame["actual_assists90"] = frame["assists"].fillna(0) * 90.0 / mins
    if frame.duplicated(["season", "understat_player_id"]).any():
        raise ValueError(f"Understat player payload contains duplicate player IDs for {season}")
    return frame.reset_index(drop=True)


def latest_core_player_rates(
    stats: pd.DataFrame,
    players: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    d = stats.copy()
    if "player_id" not in d.columns and "id" in d.columns:
        d = d.rename(columns={"id": "player_id"})
    required = {"player_id", "expected_goals_per_90", "expected_assists_per_90"}
    missing = sorted(required - set(d.columns))
    if missing:
        raise ValueError(f"FPL Core playerstats missing columns: {missing}")
    identity_required = {"player_id", "first_name", "second_name"}
    missing_identity = sorted(identity_required - set(players.columns))
    if missing_identity:
        raise ValueError(f"FPL Core players missing identity columns: {missing_identity}")

    d["player_id"] = pd.to_numeric(d["player_id"], errors="coerce")
    if d["player_id"].duplicated().any():
        if "gw" not in d.columns:
            raise ValueError("longitudinal FPL Core playerstats lacks gw")
        d["gw"] = pd.to_numeric(d["gw"], errors="coerce")
        d = d.sort_values(["player_id", "gw"]).drop_duplicates("player_id", keep="last")
    keep = ["player_id", "expected_goals_per_90", "expected_assists_per_90"]
    if "minutes" in d.columns:
        keep.append("minutes")
    d = d[keep].copy()
    d = d.rename(
        columns={
            "expected_goals_per_90": "core_xg90",
            "expected_assists_per_90": "core_xa90",
            "minutes": "core_minutes",
        }
    )
    identity = players[["player_id", "first_name", "second_name"]].drop_duplicates("player_id").copy()
    identity["player_name"] = (
        identity["first_name"].fillna("").astype(str).str.strip()
        + " "
        + identity["second_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    out = identity.merge(d, on="player_id", how="inner", validate="one_to_one")
    out["season"] = int(season)
    out["name_key"] = out["player_name"].map(normalise_player_name)
    for col in ["core_xg90", "core_xa90", "core_minutes"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["core_xg90", "core_xa90", "name_key"]).reset_index(drop=True)


def match_core_understat(core: pd.DataFrame, understat: pd.DataFrame) -> pd.DataFrame:
    core_counts = core.groupby("name_key").size()
    understat_counts = understat.groupby("name_key").size()
    valid = set(core_counts[core_counts == 1].index) & set(understat_counts[understat_counts == 1].index)
    left = core[core["name_key"].isin(valid)].copy()
    right_cols = [
        "name_key",
        "understat_player_id",
        "understat_xg90",
        "understat_xa90",
        "minutes",
        "goals",
        "assists",
        "actual_goals90",
        "actual_assists90",
    ]
    right = understat[[col for col in right_cols if col in understat.columns]].copy()
    return left.merge(right, on="name_key", how="inner", validate="one_to_one")


def _poisson_nll(actual: np.ndarray, expected: np.ndarray) -> np.ndarray:
    y = np.asarray(actual, dtype=float)
    lam = np.clip(np.asarray(expected, dtype=float), 1e-9, None)
    lgamma = np.vectorize(math.lgamma)
    return lam - y * np.log(lam) + lgamma(y + 1.0)


def _losses(frame: pd.DataFrame, xg_weight: float, xa_weight: float) -> pd.DataFrame:
    minutes = frame["target_minutes"].to_numpy(float)
    goal_rate = (
        (1.0 - xg_weight) * frame["core_xg90"].to_numpy(float)
        + xg_weight * frame["understat_xg90"].to_numpy(float)
    )
    assist_rate = (
        (1.0 - xa_weight) * frame["core_xa90"].to_numpy(float)
        + xa_weight * frame["understat_xa90"].to_numpy(float)
    )
    expected_goals = goal_rate * minutes / 90.0
    expected_assists = assist_rate * minutes / 90.0
    return pd.DataFrame(
        {
            "goal_nll": _poisson_nll(frame["target_goals"].to_numpy(float), expected_goals),
            "assist_nll": _poisson_nll(
                frame["target_assists"].to_numpy(float), expected_assists
            ),
        },
        index=frame.index,
    )


def calibrate_understat_player_blend(
    panel: pd.DataFrame,
    *,
    weights: tuple[float, ...] = tuple(np.linspace(0.0, 1.0, 11)),
    bootstrap_samples: int = 5000,
    seed: int = 20260814,
) -> UnderstatPlayerAudit:
    required = {
        "audit_split",
        "core_xg90",
        "core_xa90",
        "understat_xg90",
        "understat_xa90",
        "target_minutes",
        "target_goals",
        "target_assists",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"player signal panel missing columns: {missing}")
    d = panel.dropna(subset=list(required)).copy()
    train = d[d["audit_split"] == "calibration"].copy()
    holdout = d[d["audit_split"] == "holdout"].copy()
    if train.empty or holdout.empty:
        raise ValueError("player signal audit requires calibration and untouched holdout rows")

    goal_grid: list[dict] = []
    assist_grid: list[dict] = []
    for weight in weights:
        losses = _losses(train, float(weight), float(weight))
        goal_grid.append({"weight": float(weight), "goal_nll": float(losses["goal_nll"].mean())})
        assist_grid.append(
            {"weight": float(weight), "assist_nll": float(losses["assist_nll"].mean())}
        )
    goal_table = pd.DataFrame(goal_grid)
    assist_table = pd.DataFrame(assist_grid)
    xg_weight = float(goal_table.sort_values(["goal_nll", "weight"]).iloc[0]["weight"])
    xa_weight = float(assist_table.sort_values(["assist_nll", "weight"]).iloc[0]["weight"])
    calibration = goal_table.merge(assist_table, on="weight")

    core_loss = _losses(holdout, 0.0, 0.0)
    blend_loss = _losses(holdout, xg_weight, xa_weight)
    delta = (blend_loss["goal_nll"] + blend_loss["assist_nll"]) - (
        core_loss["goal_nll"] + core_loss["assist_nll"]
    )
    rng = np.random.default_rng(seed)
    values = delta.to_numpy(float)
    means = np.empty(max(int(bootstrap_samples), 1), dtype=float)
    for idx in range(len(means)):
        sample = rng.choice(values, size=len(values), replace=True)
        means[idx] = float(sample.mean())
    ci_low, ci_high = np.quantile(means, [0.025, 0.975])

    core_goal = float(core_loss["goal_nll"].mean())
    core_assist = float(core_loss["assist_nll"].mean())
    blend_goal = float(blend_loss["goal_nll"].mean())
    blend_assist = float(blend_loss["assist_nll"].mean())
    combined_delta = float(delta.mean())
    pass_gate = bool(
        len(holdout) >= 80
        and combined_delta < 0
        and float(ci_high) < 0
        and blend_goal <= core_goal * 1.01
        and blend_assist <= core_assist * 1.01
        and (xg_weight > 0 or xa_weight > 0)
    )
    summary = {
        "calibration_rows": int(len(train)),
        "rows": int(len(holdout)),
        "core_goal_nll": core_goal,
        "blend_goal_nll": blend_goal,
        "core_assist_nll": core_assist,
        "blend_assist_nll": blend_assist,
        "combined_nll_delta": combined_delta,
        "bootstrap_ci95_low": float(ci_low),
        "bootstrap_ci95_high": float(ci_high),
        "bootstrap_samples": int(bootstrap_samples),
    }
    return UnderstatPlayerAudit(
        calibration=calibration,
        holdout=summary,
        selected_xg_weight=xg_weight,
        selected_xa_weight=xa_weight,
        pass_gate=pass_gate,
    )
