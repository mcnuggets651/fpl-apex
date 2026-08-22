#!/usr/bin/env python3
"""Run pinned AIrsenal predictions and export the official-FPL-ID contract.

A row existing in an upstream file is not the same thing as the upstream supplying
an opinion. In particular, an all-zero surface for an entire current Premier League
club is treated as a structural abstention rather than 100% expert coverage. The raw
rows remain present for provenance, while explicit support metadata lets Apex apply
its governed fallback without fabricating an AIrsenal forecast.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

from datetime import datetime, timezone


BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
ROOT = Path(__file__).resolve().parents[1]
ZERO_TOLERANCE = 1e-12


class OfficialHorizon:
    """Rich official horizon context with backwards-compatible two-value unpacking.

    This deliberately remains a plain class rather than a dataclass. The worker is
    imported by regression tests through ``importlib.util.module_from_spec`` without
    registering the temporary module in ``sys.modules``; Python 3.12 dataclasses with
    postponed annotations inspect that registry during class creation. A data holder
    should not make the production script dependent on a loader implementation detail.
    """

    __slots__ = ("gameweeks", "official_ids", "player_teams", "team_names")

    def __init__(
        self,
        gameweeks: list[int],
        official_ids: set[int],
        player_teams: dict[int, int],
        team_names: dict[int, str],
    ) -> None:
        self.gameweeks = gameweeks
        self.official_ids = official_ids
        self.player_teams = player_teams
        self.team_names = team_names

    # Preserve the historical two-value helper contract for tests/consumers while
    # exposing richer official context to the production worker.
    def __iter__(self):
        yield self.gameweeks
        yield self.official_ids

    def __eq__(self, other):
        if isinstance(other, tuple) and len(other) == 2:
            return (self.gameweeks, self.official_ids) == other
        if isinstance(other, OfficialHorizon):
            return (
                self.gameweeks == other.gameweeks
                and self.official_ids == other.official_ids
                and self.player_teams == other.player_teams
                and self.team_names == other.team_names
            )
        return False


def _actionable_gameweeks(
    events: list[dict], horizon: int, *, now: datetime | None = None
) -> list[int]:
    """Match Apex's deadline-aware horizon without crossing the season boundary."""
    now = now or datetime.now(timezone.utc)
    open_ids = []
    for event in events:
        deadline = event.get("deadline_time")
        if not deadline:
            continue
        parsed = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        if parsed > now:
            open_ids.append(int(event["id"]))
    if open_ids:
        return sorted(open_ids)[:horizon]

    # Keep a defensive fallback for upstream/bootstrap fixtures without deadlines.
    # Select only real official events: range(start, start+horizon) would fabricate
    # Gameweeks at the end of the season.
    unfinished = sorted(
        int(event["id"]) for event in events if not event.get("finished", False)
    )
    return unfinished[:horizon]


