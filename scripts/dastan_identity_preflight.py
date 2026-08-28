#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from apex.forecast.dastan_identity import (
    audit_current_roster,
    payload_sha256,
    resolve_understat_clubs,
)

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
REVIEWED_ALIASES = {
    "Coventry City": ("Coventry", "Coventry_City"),
    "Hull City": ("Hull", "Hull_City"),
}


def _mapping_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Dastan's stable FPL-code roster and resolve only the reviewed "
            "missing club identities from the live Understat EPL season."
        )
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--understat-season", default="2026")
    args = parser.parse_args()

    if not args.mapping.is_file():
        raise SystemExit(f"Dastan current mapping missing: {args.mapping}")

    response = requests.get(
        BOOTSTRAP_URL,
        headers={"User-Agent": "apex-v2-dastan-preflight/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    bootstrap = response.json()
    elements = bootstrap.get("elements")
    if not isinstance(elements, list):
        raise SystemExit("Official FPL bootstrap elements malformed")

    try:
        from understatapi import UnderstatClient
    except ImportError as exc:
        raise SystemExit(
            "understatapi is required; run inside the pinned Dastan data environment"
        ) from exc

    with UnderstatClient() as client:
        teams = client.league(league="EPL").get_team_data(season=args.understat_season)
    if not isinstance(teams, dict) or not teams:
        raise SystemExit("Understat EPL team payload is empty or malformed")

    overlays = resolve_understat_clubs(teams, aliases=REVIEWED_ALIASES)
    roster = audit_current_roster(elements, _mapping_rows(args.mapping))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "understat_season": args.understat_season,
        "understat_payload_sha256": payload_sha256(teams),
        "understat_team_count": len(teams),
        "reviewed_aliases": {
            key: list(values) for key, values in REVIEWED_ALIASES.items()
        },
        "club_overlay": [
            {
                "club_name": row.club_name,
                "understat_name": row.understat_name,
                "understat_team_id": row.understat_team_id,
            }
            for row in overlays
        ],
        "roster_audit": roster,
        "raw_understat_teams": teams,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "club_overlay": payload["club_overlay"],
                "matched_by_fpl_code": roster["matched_by_fpl_code"],
                "official_players": roster["official_players"],
                "missing_from_dastan_roster": len(roster["missing_from_dastan_roster"]),
                "unresolved_understat": len(roster["unresolved_understat_codes"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
