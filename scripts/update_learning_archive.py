#!/usr/bin/env python3
"""Maintain the no-hindsight Apex deadline learning archive.

Before a deadline this saves the freshest green projection that genuinely existed
before lock. After Official FPL marks the Gameweek finished it attaches realised
points and minutes. Learning then compares every provider on identical immutable rows.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import BASE, OfficialFPLClient
from apex_fpl.services.learning import (
    aggregate_deadline_forecast,
    attach_actual_outcomes,
    build_learning_report,
    load_completed_archive,
    parse_event_live_outcomes,
    write_learning_report,
)
from apex_fpl.services.projection_registry import PROJECTION_PROVIDERS
from apex_fpl.services.prospective_ledger import provider_ledger_from_forecast


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
    canonical_path = Path("data/generated/apex_recommendation_latest.json")
    canonical = (
        json.loads(canonical_path.read_text(encoding="utf-8"))
        if canonical_path.exists()
        else {}
    )

    # Repeated scheduled runs may replace the convenience GW file before deadline,
    # while content-addressed capture files remain immutable evidence of every bundle.
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
                deadline_time=deadline.isoformat(),
            )
            path = archive_dir / f"gw{gw:02d}_forecast.csv"
            csv_bytes = frame.to_csv(index=False).encode("utf-8")
            forecast_sha = hashlib.sha256(csv_bytes).hexdigest()
            bundle_id = str(canonical.get("decision_bundle_id") or forecast_sha)
            capture_dir = archive_dir / f"gw{gw:02d}_captures"
            capture_dir.mkdir(parents=True, exist_ok=True)
            capture_path = capture_dir / f"{bundle_id}.csv"
            if not capture_path.exists():
                capture_path.write_bytes(csv_bytes)

            source_versions: dict[str, str] = {}
            source_by_name = {
                str(source.get("name") or ""): source
                for source in latest.get("sources") or []
                if isinstance(source, dict)
            }
            for provider_key, spec in PROJECTION_PROVIDERS.items():
                if provider_key == "apex":
                    source_versions[spec.display_name] = str(latest.get("model_version") or "")
                    continue
                source = source_by_name.get(spec.source_status_name, {})
                source_versions[spec.display_name] = str(source.get("version") or "")
            official_source = source_by_name.get("official_fpl", {})
            source_versions["Official FPL EP"] = str(official_source.get("version") or "")

            provider_ledger = provider_ledger_from_forecast(
                frame,
                season=settings.season,
                champion_provider=settings.champion_provider,
                source_versions=source_versions,
            )
            provider_path = capture_dir / f"{bundle_id}_providers.csv"
            if not provider_path.exists():
                provider_path.write_text(provider_ledger.to_csv(index=False), encoding="utf-8")
            if not path.exists() or path.read_bytes() != csv_bytes:
                path.write_bytes(csv_bytes)
            metadata = {
                "gw": gw,
                "deadline_time": deadline.isoformat(),
                "captured_at": now.isoformat(),
                "hours_before_deadline": hours,
                "official_snapshot": latest.get("official_snapshot", {}),
                "upstreams": latest.get("upstreams", {}),
                "sources": latest.get("sources", []),
                "champion_provider": settings.champion_provider,
                "decision_bundle_id": canonical.get("decision_bundle_id"),
                "forecast_sha256": forecast_sha,
                "material_inputs": (canonical.get("decision_bundle") or {}).get(
                    "material_inputs", {}
                ),
            }
            metadata_path = archive_dir / f"gw{gw:02d}_metadata.json"
            previous = (
                json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata_path.exists()
                else {}
            )
            metadata["outcome_revisions"] = previous.get("outcome_revisions", [])
            if previous.get("forecast_sha256") != forecast_sha:
                metadata_path.write_text(
                    json.dumps(metadata, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
            print(f"Archived green GW{gw} forecast {hours:.1f}h before deadline")

    # Attach Official outcomes only after FPL itself marks the event finished.
    for _, event in official.events.iterrows():
        gw = int(event["id"])
        path = archive_dir / f"gw{gw:02d}_forecast.csv"
        if not path.exists() or not bool(event.get("finished", False)):
            continue
        frame = pd.read_csv(path)
        live = http.get_json(
            f"{BASE}/event/{gw}/live/",
            f"official_event_{gw}_live",
            True,
        )
        outcomes = parse_event_live_outcomes(live)
        if not outcomes:
            continue
        updated = attach_actual_outcomes(frame, outcomes, retrieved_at=now.isoformat())
        old_points = pd.to_numeric(frame.get("event_points"), errors="coerce")
        new_points = pd.to_numeric(updated["event_points"], errors="coerce")
        old_minutes = pd.to_numeric(frame.get("actual_minutes"), errors="coerce")
        new_minutes = pd.to_numeric(updated["actual_minutes"], errors="coerce")
        if old_points.equals(new_points) and old_minutes.equals(new_minutes):
            continue
        updated.to_csv(path, index=False)
        metadata_path = archive_dir / f"gw{gw:02d}_metadata.json"
        metadata = (
            json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata_path.exists()
            else {"gw": gw}
        )
        revisions = list(metadata.get("outcome_revisions") or [])
        outcome_payload = {
            str(player_id): values for player_id, values in sorted(outcomes.items())
        }
        revisions.append(
            {
                "retrieved_at": now.isoformat(),
                "outcomes_sha256": hashlib.sha256(
                    json.dumps(outcome_payload, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "changed_point_rows": int((old_points != new_points).fillna(True).sum()),
                "changed_minutes_rows": int((old_minutes != new_minutes).fillna(True).sum()),
            }
        )
        metadata["outcome_revisions"] = revisions
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(f"Attached/revised Official FPL outcomes for GW{gw} archive")

    completed = load_completed_archive(archive_dir)
    report = build_learning_report(
        completed,
        champion_provider=settings.champion_provider,
    )
    write_learning_report(report, calibration_path)
    print(
        f"Learning archive: completed GW={report.completed_gameweeks}, "
        f"rows={report.active_rows}, champion={settings.champion_provider}"
    )


if __name__ == "__main__":
    main()
