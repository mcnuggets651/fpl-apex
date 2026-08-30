from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
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
CORE_REPOSITORY = "olbauday/FPL-Core-Insights"
REQUIRED_INTERNAL_SOURCES = frozenset(
    {
        "official_fpl",
        "fpl_core_playerstats",
        "fpl_core_previous_season",
        "understat_team_model",
        "fixture_model",
    }
)


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


def _latest_core_commit(*, now: datetime, max_age_hours: float) -> dict[str, str | float]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{CORE_REPOSITORY}/commits/main",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fpl-apex-proprietary-shadow",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    sha = str(payload.get("sha") or "").strip()
    commit = payload.get("commit") or {}
    committer = commit.get("committer") or {}
    raw_time = str(committer.get("date") or "").strip()
    if len(sha) != 40 or not raw_time:
        raise RuntimeError("latest FPL Core response lacks immutable SHA/timestamp")
    committed = _parse_utc(raw_time)
    age_hours = (now - committed).total_seconds() / 3600.0
    if age_hours < -0.5:
        raise RuntimeError(
            f"latest FPL Core commit timestamp is {abs(age_hours):.1f}h in the future"
        )
    if age_hours > float(max_age_hours):
        raise RuntimeError(
            f"latest FPL Core commit is stale ({age_hours:.1f}h; max {max_age_hours:.1f}h)"
        )
    return {
        "sha": sha,
        "committed_at": committed.isoformat(),
        "age_hours": max(age_hours, 0.0),
    }


def _runtime_core_lock(
    base_lock_path: Path,
    output_path: Path,
    *,
    resolved: dict[str, str | float],
    now: datetime,
) -> Path:
    payload = json.loads(Path(base_lock_path).read_text(encoding="utf-8"))
    sources = payload.setdefault("sources", {})
    current = dict(sources.get("fpl_core_insights") or {})
    current.update(
        {
            "repository": CORE_REPOSITORY,
            "commit": str(resolved["sha"]),
            "committed_at": str(resolved["committed_at"]),
            "resolved_at": now.isoformat(),
            "resolved_age_hours": float(resolved["age_hours"]),
            "newer_revision_available": False,
            "resolution_policy": (
                "run-local latest-main resolution for non-serving Apex proprietary shadow"
            ),
            "role": "enrichment_data",
            "required_for_full_apex": False,
        }
    )
    sources["fpl_core_insights"] = current
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _assert_internal_source_health(sources) -> dict[str, dict[str, str | bool]]:
    by_name = {str(source.name): source for source in sources}
    failures: list[str] = []
    health: dict[str, dict[str, str | bool]] = {}
    for name in sorted(REQUIRED_INTERNAL_SOURCES):
        source = by_name.get(name)
        if source is None:
            failures.append(f"{name}: missing source-health record")
            continue
        health[name] = {
            "ok": bool(source.ok),
            "detail": str(source.detail),
            "version": str(source.version),
        }
        if not bool(source.ok):
            failures.append(f"{name}: {source.detail}")
    if failures:
        raise RuntimeError(
            "Apex proprietary required internal source gate failed: "
            + " | ".join(failures)
        )
    return health


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

    base_settings = load_settings()
    core_resolution = _latest_core_commit(
        now=now,
        max_age_hours=base_settings.max_core_age_hours,
    )
    runtime_lock = _runtime_core_lock(
        base_settings.upstreams_lock_path,
        Path(args.workdir) / "runtime-upstreams.lock.json",
        resolved=core_resolution,
        now=now,
    )

    # Keep the legacy engine isolated and turn off every external forecast/blend vote.
    # The worker exports only project_players(...).apex_xp, computed before the
    # legacy blend. News is disabled here because V2 owns the canonical evidence
    # layer; verified manual role files may still act as factual football context.
    settings = replace(
        base_settings,
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
        upstreams_lock_path=runtime_lock,
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

    source_health = _assert_internal_source_health(result.sources)
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
        "resolved_core": core_resolution,
        "required_internal_sources": sorted(REQUIRED_INTERNAL_SOURCES),
        "internal_source_health": source_health,
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
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
