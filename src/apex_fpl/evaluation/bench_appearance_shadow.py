from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.evaluation.historical_minutes_preseason import (
    GitCoreReader,
    audit_historical_season,
    load_source_manifest,
)

BENCH_METRICS = (
    "appearance_brier",
    "appearance_calibration_ece",
    "bench_appearance_brier",
    "bench_appearance_calibration_ece",
)
ROBUSTNESS_BOOTSTRAP_ITERATIONS = 400
ROBUSTNESS_SEED = 20260815
MIN_RECENT_ROWS = 4000
MIN_RECENT_PLAYERS = 500
KEY_COHORTS = (
    "established_returning_starter",
    "repeated_preseason_starter",
)


def _brier(probability: pd.Series, outcome: pd.Series) -> float:
    p = pd.to_numeric(probability, errors="coerce")
    y = pd.to_numeric(outcome, errors="coerce")
    mask = p.notna() & y.notna()
    return float(np.mean(np.square(p[mask] - y[mask]))) if mask.any() else float("nan")


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
    error = 0.0
    for idx in range(bins):
        use = labels == idx
        if not np.any(use):
            continue
        error += (np.sum(use) / len(p)) * abs(
            float(p.iloc[use].mean()) - float(y.iloc[use].mean())
        )
    return float(error)


