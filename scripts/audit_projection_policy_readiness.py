from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from apex_fpl.replay.audit import audit_replay_store


DECAY_CANDIDATES = (1.00, 0.97, 0.95, 0.90)
HISTORICAL_PRESEASON_SEASONS = ("2024-2025", "2025-2026")


def _friendlies_dir(core_root: Path, season: str) -> Path:
    return core_root / "data" / season / "By Tournament" / "Friendlies"


def build_readiness(apex_store: Path, core_root: Path) -> dict:
    replay = audit_replay_store(apex_store, season="2025-2026")
    preseason = {
        season: _friendlies_dir(core_root, season).is_dir()
        for season in HISTORICAL_PRESEASON_SEASONS
    }
    preseason_history_ready = all(preseason.values())

    decay_blockers = list(replay.blockers)
    if not replay.apex_replay_eligible:
        decay_result = "blocked_missing_predeadline_apex_bundles"
    else:
        # This gate deliberately does not pick a winner without running the four
        # transfer-aware policies over the sealed decision surfaces.
        decay_result = "eligible_for_transfer_aware_decay_replay"

    historical_blockers: list[str] = []
    if not preseason_history_ready:
        missing = [season for season, exists in preseason.items() if not exists]
        historical_blockers.append(
            "missing historical preseason player-match archive for: " + ", ".join(missing)
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": "apex-projection-policy-readiness-v1",
        "fixture_decay": {
            "candidates": list(DECAY_CANDIDATES),
            "incumbent": 0.90,
            "result": decay_result,
            "promotion_allowed": False,
            "blockers": decay_blockers,
            "rule": (
                "No decay change without no-hindsight transfer-aware season replay; "
                "raw horizon xP remains undiscounted regardless of policy."
            ),
        },
        "preseason_return_fallback": {
            "historical_friendlies_available": preseason,
            "historical_validation_ready": preseason_history_ready,
            "promotion_allowed": False,
            "blockers": historical_blockers,
            "rule": (
                "Preserve observed goals/assists/shots now; do not convert them to xG/xA "
                "until a chronological historical preseason->early-season gate is available."
            ),
        },
        "minutes_decomposition": {
            "historical_friendlies_available": preseason,
            "historical_validation_ready": preseason_history_ready,
            "promotion_allowed": False,
            "blockers": historical_blockers,
            "required_metrics": [
                "start_brier",
                "start_calibration",
                "minutes_mae",
                "minutes_rmse",
                "bench_appearance_calibration",
                "starter_conditional_minutes_mae",
                "substitute_conditional_minutes_mae",
            ],
            "rule": (
                "Do not replace production xMins until a decomposed challenger improves "
                "historical preseason->early-season calibration on a true holdout."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apex-store", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_readiness(args.apex_store, args.core_root)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
