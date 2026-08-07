#!/usr/bin/env python3
"""Publish the latest green Apex result into a small GitHub-readable snapshot.

GitHub Actions artifacts are useful for debugging but are awkward for ChatGPT or a
human to inspect later. This script copies only the decision-critical, validated
state into ``data/generated/`` so the repository itself always exposes the latest
production recommendation without committing bulky raw caches/snapshots.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd


def _records(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if limit is not None:
        df = df.head(limit)
    return json.loads(df.to_json(orient="records"))


def main() -> None:
    report_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/generated")
    latest_json = report_dir / "latest.json"
    latest_md = report_dir / "latest.md"
    if not latest_json.exists() or not latest_md.exists():
        raise SystemExit("Apex reports are missing; run the pipeline first")

    report = json.loads(latest_json.read_text(encoding="utf-8"))
    if report.get("safe_to_act") is not True or report.get("full_apex_ready") is not True:
        raise SystemExit(
            "Refusing to publish a production snapshot because the full Apex gate is not green"
        )

    sources = report.get("sources", [])
    unhealthy_required = [
        row.get("name")
        for row in sources
        if row.get("name") in {"official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds"}
        and (not row.get("ok") or not row.get("configured", True))
    ]
    if unhealthy_required:
        raise SystemExit(
            "Refusing to publish because required source rows are unhealthy: "
            + ", ".join(str(x) for x in unhealthy_required)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    published = {
        "contract": "apex-fpl-production-snapshot-v1",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "generated_at": report.get("generated_at"),
        "gameweeks": report.get("gameweeks", []),
        "safe_to_act": True,
        "full_apex_ready": True,
        "official_snapshot": report.get("official_snapshot", {}),
        "upstreams": report.get("upstreams", {}),
        "sources": sources,
        "scenario_comparison": report.get("scenario_comparison", []),
        "scenarios": report.get("scenarios", {}),
        "risk_report": report.get("risk_report", []),
        "transfer_plan": report.get("transfer_plan"),
        # Enough ranked alternatives for ChatGPT to answer most player-vs-player
        # questions without forcing the large per-fixture projection table into git.
        "top_players": _records(report_dir / "players.csv", limit=150),
    }

    parity = output_dir / "solver_parity.json"
    if parity.exists():
        try:
            published["solver_parity"] = json.loads(parity.read_text(encoding="utf-8"))
        except Exception:
            published["solver_parity"] = None

    (output_dir / "apex_latest.json").write_text(
        json.dumps(published, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "apex_latest.md").write_text(
        latest_md.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print(
        f"Published green Apex snapshot: {len(published['top_players'])} ranked players, "
        f"scenarios={list(published['scenarios'])}"
    )


if __name__ == "__main__":
    main()