def _official_horizon(horizon: int) -> OfficialHorizon:
    request = urllib.request.Request(
        BOOTSTRAP_URL,
        headers={"User-Agent": "apex-fpl-airsenal-worker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    gameweeks = _actionable_gameweeks(payload["events"], horizon)
    if not gameweeks:
        raise SystemExit("No actionable official FPL Gameweeks remain")
    if gameweeks != list(range(gameweeks[0], gameweeks[-1] + 1)):
        raise SystemExit(f"Official FPL returned a non-contiguous horizon: {gameweeks}")
    official_ids = {int(player["id"]) for player in payload["elements"]}
    player_teams = {
        int(player["id"]): int(player["team"])
        for player in payload["elements"]
        if player.get("team") is not None
    }
    team_names = {
        int(team["id"]): str(team.get("name") or team["id"])
        for team in payload.get("teams", [])
    }
    return OfficialHorizon(gameweeks, official_ids, player_teams, team_names)


def _airsenal_pin() -> str:
    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
    return str(lock["sources"]["airsenal"]["commit"])


def _read_export(output: Path) -> tuple[list[dict[str, str]], list[str]]:
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return rows, fields


def _assert_export_contract(
    output: Path, official_ids: set[int], requested_gameweeks: list[int]
) -> None:
    rows, _ = _read_export(output)
    if not rows:
        raise SystemExit("AIrsenal export is empty")
    exported = {int(row["player_id"]) for row in rows}
    unknown = sorted(exported - official_ids)
    if unknown:
        raise SystemExit(f"AIrsenal export contains unknown official FPL IDs: {unknown[:10]}")

    requested = {int(gw) for gw in requested_gameweeks}
    covered = {int(row["gw"]) for row in rows}
    missing = sorted(requested - covered)
    if missing:
        raise SystemExit(f"AIrsenal export is missing requested Gameweeks: {missing}")

    # The production worker promises a complete raw official-player/GW matrix.
    # Semantic abstentions are represented explicitly later; missing rows are never
    # allowed to masquerade as abstentions or as zero forecasts.
    requested_rows = [row for row in rows if int(row["gw"]) in requested]
    pairs = {(int(row["player_id"]), int(row["gw"])) for row in requested_rows}
    expected = {(int(pid), int(gw)) for pid in official_ids for gw in requested}
    missing_pairs = sorted(expected - pairs)
    if missing_pairs:
        raise SystemExit(
            "AIrsenal export is not a complete official player/Gameweek matrix; "
            f"missing pairs include {missing_pairs[:10]}"
        )
    if len(pairs) != len(requested_rows):
        raise SystemExit("AIrsenal export contains duplicate official player/Gameweek rows")


def _annotate_semantic_support(
    output: Path,
    player_teams: dict[int, int],
    team_names: dict[int, str],
    requested_gameweeks: list[int],
) -> dict[int, str]:
    """Mark impossible whole-club zero surfaces as explicit upstream abstentions.

    A real FPL forecast may legitimately be zero for a bench player. It is not a
    credible independent forecast for every registered player at one club to be zero
    across the complete multi-week horizon. That shape means the upstream lacks a
    usable model surface for the club (for example, a newly promoted team not yet
    represented by the model). We preserve raw xP but declare those rows unsupported.
    """
    rows, fields = _read_export(output)
    requested = {int(gw) for gw in requested_gameweeks}
    by_team: dict[int, list[float]] = {}
    for row in rows:
        if int(row["gw"]) not in requested:
            continue
        pid = int(row["player_id"])
        team = player_teams.get(pid)
        if team is None:
            raise SystemExit(f"Official team mapping missing for AIrsenal player {pid}")
        try:
            value = float(row["xp"])
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"AIrsenal export contains invalid xP for player {pid}") from exc
        by_team.setdefault(team, []).append(value)

    abstentions: dict[int, str] = {}
    for team, values in by_team.items():
        if values and all(abs(float(value)) <= ZERO_TOLERANCE for value in values):
            abstentions[team] = team_names.get(team, str(team))

    support_field = "source_supported"
    reason_field = "support_reason"
    out_fields = [field for field in fields if field not in {support_field, reason_field}]
    out_fields.extend([support_field, reason_field])
    for row in rows:
        team = player_teams.get(int(row["player_id"]))
        supported = team not in abstentions
        row[support_field] = "true" if supported else "false"
        row[reason_field] = (
            "" if supported else f"structural_all_zero_team_surface:{abstentions[team]}"
        )

    tmp = output.with_suffix(output.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(output)
    return abstentions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate genuine pinned AIrsenal forecasts for the live FPL horizon."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.horizon < 1:
        parser.error("--horizon must be positive")
    if not args.db.is_file() or args.db.stat().st_size == 0:
        raise SystemExit(f"AIrsenal database is missing or empty: {args.db}")

    context = _official_horizon(args.horizon)
    # Tests and external callers may still monkeypatch the historical two-tuple
    # helper. Production receives OfficialHorizon and therefore exact team context.
    if isinstance(context, OfficialHorizon):
        gameweeks = context.gameweeks
        official_ids = context.official_ids
        player_teams = context.player_teams
        team_names = context.team_names
    else:
        gameweeks, official_ids = context
        player_teams = {int(pid): 0 for pid in official_ids}
        team_names = {0: "unknown-team"}

    start = gameweeks[0]
    # Pinned AIrsenal's gameweek_end is exclusive (Python range semantics).
    end_exclusive = gameweeks[-1] + 1
    env = {
        **os.environ,
        "AIRSENAL_DB_FILE": str(args.db.resolve()),
        "AIRSENAL_SOURCE_VERSION": _airsenal_pin(),
    }
    subprocess.run(
        [
            "airsenal_run_prediction",
            "--gameweek_start",
            str(start),
            "--gameweek_end",
            str(end_exclusive),
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_airsenal.py"),
            str(args.db),
            "LATEST",
            str(args.output),
        ],
        check=True,
        env=env,
    )
    _assert_export_contract(args.output, official_ids, gameweeks)
    abstentions = _annotate_semantic_support(
        args.output,
        player_teams,
        team_names,
        gameweeks,
    )
    if abstentions:
        names = ", ".join(abstentions[team] for team in sorted(abstentions))
        print(
            "AIrsenal semantic abstention detected for structurally all-zero club "
            f"surface(s): {names}. Raw rows retained; Apex fallback will be explicit."
        )
    print(
        f"Generated genuine AIrsenal forecast for GW{start}-GW{gameweeks[-1]} "
        f"with pinned source {_airsenal_pin()}"
    )


if __name__ == "__main__":
    main()
