#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.config import load_settings
from apex_fpl.data.understat import load_understat_history, season_start_year
from apex_fpl.evaluation.team_goals import run_team_goal_walk_forward


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward evaluation for Apex team goals")
    parser.add_argument("--out", default="reports/team_goals")
    parser.add_argument("--refresh-active", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    active = season_start_year(settings.season)
    first = max(2018, active - settings.understat_history_seasons)
    history = load_understat_history(
        range(first, active + 1),
        active_season=active,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=args.refresh_active,
    )
    result = run_team_goal_walk_forward(history.matches)
    if result.summary.empty:
        raise SystemExit("team-goal evaluation produced no chronological folds")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result.predictions.to_csv(out / "walk_forward_predictions.csv", index=False)
    result.summary.to_csv(out / "walk_forward_summary.csv", index=False)
    result.ablation.to_csv(out / "feature_ablation.csv", index=False)

    mean = result.summary.groupby("model")[["goal_mae", "poisson_loss", "clean_sheet_brier"]].mean()
    model = mean.loc["model"]
    baseline = mean.loc["baseline"]
    metrics = ("goal_mae", "poisson_loss", "clean_sheet_brier")
    ablation_mean = result.ablation.groupby("variant")[list(metrics)].mean()
    fold_pairs = result.summary.pivot(index="season", columns="model", values=list(metrics))
    beats_every_fold = {
        metric: bool((fold_pairs[(metric, "model")] < fold_pairs[(metric, "baseline")]).all())
        for metric in metrics
    }
    evidence = {
        "method": "expanding-season-no-hindsight",
        "model_version": "understat_time_decay_v1",
        "pre_registered_configuration": {
            "half_life_days": 240.0,
            "prior_matches": 10.0,
        },
        "completed_seasons": list(history.completed_seasons),
        "folds": int(result.summary["season"].nunique()),
        "model": model.to_dict(),
        "league_average_baseline": baseline.to_dict(),
        "beats_baseline": {
            metric: bool(model[metric] < baseline[metric])
            for metric in metrics
        },
        "beats_baseline_in_every_fold": beats_every_fold,
        "ablation_mean": {
            str(variant): {metric: float(row[metric]) for metric in metrics}
            for variant, row in ablation_mean.iterrows()
        },
        "promotion_gate": {
            "chronological_out_of_sample": True,
            "three_completed_test_seasons": int(result.summary["season"].nunique()) >= 3,
            "beats_baseline_all_metrics": all(model[metric] < baseline[metric] for metric in metrics),
            "beats_baseline_every_fold": all(beats_every_fold.values()),
            "gameweek_block_bootstrap": False,
            "decision_regret_non_degradation": False,
            "leave_one_source_out_stability": False,
            "passed": False,
        },
        "promotion_reason": (
            "Keep in shadow mode: the forecast backtest is encouraging, but the "
            "pre-registered time-decay configuration did not dominate its ablations "
            "and the required bootstrap, decision-regret and source-removal gates "
            "have not run."
        ),
        "auto_promoted": False,
    }
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
