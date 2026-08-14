#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.understat import fetch_understat_season
from apex_fpl.evaluation.understat_players import (
    calibrate_understat_player_blend,
    latest_core_player_rates,
    match_core_understat,
    normalise_understat_players,
)
from apex_fpl.services.provenance import load_upstream_pins


def _season_label(year: int) -> str:
    return f"{year}-{year + 1}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-season", type=int, default=2021)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument("--minimum-minutes", type=float, default=450.0)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output",
        default="reports/understat_player_predictive_audit.json",
    )
    args = parser.parse_args()
    if args.last_season - args.first_season < 3:
        raise SystemExit("need at least four seasons for calibration plus untouched holdout")

    settings = load_settings()
    http = CachedHttp(settings.cache_dir)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    if not core_pin:
        raise SystemExit("FPL Core pin is required for reproducible player audit")

    matched_by_year: dict[int, pd.DataFrame] = {}
    understat_by_year: dict[int, pd.DataFrame] = {}
    coverage: list[dict] = []
    for year in range(args.first_season, args.last_season + 1):
        payload = fetch_understat_season(
            year,
            cache_dir=settings.cache_dir / "understat",
            refresh=args.force,
        )
        understat = normalise_understat_players(payload, year)
        client = FPLCoreClient(http, _season_label(year), ref=core_pin)
        core = latest_core_player_rates(
            client.playerstats(force=args.force),
            client.players(force=args.force),
            year,
        )
        matched = match_core_understat(core, understat)
        understat_by_year[year] = understat
        matched_by_year[year] = matched
        coverage.append(
            {
                "season": year,
                "core_rows": int(len(core)),
                "understat_rows": int(len(understat)),
                "matched_rows": int(len(matched)),
                "core_match_rate": float(len(matched) / len(core)) if len(core) else 0.0,
            }
        )

    panel_parts: list[pd.DataFrame] = []
    for source_year in range(args.first_season, args.last_season):
        source = matched_by_year[source_year].copy()
        target = understat_by_year[source_year + 1][
            ["understat_player_id", "minutes", "goals", "assists"]
        ].rename(
            columns={
                "minutes": "target_minutes",
                "goals": "target_goals",
                "assists": "target_assists",
            }
        )
        panel = source.merge(
            target,
            on="understat_player_id",
            how="inner",
            validate="one_to_one",
        )
        source_understat_minutes = pd.to_numeric(panel["minutes"], errors="coerce")
        source_core_minutes = pd.to_numeric(panel.get("core_minutes"), errors="coerce")
        target_minutes = pd.to_numeric(panel["target_minutes"], errors="coerce")
        eligible = (
            source_understat_minutes.ge(args.minimum_minutes)
            & target_minutes.ge(args.minimum_minutes)
        )
        if source_core_minutes.notna().any():
            eligible &= source_core_minutes.fillna(0).ge(args.minimum_minutes)
        panel = panel[eligible].copy()
        panel["source_season"] = source_year
        panel["target_season"] = source_year + 1
        panel_parts.append(panel)

    if not panel_parts:
        raise SystemExit("no matched no-hindsight player rows were produced")
    panel = pd.concat(panel_parts, ignore_index=True)
    holdout_source_season = args.last_season - 1
    audit = calibrate_understat_player_blend(
        panel,
        holdout_source_season=holdout_source_season,
        bootstrap_samples=args.bootstrap_samples,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel_path = output_path.with_name("understat_player_predictive_panel.csv")
    calibration_path = output_path.with_name("understat_player_weight_grid.csv")
    panel.to_csv(panel_path, index=False)
    audit.calibration.to_csv(calibration_path, index=False)
    payload = {
        "contract": "apex-understat-player-predictive-audit-v1",
        "production_changed": False,
        "method": (
            "End-of-season FPL Core and Understat xG/xA rates predict next-season "
            "actual goals/assists. Blend weights are chosen on earlier source seasons "
            "and evaluated once on the untouched final source-season holdout."
        ),
        "source_seasons": list(range(args.first_season, args.last_season)),
        "holdout_source_season": holdout_source_season,
        "holdout_target_season": args.last_season,
        "minimum_source_and_target_minutes": args.minimum_minutes,
        "identity_policy": "unique normalized full-name matches only; ambiguity rejected",
        "coverage": coverage,
        "selected_xg_understat_weight": audit.selected_xg_weight,
        "selected_xa_understat_weight": audit.selected_xa_weight,
        "holdout": audit.holdout,
        "promotion_gate": {
            "minimum_holdout_rows": 80,
            "combined_nll_delta_must_be_negative": True,
            "bootstrap_ci95_high_must_be_below_zero": True,
            "goal_and_assist_nll_each_may_not_degrade_more_than_fraction": 0.01,
            "nonzero_understat_weight_required": True,
        },
        "pass": audit.pass_gate,
        "recommendation": (
            "eligible_for_bounded_production-blend A/B"
            if audit.pass_gate
            else "remain shadow; do not assign player-level production weight"
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