def score_bench_appearance_shadow(scored: pd.DataFrame) -> dict:
    """Evaluate only substitute propensity; incumbent start/xMins remain fixed."""

    frame = scored.copy()
    availability = pd.to_numeric(
        frame["availability_probability"], errors="coerce"
    ).fillna(1).clip(0, 1)
    incumbent_start = pd.to_numeric(
        frame["incumbent_start_probability"], errors="coerce"
    ).fillna(0).clip(0, 1)
    role_start = pd.Series(
        np.where(availability > 0, incumbent_start / availability, 0.0),
        index=frame.index,
    ).clip(0, 1)
    role_bench = pd.to_numeric(
        frame["challenger_role_bench_probability"], errors="coerce"
    ).fillna(0.35).clip(0, 1)

    frame["bench_only_appearance_probability"] = (
        (role_start + (1 - role_start) * role_bench) * availability
    ).clip(0, 1)
    frame["bench_only_bench_appearance_probability"] = (
        role_bench * availability
    ).clip(0, 1)

    nonstarters = frame["actual_start"].eq(0)
    incumbent = {
        "appearance_brier": _brier(
            frame["incumbent_appearance_probability"], frame["actual_appearance"]
        ),
        "appearance_calibration_ece": _ece(
            frame["incumbent_appearance_probability"], frame["actual_appearance"]
        ),
        "bench_appearance_brier": _brier(
            frame.loc[nonstarters, "incumbent_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
        "bench_appearance_calibration_ece": _ece(
            frame.loc[nonstarters, "incumbent_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
    }
    shadow = {
        "appearance_brier": _brier(
            frame["bench_only_appearance_probability"], frame["actual_appearance"]
        ),
        "appearance_calibration_ece": _ece(
            frame["bench_only_appearance_probability"], frame["actual_appearance"]
        ),
        "bench_appearance_brier": _brier(
            frame.loc[nonstarters, "bench_only_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
        "bench_appearance_calibration_ece": _ece(
            frame.loc[nonstarters, "bench_only_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
    }
    return {
        "rows": int(len(frame)),
        "players": int(frame["player_id"].nunique()),
        "incumbent": incumbent,
        "bench_only_shadow": shadow,
        "delta_shadow_minus_incumbent": {
            key: float(shadow[key] - incumbent[key]) for key in incumbent
        },
        "start_probability_changed": False,
        "expected_minutes_changed": False,
    }


def _all_metrics_improve(metrics: dict) -> bool:
    deltas = metrics.get("delta_shadow_minus_incumbent", {})
    return bool(deltas) and all(float(deltas.get(key, np.inf)) < 0 for key in BENCH_METRICS)


def _cluster_bootstrap(
    scored: pd.DataFrame,
    cluster_col: str,
    *,
    iterations: int = ROBUSTNESS_BOOTSTRAP_ITERATIONS,
    seed: int = ROBUSTNESS_SEED,
) -> dict:
    clusters = pd.Series(scored[cluster_col].dropna().unique())
    if clusters.empty:
        return {"clusters": 0, "iterations": 0, "metric_delta_ci95": {}}

    groups = {value: scored[scored[cluster_col].eq(value)] for value in clusters.tolist()}
    values = clusters.to_numpy()
    rng = np.random.default_rng(seed)
    draws = {metric: [] for metric in BENCH_METRICS}
    for _ in range(iterations):
        sampled = rng.choice(values, size=len(values), replace=True)
        frame = pd.concat([groups[value] for value in sampled], ignore_index=True)
        deltas = score_bench_appearance_shadow(frame)["delta_shadow_minus_incumbent"]
        for metric in BENCH_METRICS:
            draws[metric].append(float(deltas[metric]))

    return {
        "clusters": int(len(values)),
        "iterations": int(iterations),
        "metric_delta_ci95": {
            metric: {
                "lower": float(np.quantile(samples, 0.025)),
                "median": float(np.quantile(samples, 0.5)),
                "upper": float(np.quantile(samples, 0.975)),
            }
            for metric, samples in draws.items()
        },
    }


def _leave_one_team_out(scored: pd.DataFrame) -> dict:
    teams = sorted(pd.to_numeric(scored["team_code"], errors="coerce").dropna().unique())
    rows = []
    for team in teams:
        subset = scored[~pd.to_numeric(scored["team_code"], errors="coerce").eq(team)]
        metrics = score_bench_appearance_shadow(subset)
        rows.append(
            {
                "omitted_team_code": int(team),
                "rows": int(len(subset)),
                "all_metrics_improve": _all_metrics_improve(metrics),
                "delta_shadow_minus_incumbent": metrics["delta_shadow_minus_incumbent"],
            }
        )
    return {
        "teams": int(len(teams)),
        "all_omissions_improve_all_metrics": bool(rows)
        and all(row["all_metrics_improve"] for row in rows),
        "results": rows,
    }


def _key_cohort_gate(scored: pd.DataFrame) -> dict:
    rows = {}
    for cohort in KEY_COHORTS:
        if cohort not in scored.columns:
            rows[cohort] = {"available": False, "all_metrics_improve": False}
            continue
        subset = scored[scored[cohort].fillna(False)]
        if subset.empty:
            rows[cohort] = {"available": False, "all_metrics_improve": False}
            continue
        metrics = score_bench_appearance_shadow(subset)
        rows[cohort] = {
            "available": True,
            "rows": int(len(subset)),
            "players": int(subset["player_id"].nunique()),
            "all_metrics_improve": _all_metrics_improve(metrics),
            "delta_shadow_minus_incumbent": metrics["delta_shadow_minus_incumbent"],
        }
    return {
        "required_cohorts": list(KEY_COHORTS),
        "all_required_cohorts_improve": all(
            row.get("available") and row.get("all_metrics_improve") for row in rows.values()
        ),
        "cohorts": rows,
    }


def recent_season_robustness_gate(scored: pd.DataFrame) -> dict:
    """Qualify a narrow recent-season challenger for production A/B, never promotion."""

    overall = score_bench_appearance_shadow(scored)
    player_bootstrap = _cluster_bootstrap(scored, "player_id", seed=ROBUSTNESS_SEED)
    team_bootstrap = _cluster_bootstrap(scored, "team_code", seed=ROBUSTNESS_SEED + 1)
    leave_team_out = _leave_one_team_out(scored)
    cohorts = _key_cohort_gate(scored)

    def ci_all_negative(payload: dict) -> bool:
        cis = payload.get("metric_delta_ci95", {})
        return bool(cis) and all(float(cis[key]["upper"]) < 0 for key in BENCH_METRICS)

    checks = {
        "minimum_rows": int(len(scored)) >= MIN_RECENT_ROWS,
        "minimum_players": int(scored["player_id"].nunique()) >= MIN_RECENT_PLAYERS,
        "overall_all_metrics_improve": _all_metrics_improve(overall),
        "player_clustered_ci_all_negative": ci_all_negative(player_bootstrap),
        "team_clustered_ci_all_negative": ci_all_negative(team_bootstrap),
        "leave_one_team_out_all_negative": leave_team_out[
            "all_omissions_improve_all_metrics"
        ],
        "key_cohorts_all_improve": cohorts["all_required_cohorts_improve"],
    }
    eligible = all(checks.values())
    return {
        "contract": "apex-bench-appearance-recent-season-robustness-v1",
        "recent_season_is_sufficient_if_robust": True,
        "minimum_rows": MIN_RECENT_ROWS,
        "minimum_players": MIN_RECENT_PLAYERS,
        "checks": checks,
        "eligible_for_production_ab": eligible,
        "production_ab_required_before_promotion": True,
        "promotion_allowed": False,
        "overall": overall,
        "player_clustered_bootstrap": player_bootstrap,
        "team_clustered_bootstrap": team_bootstrap,
        "leave_one_team_out": leave_team_out,
        "key_cohort_gate": cohorts,
        "blockers": (
            ["production projection/decision A/B has not been run"]
            if eligible
            else [
                "recent-season robustness gate did not pass every required check; "
                "do not promote or run a production challenger"
            ]
        ),
    }


def run_bench_appearance_shadow(core_root: Path, manifest_path: Path) -> dict:
    sources, _minimum_broad_model_seasons = load_source_manifest(manifest_path)
    reader = GitCoreReader(core_root)
    frames = []
    seasons = []
    for source in sources:
        _, scored = audit_historical_season(reader, source)
        current_players = reader.csv(source.feature_ref, source.current_players_path)
        team_map = current_players[["player_id", "team_code"]].drop_duplicates("player_id")
        team_map["player_id"] = pd.to_numeric(team_map["player_id"], errors="coerce")
        team_map = team_map.dropna(subset=["player_id"]).copy()
        team_map["player_id"] = team_map["player_id"].astype(int)
        scored = scored.merge(team_map, on="player_id", how="left", validate="many_to_one")
        scored["season"] = source.season
        frames.append(scored)
        season_result = {
            "season": source.season,
            "metrics": score_bench_appearance_shadow(scored),
            "cohorts": {},
        }
        for cohort in [
            "established_returning_starter",
            "rotation_prior",
            "repeated_preseason_starter",
            "cameo_only",
            "no_prior_role",
        ]:
            subset = scored[scored[cohort].fillna(False)]
            if not subset.empty:
                season_result["cohorts"][cohort] = score_bench_appearance_shadow(subset)
        seasons.append(season_result)

    combined_frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined = score_bench_appearance_shadow(combined_frame) if frames else {}
    improves_all = _all_metrics_improve(combined)
    robustness = recent_season_robustness_gate(combined_frame) if frames else {}
    return {
        "contract": "apex-bench-appearance-shadow-v2",
        "shadow_result": (
            "bench_only_improves_all_appearance_metrics"
            if improves_all
            else "bench_only_mixed_or_worse"
        ),
        "recent_season_robustness": robustness,
        "eligible_for_production_ab": bool(
            robustness.get("eligible_for_production_ab", False)
        ),
        "promotion_allowed": False,
        "blockers": robustness.get("blockers", [])
        + [
            "shadow audit only; production start probability and expected minutes are unchanged"
        ],
        "combined_metrics": combined,
        "seasons": seasons,
    }
