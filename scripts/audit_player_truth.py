#!/usr/bin/env python3
"""CLI for the all-player factual/provenance production audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.services.player_truth import audit_player_truth


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", default="reports/players.csv")
    parser.add_argument("--projections", default="reports/projections.csv")
    parser.add_argument(
        "--recommendation",
        default="data/generated/apex_recommendation_latest.json",
    )
    parser.add_argument("--output", default="reports/player_truth_audit.json")
    parser.add_argument("--csv", default="reports/player_truth_audit.csv")
    args = parser.parse_args()

    players_path = Path(args.players)
    projections_path = Path(args.projections)
    if not players_path.exists() or not projections_path.exists():
        raise SystemExit("player truth audit requires generated players.csv and projections.csv")

    expected_players = None
    recommendation_path = Path(args.recommendation)
    if recommendation_path.exists():
        try:
            recommendation = json.loads(
                recommendation_path.read_text(encoding="utf-8")
            )
            value = (recommendation.get("official_snapshot") or {}).get("players")
            if value is not None:
                expected_players = int(value)
        except Exception:
            expected_players = None

    payload = audit_player_truth(
        pd.read_csv(players_path),
        pd.read_csv(projections_path),
        expected_players,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    pd.DataFrame(payload["players"]).to_csv(args.csv, index=False)

    print(
        f"Player truth: ready={payload['ready']} players={payload['player_count']} "
        f"hard_fact_coverage={payload['hard_fact_coverage']:.2%}"
    )
    for blocker in payload["blockers"]:
        print("BLOCKER:", blocker)
    for warning in payload["warnings"]:
        print("WARNING:", warning)
    raise SystemExit(0 if payload["ready"] else 1)


if __name__ == "__main__":
    main()
