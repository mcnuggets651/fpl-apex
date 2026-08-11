from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from apex_fpl.replay.audit import audit_replay_store


def _revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _official_coverage(vaastav_root: Path | None) -> dict:
    if vaastav_root is None:
        return {"revision": None, "xp_gameweeks": [], "outcome_gameweeks": []}
    gws = vaastav_root / "data" / "2025-26" / "gws"
    return {
        "revision": _revision(vaastav_root),
        "xp_gameweeks": [gw for gw in range(1, 39) if (gws / f"xP{gw}.csv").is_file()],
        "outcome_gameweeks": [gw for gw in range(1, 39) if (gws / f"gw{gw}.csv").is_file()],
        "qualification": (
            "baseline/scoring inputs only; mixed result files are not Apex deadline bundles"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apex-store", type=Path, required=True)
    parser.add_argument("--vaastav-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    apex = audit_replay_store(args.apex_store)
    official = _official_coverage(args.vaastav_root)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "locked pseudo-prospective integration benchmark",
        "season": "2025-2026",
        "apex_store": apex.to_dict(),
        "official_history": official,
        "result": (
            "eligible" if apex.apex_replay_eligible else "blocked_missing_predeadline_apex_bundles"
        ),
        "claims_allowed": {
            "official_xp_baseline": len(official["xp_gameweeks"]) == 38,
            "realised_scoring": len(official["outcome_gameweeks"]) == 38,
            "apex_season_total": apex.apex_replay_eligible,
            "blind_holdout": False,
        },
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
