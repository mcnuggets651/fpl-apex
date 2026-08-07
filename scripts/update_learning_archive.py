#!/usr/bin/env python3
"""Maintain the no-hindsight Apex deadline learning archive.

Run after a green Pinnacle projection. Before a deadline it saves/refreshes the
next-GW forecast. After a Gameweek is officially finished it attaches official FPL
points. A walk-forward calibration report is then rebuilt from completed archives.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import BASE, OfficialFPLClient
from apex_fpl.services.learning import (
    aggregate_deadline_forecast,
    attach_actual_points,
    build_learning_report,
    load_completed_archive,
    parse_event_live_points,
    write_learning_report,
)


def _deadline(row: pd.Series) -> pd.Timestamp | None:
    value = pd.to_datetime(row.get("deadline_time"), utc=True, errors="coerce")
    return None if pd.isna(value) else value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--archive", default="data/history/deadlines")
    parser.add_argument("--calibration", default="data/generated/calibration_report.json")
    parser.add_argument("--capture-hours", type=float, default=30.0)
    args = parser.parse_args()

    report_dir = Path(args.reports)
    archive_dir = Path(args.archive)
    calibration_path = Path(args.calibration)
    archive_dir.mkdir(parents=True, exist_ok=True)

    latest_path = report_dir / "latest.json"
    projections_path = report_dir / "projections.csv"
    players_path = report_dir / "players.csv"
    if not latest_path.exists() or not projections_path.exists() or not players_path.exists():
        raise SystemExit("run the green Apex/Pinnacle pipeline before updating learning archive")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    if latest.get("safe_to_act") is not True or latest.get("full_apex_ready") is not True:
        raise SystemExit("refusing to archive a deadline forecast from a non-green production run")

    settings = load_settings()
    http = CachedHttp(settings.cache_dir)
    official = OfficialFPLClient(http).snapshot(force=True)
    projections = pd.read_csv(projections_path)
    players = pd.read_csv(players_path)
    now = datetime.now(timezone.utc)
    now_ts = pd.Timestamp(now)

    # Capture only a genuine pre-deadline snapshot. Repeated six-hour runs overwrite
    # the same GW file, so the final archive is the freshest validated forecast that
    # existed before the lock rather than an arbitrary early-week estimate.
    future = []
    for _, row in official.events.iterrows():
        deadline = _deadline(row)
        if deadline is not None and deadline > now_ts:
            future.append((deadline, int(row["id"])))
    if future:
        deadline, gw = min(future)
        hours = (deadline - now_ts).total_seconds() / 3600.0
        if 0.0 < hours <= float(args.capture_hours):
            frame = aggregate_deadline_forecast(
                projections,
                players,
                gw,
                generated_at=str(latest.get("generated_at", now.isoformat())),
                snapshot_id=str((latest.get("official_snapshot") or {}).get("snapshot_id", "")),
            )
            path = archive_dir / f"gw{gw:02d}_forecast.csv"
            frame.to_csv(path, index=False)
            metadata = {
                "gw": gw,
                "deadline_time": deadline.isoformat(),
                "captured_at": now.isoformat(),
                "hours_before_deadline": hours,
                "official_snapshot": latest.get("official_snapshot", {}),
                "upstreams": latest.get("upstreams", {}),
                "sources": latest.get("sources", []),
            }
            (archive_dir / f"gw{gw:02d}_metadata.json").write_text(
                json.dumps(metadata, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            print(f"Archived green GW{gw} forecast {hours:.1f}h before deadline")

    # Attach official outcomes only after FPL itself marks the event finished.
    for _, event in official.events.iterrows():
        gw = int(event["id"])
        path = archive_dir / f"gw{gw:02d}_forecast.csv"
        if not path.exists() or not bool(event.get("finished", False)):
            continue
        frame = pd.read_csv(path)
        if "event_points" in frame.columns and pd.to_numeric(
            frame["event_points"], errors="coerce"
        ).notna().all():
            continue
        live = http.get_json(
            f"{BASE}/event/{gw}/live/",
            f"official_event_{gw}_live",
            True,
        )
        points = parse_event_live_points(live)
        if not points:
            continue
        frame = attach_actual_points(frame, points, retrieved_at=now.isoformat())
        frame.to_csv(path, index=False)
        print(f"Attached official FPL outcomes to GW{gw} archive")

    completed = load_completed_archive(archive_dir)
    report = build_learning_report(completed)
    write_learning_report(report, calibration_path)
    print(
        f"Learning archive: completed GW={report.completed_gameweeks}, "
        f"active rows={report.active_rows}"
    )


if __name__ == "__main__":
    main()
