from __future__ import annotations

import argparse
import math
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apex.runtime.config import CURRENT_SCORING_RULES_VERSION
from apex.sources.official import fetch_official_snapshot
from apex_fpl.config import load_settings
from apex_fpl.services.pipeline import run_pipeline

MODEL_ID = "apex_proprietary"
MODEL_VERSION = "apex-proprietary-v1"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _target_gameweeks(official, now: datetime, horizon: int) -> list[int]:
    future = [
        int(gameweek)
        for gameweek, deadline in official.deadlines.items()
        if _parse_utc(deadline) > now
    ]
    return sorted(future)[: int(horizon)]


def _fixture_count(official, element_id: int, gameweek: int) -> int:
    player = official.player_map()[int(element_id)]
    return sum(
        1
        for fixture in official.fixtures
        if fixture.gameweek == int(gameweek)
        and player.team_id in {fixture.home_team_id, fixture.away_team_id}
    )


def _export_raw_apex(
    projections: pd.DataFrame,
    players: pd.DataFrame,
    *,
    official,
    gameweeks: list[int],
    generated_at: str,
    code_sha: str,
) -> pd.DataFrame:
    """Build one raw proprietary xP row per Official player/GW.

    `apex_xp` is computed before the legacy ensemble step. This exporter never
    reads canonical_ev_xp, risk_adjusted_xp, AIrsenal, Official EP, or market xP.
    """
    required = {"player_id", "gw", "apex_xp"}
    missing = sorted(required - set(projections.columns))
    if missing:
        raise RuntimeError(f"raw Apex projection output missing columns: {missing}")

    raw = projections[["player_id", "gw", "apex_xp"]].copy()
    raw["player_id"] = pd.to_numeric(raw["player_id"], errors="raise").astype(int)
    raw["gw"] = pd.to_numeric(raw["gw"], errors="raise").astype(int)
    raw["apex_xp"] = pd.to_numeric(raw["apex_xp"], errors="coerce")
    raw = raw[raw["gw"].isin(gameweeks)]
    grouped = raw.groupby(["player_id", "gw"], as_index=False)["apex_xp"].sum()

    context_columns = [
        column
        for column in (
            "player_id",
            "expected_minutes",
            "appearance_probability",
            "start_probability",
            "minutes_60_plus_probability",
        )
        if column in players.columns
    ]
    context = players[context_columns].drop_duplicates("player_id").set_index("player_id")
    by_key = grouped.set_index(["player_id", "gw"])["apex_xp"]

    rows: list[dict] = []
    for element_id in sorted(official.player_ids):
        for gameweek in gameweeks:
            key = (int(element_id), int(gameweek))
            if key not in by_key.index:
                raise RuntimeError(
                    f"raw Apex projection missing Official player/GW row: {element_id}/GW{gameweek}"
                )
            expected_points = float(by_key.loc[key])
            if not math.isfinite(expected_points) or expected_points < -1e-9:
                raise RuntimeError(
                    f"raw Apex projection invalid for {element_id}/GW{gameweek}: {expected_points}"
                )
            fixtures = _fixture_count(official, element_id, gameweek)
            player_context = context.loc[element_id] if element_id in context.index else None

            def value(name: str):
                if player_context is None or name not in context.columns:
                    return None
                candidate = player_context[name]
                if pd.isna(candidate):
                    return None
                return float(candidate)

            per_match_minutes = value("expected_minutes")
            rows.append(
                {
                    "element_id": int(element_id),
                    "gameweek": int(gameweek),
                    "expected_points": max(expected_points, 0.0),
                    "expected_minutes": (
                        max(per_match_minutes, 0.0) * fixtures
                        if per_match_minutes is not None
                        else None
                    ),
                    "p_appearance": value("appearance_probability") if fixtures == 1 else None,
                    "p_start": value("start_probability") if fixtures == 1 else None,
                    "p_60": value("minutes_60_plus_probability") if fixtures == 1 else None,
                    "coverage_status": "FORECAST",
                    "generated_at": generated_at,
                    "provider_version": f"{MODEL_VERSION}@{code_sha[:12]}",
                    "scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
                    "source_snapshot": official.source_hash,
                    "model_contract": "RAW_APEX_XP_ONLY_V1",
                }
            )
    return pd.DataFrame(rows)


