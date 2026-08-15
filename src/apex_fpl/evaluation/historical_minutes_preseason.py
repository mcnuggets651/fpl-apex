from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.models.minutes import minutes_profile
from apex_fpl.services.enrichment import add_preseason_features


@dataclass(frozen=True)
class HistoricalSeasonSource:
    season: str
    feature_ref: str
    feature_timestamp: str
    outcome_ref: str
    current_players_path: str
    preseason_matches_path: str
    preseason_stats_path: str
    prior_players_path: str
    prior_stats_template: str
    outcome_stats_template: str
    outcome_gameweeks: tuple[int, ...]
    prior_gameweeks: tuple[int, ...] = tuple(range(1, 39))


class GitCoreReader:
    """Read immutable CSV snapshots directly from a local FPL Core git clone."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def _show(self, ref: str, path: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def csv(self, ref: str, path: str) -> pd.DataFrame:
        return pd.read_csv(StringIO(self._show(ref, path)))


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def load_source_manifest(path: Path) -> tuple[list[HistoricalSeasonSource], int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    minimum = int(payload.get("minimum_independent_seasons_for_promotion", 2))
    sources = []
    for row in payload.get("seasons", []):
        sources.append(
            HistoricalSeasonSource(
                season=str(row["season"]),
                feature_ref=str(row["feature_ref"]),
                feature_timestamp=str(row["feature_timestamp"]),
                outcome_ref=str(row["outcome_ref"]),
                current_players_path=str(row["current_players_path"]),
                preseason_matches_path=str(row["preseason_matches_path"]),
                preseason_stats_path=str(row["preseason_stats_path"]),
                prior_players_path=str(row["prior_players_path"]),
                prior_stats_template=str(row["prior_stats_template"]),
                outcome_stats_template=str(row["outcome_stats_template"]),
                outcome_gameweeks=tuple(
                    int(gw) for gw in row.get("outcome_gameweeks", range(1, 9))
                ),
                prior_gameweeks=tuple(
                    int(gw) for gw in row.get("prior_gameweeks", range(1, 39))
                ),
            )
        )
    return sources, minimum


def _numeric(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _is_appearance(frame: pd.DataFrame) -> pd.Series:
    """Core roster rows count as appearances only when positive minutes were played."""

    return _numeric(frame, "minutes_played", 0).fillna(0).gt(0)


def _is_start(frame: pd.DataFrame) -> pd.Series:
    return _is_appearance(frame) & _numeric(
        frame, "start_min", np.nan
    ).fillna(np.inf).le(1.0)


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den.where(den > 0)).replace([np.inf, -np.inf], np.nan)


def aggregate_prior_role(
    current_players: pd.DataFrame,
    prior_players: pd.DataFrame,
    prior_match_rows: pd.DataFrame,
    *,
    prior_team_matches: float = 38.0,
) -> pd.DataFrame:
    """Map prior PL playing-time states onto current IDs through stable player_code."""

    required = {"player_code", "player_id"}
    if not required.issubset(current_players.columns):
        raise ValueError("current players lack stable player_code/player_id mapping")
    if not required.issubset(prior_players.columns):
        raise ValueError("prior players lack stable player_code/player_id mapping")

    current = current_players[["player_code", "player_id"]].drop_duplicates().copy()
    prior = prior_players[["player_code", "player_id"]].drop_duplicates().copy()
    current["player_id"] = pd.to_numeric(current["player_id"], errors="coerce")
    prior["player_id"] = pd.to_numeric(prior["player_id"], errors="coerce")
    current = current.dropna().astype({"player_id": int}).rename(
        columns={"player_id": "current_player_id"}
    )
    prior = prior.dropna().astype({"player_id": int}).rename(
        columns={"player_id": "prior_player_id"}
    )
    identity = current.merge(prior, on="player_code", how="inner", validate="one_to_one")

    rows = prior_match_rows.copy()
    if rows.empty:
        return identity[["current_player_id"]].rename(
            columns={"current_player_id": "player_id"}
        )
    rows["player_id"] = pd.to_numeric(rows["player_id"], errors="coerce")
    rows["minutes_played"] = _numeric(rows, "minutes_played", 0).fillna(0)
    rows = rows.dropna(subset=["player_id"])
    rows["player_id"] = rows["player_id"].astype(int)
    rows["is_appearance"] = _is_appearance(rows).astype(int)
    rows["is_start"] = _is_start(rows).astype(int)
    rows["is_sub"] = (
        rows["is_appearance"].eq(1) & rows["is_start"].eq(0)
    ).astype(int)

    agg = rows.groupby("player_id", as_index=False).agg(
        prior_appearances=("is_appearance", "sum"),
        prior_starts=("is_start", "sum"),
        prior_minutes=("minutes_played", "sum"),
    )
    starter = (
        rows[rows["is_start"].eq(1)]
        .groupby("player_id", as_index=False)["minutes_played"]
        .mean()
        .rename(columns={"minutes_played": "prior_minutes_if_start"})
    )
    substitute = (
        rows[rows["is_sub"].eq(1)]
        .groupby("player_id", as_index=False)["minutes_played"]
        .mean()
        .rename(columns={"minutes_played": "prior_minutes_if_sub"})
    )
    agg = agg.merge(starter, on="player_id", how="left").merge(
        substitute, on="player_id", how="left"
    )
    agg = agg.rename(columns={"player_id": "prior_player_id"})
    out = identity.merge(agg, on="prior_player_id", how="left")
    out = out.rename(columns={"current_player_id": "player_id"}).drop(
        columns=["player_code", "prior_player_id"]
    )
    matches = pd.Series(float(prior_team_matches), index=out.index)
    out["prior_start_probability"] = (
        pd.to_numeric(out["prior_starts"], errors="coerce").fillna(0) / matches
    ).clip(0, 1)
    out["prior_appearance_probability"] = (
        pd.to_numeric(out["prior_appearances"], errors="coerce").fillna(0) / matches
    ).clip(0, 1)
    nonstart_opportunities = matches - pd.to_numeric(
        out["prior_starts"], errors="coerce"
    ).fillna(0)
    prior_sub_apps = (
        pd.to_numeric(out["prior_appearances"], errors="coerce").fillna(0)
        - pd.to_numeric(out["prior_starts"], errors="coerce").fillna(0)
    ).clip(lower=0)
    out["prior_bench_appearance_probability"] = _safe_div(
        prior_sub_apps, nonstart_opportunities
    ).fillna(0.0).clip(0, 1)
    out["prior_minutes_per_match"] = (
        pd.to_numeric(out["prior_minutes"], errors="coerce").fillna(0) / matches
    ).clip(0, 90)
    return out


def _team_friendly_counts(
    current_players: pd.DataFrame,
    preseason_matches: pd.DataFrame,
) -> pd.DataFrame:
    players = current_players[["player_id", "team_code"]].drop_duplicates("player_id").copy()
    players["player_id"] = pd.to_numeric(players["player_id"], errors="coerce")
    players["team_code"] = pd.to_numeric(players["team_code"], errors="coerce")
    players = players.dropna(subset=["player_id"]).astype({"player_id": int})

    matches = preseason_matches.copy()
    home = _numeric(matches, "home_team", np.nan)
    away = _numeric(matches, "away_team", np.nan)
    counts: dict[float, int] = {}
    for code in pd.concat([home, away]).dropna().tolist():
        counts[float(code)] = counts.get(float(code), 0) + 1
    players["preseason_team_friendlies"] = (
        players["team_code"].map(counts).fillna(0).astype(int)
    )
    return players[["player_id", "preseason_team_friendlies"]]


def aggregate_preseason_role(
    current_players: pd.DataFrame,
    preseason_matches: pd.DataFrame,
    preseason_stats: pd.DataFrame,
) -> pd.DataFrame:
    stats = preseason_stats.copy()
    stats["player_id"] = pd.to_numeric(stats["player_id"], errors="coerce")
    stats["minutes_played"] = _numeric(stats, "minutes_played", 0).fillna(0)
    stats = stats.dropna(subset=["player_id"])
    stats["player_id"] = stats["player_id"].astype(int)
    stats["is_appearance"] = _is_appearance(stats).astype(int)
    stats["is_start"] = _is_start(stats).astype(int)
    stats["is_sub"] = (
        stats["is_appearance"].eq(1) & stats["is_start"].eq(0)
    ).astype(int)

    agg = stats.groupby("player_id", as_index=False).agg(
        preseason_appearances=("is_appearance", "sum"),
        preseason_starts=("is_start", "sum"),
        preseason_minutes=("minutes_played", "sum"),
    )
    starter = (
        stats[stats["is_start"].eq(1)]
        .groupby("player_id", as_index=False)["minutes_played"]
        .mean()
        .rename(columns={"minutes_played": "preseason_minutes_if_start"})
    )
    substitute = (
        stats[stats["is_sub"].eq(1)]
        .groupby("player_id", as_index=False)["minutes_played"]
        .mean()
        .rename(columns={"minutes_played": "preseason_minutes_if_sub"})
    )
    agg = agg.merge(starter, on="player_id", how="left").merge(
        substitute, on="player_id", how="left"
    )
    counts = _team_friendly_counts(current_players, preseason_matches)
    out = current_players[["player_id"]].drop_duplicates().copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="coerce")
    out = out.dropna().astype({"player_id": int})
    out = out.merge(counts, on="player_id", how="left").merge(
        agg, on="player_id", how="left"
    )
    for col in [
        "preseason_team_friendlies",
        "preseason_appearances",
        "preseason_starts",
        "preseason_minutes",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    out["preseason_start_probability_team"] = _safe_div(
        out["preseason_starts"], out["preseason_team_friendlies"]
    ).fillna(0.0).clip(0, 1)
    nonstart = out["preseason_team_friendlies"] - out["preseason_starts"]
    sub_apps = (out["preseason_appearances"] - out["preseason_starts"]).clip(lower=0)
    out["preseason_bench_appearance_probability"] = _safe_div(
        sub_apps, nonstart
    ).fillna(0.0).clip(0, 1)
    return out


def _prepare_incumbent_inputs(
    current_players: pd.DataFrame,
    prior_role: pd.DataFrame,
    preseason_stats: pd.DataFrame,
    predeadline_playerstats: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    players = current_players.copy()
    players["player_id"] = pd.to_numeric(players["player_id"], errors="coerce")
    players = players.dropna(subset=["player_id"]).copy()
    players["player_id"] = players["player_id"].astype(int)

    if predeadline_playerstats is not None and not predeadline_playerstats.empty:
        pre = predeadline_playerstats.copy()
        if "id" in pre.columns and "player_id" not in pre.columns:
            pre["player_id"] = pd.to_numeric(pre["id"], errors="coerce")
        pre["player_id"] = pd.to_numeric(pre["player_id"], errors="coerce")
        pre = pre.dropna(subset=["player_id"]).copy()
        pre["player_id"] = pre["player_id"].astype(int)
        sort_cols = ["player_id", "gw"] if "gw" in pre.columns else ["player_id"]
        pre = pre.sort_values(sort_cols).drop_duplicates("player_id", keep="last")
        available = [
            col
            for col in ["player_id", "status", "chance_of_playing_next_round"]
            if col in pre.columns
        ]
        players = players.merge(pre[available], on="player_id", how="left")

    role = prior_role.copy()
    role["player_id"] = pd.to_numeric(role["player_id"], errors="coerce")
    role = role.dropna(subset=["player_id"]).copy()
    role["player_id"] = role["player_id"].astype(int)
    players = players.merge(role, on="player_id", how="left")

    # At the preseason deadline there are no current-season competitive minutes.
    # Historical role enters only through the explicit previous-season bridge.
    players["minutes"] = 0.0
    players["starts"] = 0.0
    players["starts_per_90"] = 0.0
    players["current_team_matches"] = 0.0
    players["previous_starts"] = pd.to_numeric(
        players["prior_starts"], errors="coerce"
    ).fillna(0)
    players["previous_minutes"] = pd.to_numeric(
        players["prior_minutes"], errors="coerce"
    ).fillna(0)
    players["previous_start_probability"] = pd.to_numeric(
        players["prior_start_probability"], errors="coerce"
    )
    players["previous_minutes_per_match"] = pd.to_numeric(
        players["prior_minutes_per_match"], errors="coerce"
    )

    players = add_preseason_features(players, preseason_stats)
    if "status" not in players.columns:
        players["status"] = "a"
    players["status"] = players["status"].fillna("a")
    profile = minutes_profile(players)
    return players, profile


def decomposed_minutes_challenger(
    players: pd.DataFrame,
    incumbent_profile: pd.DataFrame,
    prior_role: pd.DataFrame,
    preseason_role: pd.DataFrame,
) -> pd.DataFrame:
    """Shadow-only generative minutes challenger. Does not mutate production fields."""

    base = players[["player_id"]].copy()
    base = base.merge(prior_role, on="player_id", how="left").merge(
        preseason_role, on="player_id", how="left", suffixes=("", "_pre_role")
    )
    inc = incumbent_profile.reset_index(drop=True).copy()
    inc["player_id"] = players["player_id"].to_numpy()
    base = base.merge(
        inc[
            [
                "player_id",
                "preseason_role_weight",
                "availability_probability",
                "historical_start_probability",
            ]
        ],
        on="player_id",
        how="left",
        validate="one_to_one",
    )

    prior_start = pd.to_numeric(
        base["prior_start_probability"], errors="coerce"
    ).fillna(
        pd.to_numeric(
            base["historical_start_probability"], errors="coerce"
        ).fillna(0.5)
    )
    pre_start = pd.to_numeric(
        base["preseason_start_probability_team"], errors="coerce"
    ).fillna(prior_start)
    w = pd.to_numeric(base["preseason_role_weight"], errors="coerce").fillna(0).clip(0, 0.82)
    role_start = ((1 - w) * prior_start + w * pre_start).clip(0, 0.98)

    prior_bench = pd.to_numeric(
        base["prior_bench_appearance_probability"], errors="coerce"
    ).fillna(0.35)
    pre_bench = pd.to_numeric(
        base["preseason_bench_appearance_probability"], errors="coerce"
    ).fillna(prior_bench)
    w_bench = np.minimum(w, 0.50)
    role_bench = ((1 - w_bench) * prior_bench + w_bench * pre_bench).clip(0, 1)

    prior_start_mins = pd.to_numeric(
        base["prior_minutes_if_start"], errors="coerce"
    ).fillna(72.0).clip(45, 90)
    pre_start_mins = pd.to_numeric(
        base["preseason_minutes_if_start"], errors="coerce"
    ).fillna(prior_start_mins).clip(30, 90)
    w_cond = np.minimum(w, 0.45)
    mins_if_start = ((1 - w_cond) * prior_start_mins + w_cond * pre_start_mins).clip(
        45, 90
    )

    prior_sub_mins = pd.to_numeric(
        base["prior_minutes_if_sub"], errors="coerce"
    ).fillna(18.0).clip(1, 45)
    pre_sub_mins = pd.to_numeric(
        base["preseason_minutes_if_sub"], errors="coerce"
    ).fillna(prior_sub_mins).clip(1, 60)
    mins_if_sub = ((1 - w_cond) * prior_sub_mins + w_cond * pre_sub_mins).clip(1, 45)

    availability = pd.to_numeric(
        base["availability_probability"], errors="coerce"
    ).fillna(1).clip(0, 1)
    start = role_start * availability
    bench_app = role_bench * availability
    appearance = (role_start + (1 - role_start) * role_bench).clip(0, 1) * availability
    expected = (
        role_start * mins_if_start
        + (1 - role_start) * role_bench * mins_if_sub
    ).clip(0, 90) * availability

    return pd.DataFrame(
        {
            "player_id": base["player_id"].astype(int),
            "challenger_expected_minutes": expected,
            "challenger_start_probability": start,
            "challenger_appearance_probability": appearance,
            "challenger_bench_appearance_probability": bench_app,
            "challenger_minutes_if_start": mins_if_start,
            "challenger_minutes_if_sub": mins_if_sub,
            "challenger_role_start_probability": role_start,
            "challenger_role_bench_probability": role_bench,
        }
    )


def aggregate_outcomes(
    current_players: pd.DataFrame,
    outcome_rows: pd.DataFrame,
    gameweeks: tuple[int, ...],
) -> pd.DataFrame:
    """One row per preseason player per future GW, including zero-minute absences."""

    player_ids = (
        pd.to_numeric(current_players["player_id"], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
    )
    grid = pd.MultiIndex.from_product(
        [player_ids, list(gameweeks)], names=["player_id", "gw"]
    ).to_frame(index=False)

    rows = outcome_rows.copy()
    if rows.empty:
        rows = pd.DataFrame(columns=["player_id", "gw", "minutes_played", "start_min"])
    rows["player_id"] = pd.to_numeric(rows["player_id"], errors="coerce")
    rows["gw"] = pd.to_numeric(rows["gw"], errors="coerce")
    rows["minutes_played"] = _numeric(rows, "minutes_played", 0).fillna(0)
    rows = rows.dropna(subset=["player_id", "gw"]).copy()
    rows["player_id"] = rows["player_id"].astype(int)
    rows["gw"] = rows["gw"].astype(int)
    rows["actual_start"] = _is_start(rows).astype(int)
    rows["actual_appearance"] = _is_appearance(rows).astype(int)
    rows = rows.groupby(["player_id", "gw"], as_index=False).agg(
        actual_minutes=("minutes_played", "sum"),
        actual_start=("actual_start", "max"),
        actual_appearance=("actual_appearance", "max"),
    )
    out = grid.merge(rows, on=["player_id", "gw"], how="left")
    out[["actual_minutes", "actual_start", "actual_appearance"]] = out[
        ["actual_minutes", "actual_start", "actual_appearance"]
    ].fillna(0)
    out["actual_bench_appearance"] = (
        out["actual_appearance"].eq(1) & out["actual_start"].eq(0)
    ).astype(int)
    return out


def _brier(probability: pd.Series, outcome: pd.Series) -> float:
    p = pd.to_numeric(probability, errors="coerce")
    y = pd.to_numeric(outcome, errors="coerce")
    mask = p.notna() & y.notna()
    return float(np.mean(np.square(p[mask] - y[mask]))) if mask.any() else float("nan")


def _mae(prediction: pd.Series, actual: pd.Series) -> float:
    p = pd.to_numeric(prediction, errors="coerce")
    y = pd.to_numeric(actual, errors="coerce")
    mask = p.notna() & y.notna()
    return float(np.mean(np.abs(p[mask] - y[mask]))) if mask.any() else float("nan")


def _rmse(prediction: pd.Series, actual: pd.Series) -> float:
    p = pd.to_numeric(prediction, errors="coerce")
    y = pd.to_numeric(actual, errors="coerce")
    mask = p.notna() & y.notna()
    return (
        float(np.sqrt(np.mean(np.square(p[mask] - y[mask]))))
        if mask.any()
        else float("nan")
    )


def _ece(probability: pd.Series, outcome: pd.Series, bins: int = 10) -> float:
    p = pd.to_numeric(probability, errors="coerce")
    y = pd.to_numeric(outcome, errors="coerce")
    mask = p.notna() & y.notna()
    p = p[mask].clip(0, 1)
    y = y[mask]
    if p.empty:
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    labels = np.minimum(np.digitize(p.to_numpy(), edges[1:-1]), bins - 1)
    total = len(p)
    error = 0.0
    for idx in range(bins):
        use = labels == idx
        if not np.any(use):
            continue
        error += (np.sum(use) / total) * abs(
            float(p.iloc[use].mean()) - float(y.iloc[use].mean())
        )
    return float(error)


def score_minutes_models(scored: pd.DataFrame) -> dict:
    nonstarters = scored["actual_start"].eq(0)
    started = scored["actual_start"].eq(1)
    subbed = scored["actual_bench_appearance"].eq(1)

    metrics = {
        "rows": int(len(scored)),
        "players": int(scored["player_id"].nunique()),
        "incumbent": {
            "start_brier": _brier(
                scored["incumbent_start_probability"], scored["actual_start"]
            ),
            "start_calibration_ece": _ece(
                scored["incumbent_start_probability"], scored["actual_start"]
            ),
            "appearance_brier": _brier(
                scored["incumbent_appearance_probability"], scored["actual_appearance"]
            ),
            "bench_appearance_brier": _brier(
                scored.loc[nonstarters, "incumbent_bench_appearance_probability"],
                scored.loc[nonstarters, "actual_bench_appearance"],
            ),
            "minutes_mae": _mae(
                scored["incumbent_expected_minutes"], scored["actual_minutes"]
            ),
            "minutes_rmse": _rmse(
                scored["incumbent_expected_minutes"], scored["actual_minutes"]
            ),
            "starter_conditional_minutes_mae": _mae(
                scored.loc[started, "incumbent_minutes_if_start"],
                scored.loc[started, "actual_minutes"],
            ),
            "substitute_conditional_minutes_mae": _mae(
                scored.loc[subbed, "incumbent_minutes_if_sub"],
                scored.loc[subbed, "actual_minutes"],
            ),
        },
        "challenger": {
            "start_brier": _brier(
                scored["challenger_start_probability"], scored["actual_start"]
            ),
            "start_calibration_ece": _ece(
                scored["challenger_start_probability"], scored["actual_start"]
            ),
            "appearance_brier": _brier(
                scored["challenger_appearance_probability"], scored["actual_appearance"]
            ),
            "bench_appearance_brier": _brier(
                scored.loc[nonstarters, "challenger_bench_appearance_probability"],
                scored.loc[nonstarters, "actual_bench_appearance"],
            ),
            "minutes_mae": _mae(
                scored["challenger_expected_minutes"], scored["actual_minutes"]
            ),
            "minutes_rmse": _rmse(
                scored["challenger_expected_minutes"], scored["actual_minutes"]
            ),
            "starter_conditional_minutes_mae": _mae(
                scored.loc[started, "challenger_minutes_if_start"],
                scored.loc[started, "actual_minutes"],
            ),
            "substitute_conditional_minutes_mae": _mae(
                scored.loc[subbed, "challenger_minutes_if_sub"],
                scored.loc[subbed, "actual_minutes"],
            ),
        },
    }
    metrics["delta_challenger_minus_incumbent"] = {
        key: float(metrics["challenger"][key] - metrics["incumbent"][key])
        for key in metrics["incumbent"]
        if np.isfinite(metrics["challenger"][key])
        and np.isfinite(metrics["incumbent"][key])
    }
    return metrics


def _cohort_labels(player_frame: pd.DataFrame) -> pd.DataFrame:
    out = player_frame[["player_id"]].copy()
    prior_start = pd.to_numeric(
        player_frame["prior_start_probability"], errors="coerce"
    ).fillna(0)
    pre_starts = pd.to_numeric(player_frame["preseason_starts"], errors="coerce").fillna(0)
    pre_apps = pd.to_numeric(
        player_frame["preseason_appearances"], errors="coerce"
    ).fillna(0)
    out["established_returning_starter"] = prior_start >= 0.65
    out["rotation_prior"] = prior_start.between(0.20, 0.65, inclusive="left")
    out["repeated_preseason_starter"] = pre_starts >= 2
    out["cameo_only"] = (pre_apps > 0) & pre_starts.eq(0)
    out["no_prior_role"] = pd.to_numeric(
        player_frame["prior_appearances"], errors="coerce"
    ).fillna(0).eq(0)
    return out


def _preseason_return_coverage(preseason_stats: pd.DataFrame) -> dict:
    if preseason_stats.empty:
        return {"rows": 0, "minutes": 0.0}
    mins = _numeric(preseason_stats, "minutes_played", 0).fillna(0)
    appeared = mins.gt(0)
    result = {
        "rows": int(appeared.sum()),
        "players": int(
            pd.to_numeric(
                preseason_stats.loc[appeared, "player_id"], errors="coerce"
            ).nunique()
        ),
        "minutes": float(mins.sum()),
    }
    for source in ["goals", "assists", "total_shots", "shots_on_target", "xg", "xa"]:
        values = _numeric(preseason_stats, source, np.nan)
        observed = values.notna() & appeared
        result[f"{source}_rows_observed"] = int(observed.sum())
        result[f"{source}_minutes_covered"] = float(mins[observed].sum())
        result[f"{source}_minutes_coverage"] = (
            float(mins[observed].sum() / mins.sum()) if mins.sum() > 0 else 0.0
        )
    return result


def audit_historical_season(
    reader: GitCoreReader,
    source: HistoricalSeasonSource,
) -> tuple[dict, pd.DataFrame]:
    current_players = reader.csv(source.feature_ref, source.current_players_path)
    preseason_matches = reader.csv(source.feature_ref, source.preseason_matches_path)
    preseason_stats = reader.csv(source.feature_ref, source.preseason_stats_path)

    playerstats_path = f"data/{source.season}/playerstats.csv"
    try:
        predeadline_playerstats = reader.csv(source.feature_ref, playerstats_path)
    except subprocess.CalledProcessError:
        predeadline_playerstats = pd.DataFrame()

    prior_players = reader.csv(source.feature_ref, source.prior_players_path)
    prior_parts = []
    for gw in source.prior_gameweeks:
        frame = reader.csv(source.feature_ref, source.prior_stats_template.format(gw=gw))
        frame["gw"] = gw
        prior_parts.append(frame)
    prior_rows = pd.concat(prior_parts, ignore_index=True)
    prior_role = aggregate_prior_role(current_players, prior_players, prior_rows)

    preseason_role = aggregate_preseason_role(
        current_players, preseason_matches, preseason_stats
    )
    incumbent_players, incumbent_profile = _prepare_incumbent_inputs(
        current_players,
        prior_role,
        preseason_stats,
        predeadline_playerstats=predeadline_playerstats,
    )
    challenger = decomposed_minutes_challenger(
        incumbent_players, incumbent_profile, prior_role, preseason_role
    )

    outcome_parts = []
    for gw in source.outcome_gameweeks:
        frame = reader.csv(source.outcome_ref, source.outcome_stats_template.format(gw=gw))
        frame["gw"] = gw
        outcome_parts.append(frame)
    outcome_rows = pd.concat(outcome_parts, ignore_index=True)
    outcomes = aggregate_outcomes(current_players, outcome_rows, source.outcome_gameweeks)

    incumbent = incumbent_profile.reset_index(drop=True).copy()
    incumbent["player_id"] = incumbent_players["player_id"].to_numpy()
    baseline = incumbent_players[["player_id"]].merge(
        prior_role, on="player_id", how="left"
    )
    baseline["incumbent_minutes_if_start"] = pd.to_numeric(
        baseline["prior_minutes_if_start"], errors="coerce"
    ).fillna(72.0).clip(45, 90)
    baseline["incumbent_minutes_if_sub"] = pd.to_numeric(
        baseline["prior_minutes_if_sub"], errors="coerce"
    ).fillna(18.0).clip(1, 45)

    player_predictions = incumbent_players[["player_id"]].copy()
    player_predictions = player_predictions.merge(
        incumbent[
            [
                "player_id",
                "expected_minutes",
                "start_probability",
                "appearance_probability",
                "availability_probability",
            ]
        ],
        on="player_id",
        how="left",
    ).rename(
        columns={
            "expected_minutes": "incumbent_expected_minutes",
            "start_probability": "incumbent_start_probability",
            "appearance_probability": "incumbent_appearance_probability",
        }
    )
    player_predictions["incumbent_bench_appearance_probability"] = (
        0.52
        * pd.to_numeric(
            player_predictions["availability_probability"], errors="coerce"
        ).fillna(1)
    ).clip(0, 1)
    player_predictions = player_predictions.merge(
        baseline[
            ["player_id", "incumbent_minutes_if_start", "incumbent_minutes_if_sub"]
        ],
        on="player_id",
        how="left",
    ).merge(challenger, on="player_id", how="left")

    scored = outcomes.merge(player_predictions, on="player_id", how="inner")
    player_context = (
        current_players[["player_id"]]
        .drop_duplicates("player_id")
        .merge(prior_role, on="player_id", how="left")
        .merge(preseason_role, on="player_id", how="left")
    )
    cohorts = _cohort_labels(player_context)
    scored = scored.merge(cohorts, on="player_id", how="left")

    metrics = score_minutes_models(scored)
    cohort_metrics = {}
    for cohort in [
        "established_returning_starter",
        "rotation_prior",
        "repeated_preseason_starter",
        "cameo_only",
        "no_prior_role",
    ]:
        subset = scored[scored[cohort].fillna(False)]
        if not subset.empty:
            cohort_metrics[cohort] = score_minutes_models(subset)

    return (
        {
            "season": source.season,
            "feature_ref": source.feature_ref,
            "feature_timestamp": source.feature_timestamp,
            "outcome_ref": source.outcome_ref,
            "outcome_gameweeks": list(source.outcome_gameweeks),
            "row_semantics": {
                "appearance": "minutes_played > 0",
                "start": "minutes_played > 0 and start_min <= 1",
            },
            "metrics": metrics,
            "conditional_minutes_baseline": (
                "incumbent conditional-minute columns use the historical prior component "
                "because production does not expose a generative starter/substitute decomposition"
            ),
            "cohorts": cohort_metrics,
            "preseason_return_evidence": _preseason_return_coverage(preseason_stats),
        },
        scored,
    )


def run_historical_minutes_audit(
    core_root: Path,
    manifest_path: Path,
) -> dict:
    sources, minimum_seasons = load_source_manifest(manifest_path)
    reader = GitCoreReader(core_root)
    season_results = []
    scored_frames = []
    for source in sources:
        result, scored = audit_historical_season(reader, source)
        season_results.append(result)
        scored["season"] = source.season
        scored_frames.append(scored)

    valid_seasons = len(season_results)
    combined = (
        score_minutes_models(pd.concat(scored_frames, ignore_index=True))
        if scored_frames
        else {}
    )
    deltas = combined.get("delta_challenger_minus_incumbent", {})
    key_metrics = [
        "start_brier",
        "start_calibration_ece",
        "bench_appearance_brier",
        "minutes_mae",
        "minutes_rmse",
    ]
    wins = [key for key in key_metrics if deltas.get(key, np.inf) < 0]
    losses = [key for key in key_metrics if deltas.get(key, -np.inf) > 0]
    if losses:
        shadow_result = "challenger_mixed_or_worse"
    elif len(wins) == len(key_metrics):
        shadow_result = "challenger_improves_all_primary_metrics"
    else:
        shadow_result = "challenger_inconclusive"

    blockers = []
    if valid_seasons < minimum_seasons:
        blockers.append(
            f"only {valid_seasons} independent preseason season(s) available; "
            f"{minimum_seasons} required for production promotion"
        )

    return _json_safe(
        {
            "contract": "apex-historical-minutes-preseason-audit-v1",
            "source_manifest": str(manifest_path),
            "independent_seasons": valid_seasons,
            "minimum_independent_seasons_for_promotion": minimum_seasons,
            "row_semantics": {
                "appearance": "minutes_played > 0",
                "start": "minutes_played > 0 and start_min <= 1",
            },
            "shadow_result": shadow_result,
            "promotion_allowed": False,
            "blockers": blockers
            + [
                "audit is shadow-only; production minutes and preseason attacking rates are unchanged"
            ],
            "combined_metrics": combined,
            "seasons": season_results,
        }
    )