#!/usr/bin/env python3
"""Generate transparent projection decomposition and Understat shadow audits.

This script is diagnostic only. It never changes the canonical recommendation,
fixture-model mode or optimiser objective.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.data.understat import load_understat_history, season_start_year
from apex_fpl.models.fixtures import fixture_multipliers
from apex_fpl.models.team_goals import build_team_goal_surface, build_team_ratings
from apex_fpl.services.data_quality import official_strength_is_usable
from apex_fpl.services.pipeline import run_pipeline
from apex_fpl.services.projection_audit import (
    build_fixture_shadow_comparison,
    build_player_shadow_comparison,
    build_projection_decomposition,
    reprice_apex_for_fixture_shadow,
)
from apex_fpl.services.provenance import load_upstream_pins


def _with_names(frame: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    keep = [
        col
        for col in ["player_id", "web_name", "team_name", "position", "price"]
        if col in players.columns
    ]
    return frame.merge(
        players[keep].drop_duplicates("player_id"),
        on="player_id",
        how="left",
        validate="one_to_one",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    decomposition = build_projection_decomposition(
        out.projections,
        out.gameweeks,
        decay=settings.fixture_decay,
    )
    decomposition = _with_names(decomposition, out.players)
    decomposition.to_csv(output_dir / "player_projection_decomposition.csv", index=False)

    http = CachedHttp(settings.cache_dir)
    official = OfficialFPLClient(http).snapshot(force=False)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    core = FPLCoreClient(http, settings.season, ref=core_pin or "main")
    try:
        core_elos = core.fixture_elos(out.gameweeks, force=args.force)
    except Exception:
        core_elos = pd.DataFrame()
    strength_ok, _ = official_strength_is_usable(official.teams)

    # Reconstruct the current production fixture surface. In the default shadow
    # configuration this is official strength when usable, otherwise league
    # baselines plus reconciled FPL Core Elo.
    production_fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        out.gameweeks,
        core_elos=core_elos,
        use_official_strength=strength_ok,
        team_goal_surface=None,
    )

    active_year = season_start_year(settings.season)
    first_year = max(2018, active_year - settings.understat_history_seasons)
    history = load_understat_history(
        range(first_year, active_year + 1),
        active_season=active_year,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=args.force,
    )
    ratings = build_team_ratings(history.matches, official.teams)
    shadow_surface = build_team_goal_surface(
        official.fixtures,
        ratings,
        out.gameweeks,
    )
    # The shadow comparison intentionally excludes Elo so Understat/xG remains an
    # independent challenger rather than double-counting the same team-strength
    # information that production currently receives through Elo.
    shadow_fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        out.gameweeks,
        core_elos=None,
        use_official_strength=False,
        team_goal_surface=shadow_surface,
    )

    fixture_audit = build_fixture_shadow_comparison(production_fx, shadow_fx)
    team_names = official.teams[["id", "name"]].drop_duplicates("id")
    fixture_audit = fixture_audit.merge(
        team_names.rename(columns={"id": "team", "name": "team_name"}),
        on="team",
        how="left",
    ).merge(
        team_names.rename(columns={"id": "opponent", "name": "opponent_name"}),
        on="opponent",
        how="left",
    )
    fixture_audit.to_csv(output_dir / "fixture_shadow_comparison.csv", index=False)

    # Reprice only the two fixture-sensitive Apex components from the already
    # computed production projection. This is exact for the current player model
    # and avoids treating the slim report-facing ``out.players`` table as raw
    # modelling input.
    player_teams = official.players[["player_id", "team"]].drop_duplicates("player_id")
    shadow_apex = reprice_apex_for_fixture_shadow(
        out.projections,
        production_fx,
        shadow_fx,
        player_teams,
    )
    player_shadow = build_player_shadow_comparison(
        out.projections,
        shadow_apex,
        out.gameweeks,
        decay=settings.fixture_decay,
    )
    player_shadow = _with_names(player_shadow, out.players)
    player_shadow.to_csv(output_dir / "player_fixture_shadow_comparison.csv", index=False)

    canonical_path = Path("data/generated/apex_recommendation_latest.json")
    selected_ids: set[int] = set()
    if canonical_path.exists():
        try:
            payload = json.loads(canonical_path.read_text(encoding="utf-8"))
            selected_ids = {
                int(row["player_id"])
                for row in payload.get("recommendation", {}).get("squad", [])
                if row.get("player_id") is not None
            }
        except Exception:
            selected_ids = set()
    if selected_ids and not player_shadow.empty:
        player_shadow["selected_in_canonical_baseline"] = player_shadow["player_id"].isin(
            selected_ids
        )
        player_shadow.to_csv(output_dir / "player_fixture_shadow_comparison.csv", index=False)

    summary = {
        "contract": "apex-projection-shadow-audit-v1",
        "production_selection_changed": False,
        "gameweeks": out.gameweeks,
        "understat_completed_seasons": history.completed_seasons,
        "understat_warnings": history.warnings,
        "largest_player_shadow_xp_increases": (
            player_shadow.nlargest(20, "delta_apex_xp_raw").to_dict("records")
            if "delta_apex_xp_raw" in player_shadow.columns
            else []
        ),
        "largest_player_shadow_xp_decreases": (
            player_shadow.nsmallest(20, "delta_apex_xp_raw").to_dict("records")
            if "delta_apex_xp_raw" in player_shadow.columns
            else []
        ),
    }
    (output_dir / "projection_shadow_audit.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(output_dir / "projection_shadow_audit.json")


if __name__ == "__main__":
    main()