def acquire(args: argparse.Namespace) -> dict:
    now = datetime.now(timezone.utc)
    official_before, _ = fetch_official_snapshot(season=args.season)
    if args.expected_official_hash and official_before.source_hash != args.expected_official_hash:
        raise RuntimeError(
            "Official FPL authority changed before Apex proprietary acquisition: "
            f"expected {args.expected_official_hash}, got {official_before.source_hash}"
        )
    gameweeks = _target_gameweeks(official_before, now, args.horizon)
    if not gameweeks:
        raise RuntimeError("no future Official FPL deadlines for Apex proprietary shadow")

    # Keep the legacy engine isolated and turn off every external forecast/blend vote.
    # The worker exports only project_players(...).apex_xp, computed before the
    # legacy blend. News is disabled here because V2 owns the canonical evidence
    # layer; verified manual role files may still act as factual football context.
    settings = replace(
        load_settings(),
        season=args.season,
        horizon=args.horizon,
        weights={
            "official_ep": 0.0,
            "apex_model": 1.0,
            "airsenal": 0.0,
            "market": 0.0,
        },
        airsenal_csv=None,
        odds_api_key=None,
        odds_api_url=None,
        news_feeds=[],
        news_sources=[],
        fpl_entry_id=None,
        required_sources=[],
        understat_enabled=True,
        understat_team_model_mode="production",
        report_dir=Path(args.workdir) / "legacy-reports",
        snapshot_dir=Path(args.workdir) / "legacy-snapshots",
    )
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)

    previous_player_mode = os.environ.get("APEX_UNDERSTAT_PLAYER_MODEL_MODE")
    os.environ["APEX_UNDERSTAT_PLAYER_MODEL_MODE"] = "production"
    try:
        result = run_pipeline(
            settings,
            horizon=args.horizon,
            scenario="shadow-only",
            force=True,
            plan_transfers=False,
        )
    finally:
        if previous_player_mode is None:
            os.environ.pop("APEX_UNDERSTAT_PLAYER_MODEL_MODE", None)
        else:
            os.environ["APEX_UNDERSTAT_PLAYER_MODEL_MODE"] = previous_player_mode

    if list(map(int, result.gameweeks)) != gameweeks:
        raise RuntimeError(
            f"legacy raw Apex horizon mismatch: {result.gameweeks} != {gameweeks}"
        )

    official_after, _ = fetch_official_snapshot(season=args.season)
    if official_after.source_hash != official_before.source_hash:
        raise RuntimeError("Official FPL authority changed during Apex proprietary acquisition")

    generated_at = datetime.now(timezone.utc).isoformat()
    frame = _export_raw_apex(
        result.projections,
        result.players,
        official=official_after,
        gameweeks=gameweeks,
        generated_at=generated_at,
        code_sha=args.code_sha,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)

    per_gw = frame.groupby("gameweek")["element_id"].nunique().to_dict()
    if any(int(count) != len(official_after.player_ids) for count in per_gw.values()):
        raise RuntimeError("Apex proprietary export does not cover every Official player per GW")
    return {
        "provider_id": MODEL_ID,
        "provider_version": f"{MODEL_VERSION}@{args.code_sha[:12]}",
        "target_gameweek": gameweeks[0],
        "supported_gameweeks": gameweeks,
        "rows": len(frame),
        "players_per_gameweek": per_gw,
        "source_snapshot": official_after.source_hash,
        "raw_contract": "RAW_APEX_XP_ONLY_V1",
        "serve_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the isolated, non-serving Apex proprietary xP shadow."
    )
    parser.add_argument("--expected-official-hash", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--output", default="acquisition/providers/apex_proprietary.csv")
    parser.add_argument("--workdir", default="artifacts/v2/challengers/apex_proprietary")
    args = parser.parse_args()
    if args.horizon <= 0:
        parser.error("--horizon must be positive")
    report = acquire(args)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
