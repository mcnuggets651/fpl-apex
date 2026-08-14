#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

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


def _load_core_source(client: FPLCoreClient, force: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        return client.playerstats(force=force), client.players(force=force)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        # FPL Core 2024/25 is stored in the older split-directory layout.
        return (
            client._csv("playerstats/playerstats.csv", force),
            client._csv("players/players.csv", force),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-season", type=int, default=2024)
    parser.add_argument("--target-season", type=int, default=2025)
    parser.add_argument("--minimum-minutes", type=float, default=450.0)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output",
        default="reports/understat_player_predictive_audit.json",
    )
    args = parser.parse_args()
    if args.target_season != args.source_season + 1:
        raise SystemExit("target season must be exactly one year after source season")

    settings = load_settings()
    http = CachedHttp(settings.cache_dir)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    if not core_pin:
        raise SystemExit("FPL Core pin is required for reproducible player audit")

    source_understat = normalise_understat_players(
        fetch_understat_season(
            args.source_season,
            cache_dir=settings.cache_dir / "understat",
            refresh=args.force,
        ),
        args.source_season,
    )
    target_understat = normalise_understat_players(
        fetch_understat_season(
            args.target_season,
            cache_dir=settings.cache_dir / "understat",
            refresh=args.force,
        ),
        args.target_season,
    )
    client = FPLCoreClient(http, _season_label(args.source_season), ref=core_pin)
    core_stats, core_players = _load_core_source(client, args.force)
    core = latest_core_player_rates(
        core_stats,
        core_players,
        args.source_season,
    )
    source = match_core_understat(core, source_understat)
    target = target_understat[
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
    if panel.empty:
        raise SystemExit("no matched no-hindsight player rows were produced")

    # Predeclared deterministic player split. Both sets use 2024/25 information
    # to predict 2025/26 outcomes, but holdout outcomes never tune the weight.
    panel["audit_split"] = panel["understat_player_id"].map(
        lambda value: "holdout" if int(value) % 2 == 0 else "calibration"
    )
    panel["source_season"] = args.source_season
    panel["target_season"] = args.target_season
    audit = calibrate_understat_player_blend(
        panel,
        bootstrap_samples=args.bootstrap_samples,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel_path = output_path.with_name("understat_player_predictive_panel.csv")
    calibration_path = output_path.with_name("understat_player_weight_grid.csv")
    panel.to_csv(panel_path, index=False)
    audit.calibration.to_csv(calibration_path, index=False)
    payload = {
        "contract": "apex-understat-player-predictive-audit-v2",
        "production_changed": False,
        "method": (
            "End-of-2024/25 FPL Core and Understat xG/xA rates predict 2025/26 actual "
            "goals/assists. Understat player ID parity deterministically partitions eligible "
            "players into calibration and untouched holdout cohorts before weight fitting."
        ),
        "core_pin": core_pin,
        "source_season": args.source_season,
        "target_season": args.target_season,
        "minimum_source_and_target_minutes": args.minimum_minutes,
        "identity_policy": "unique normalized full-name matches only; ambiguity rejected",
        "coverage": {
            "core_source_rows": int(len(core)),
            "understat_source_rows": int(len(source_understat)),
            "cross_source_matched_rows": int(len(source)),
            "eligible_forward_rows": int(len(panel)),
            "calibration_rows": int((panel["audit_split"] == "calibration").sum()),
            "holdout_rows": int((panel["audit_split"] == "holdout").sum()),
        },
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
