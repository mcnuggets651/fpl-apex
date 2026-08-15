from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apex_fpl.replay.audit import audit_replay_store

DECAY_CANDIDATES = (1.00, 0.97, 0.95, 0.90)
HISTORICAL_PRESEASON_SEASONS = ("2024-2025", "2025-2026")


def _friendlies_dir(core_root: Path, season: str) -> Path:
    return core_root / "data" / season / "By Tournament" / "Friendlies"


def _archived_preseason_seasons(historical_audit_path: Path | None) -> set[str]:
    if historical_audit_path is None or not historical_audit_path.exists():
        return set()
    payload = json.loads(historical_audit_path.read_text(encoding="utf-8"))
    return {
        str(row["season"])
        for row in payload.get("seasons", [])
        if row.get("season") and row.get("feature_ref")
    }


def _bench_shadow_status(bench_audit_path: Path | None) -> dict:
    if bench_audit_path is None or not bench_audit_path.exists():
        return {
            "audit_available": False,
            "eligible_for_production_ab": False,
            "blockers": ["bench-appearance recent-season robustness audit is unavailable"],
        }
    payload = json.loads(bench_audit_path.read_text(encoding="utf-8"))
    robustness = payload.get("recent_season_robustness", {})
    return {
        "audit_available": True,
        "eligible_for_production_ab": bool(
            robustness.get("eligible_for_production_ab", False)
        ),
        "checks": robustness.get("checks", {}),
        "blockers": payload.get("blockers", []),
    }


def build_projection_policy_readiness(
    apex_store: Path,
    core_root: Path,
    historical_audit_path: Path | None = None,
    bench_audit_path: Path | None = None,
) -> dict:
    replay = audit_replay_store(apex_store, season="2025-2026")
    archived = _archived_preseason_seasons(historical_audit_path)
    preseason_sources = {}
    for season in HISTORICAL_PRESEASON_SEASONS:
        if _friendlies_dir(core_root, season).is_dir():
            preseason_sources[season] = "current_tree"
        elif season in archived:
            preseason_sources[season] = "git_history"
        else:
            preseason_sources[season] = None
    preseason = {season: source is not None for season, source in preseason_sources.items()}
    broad_preseason_history_ready = all(preseason.values())
    bench_shadow = _bench_shadow_status(bench_audit_path)

    decay_blockers = list(replay.blockers)
    decay_result = (
        "eligible_for_transfer_aware_decay_replay"
        if replay.apex_replay_eligible
        else "blocked_missing_predeadline_apex_bundles"
    )

    historical_blockers: list[str] = []
    if not broad_preseason_history_ready:
        missing = [season for season, exists in preseason.items() if not exists]
        historical_blockers.append(
            "missing historical preseason player-match archive for broad model validation: "
            + ", ".join(missing)
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": "apex-projection-policy-readiness-v2",
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
            "historical_friendlies_sources": preseason_sources,
            "historical_validation_ready": broad_preseason_history_ready,
            "promotion_allowed": False,
            "blockers": historical_blockers,
            "rule": (
                "Broad attacking-rate fallbacks still require independent historical validation; "
                "preserve observed goals/assists/shots without silently converting them to xG/xA."
            ),
        },
        "minutes_decomposition": {
            "historical_friendlies_available": preseason,
            "historical_friendlies_sources": preseason_sources,
            "historical_validation_ready": broad_preseason_history_ready,
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
                "Do not replace production xMins from a narrow substitute-use result. "
                "The full decomposed minutes challenger must win its own historical gate."
            ),
        },
        "bench_appearance_propensity": {
            "audit_available": bench_shadow["audit_available"],
            "recent_full_season_can_qualify_if_robust": True,
            "robustness_checks": bench_shadow.get("checks", {}),
            "eligible_for_production_ab": bench_shadow[
                "eligible_for_production_ab"
            ],
            "production_ab_required_before_promotion": True,
            "promotion_allowed": False,
            "blockers": bench_shadow["blockers"],
            "rule": (
                "A narrow substitute-appearance challenger may advance from one recent full "
                "season only if player/team-clustered confidence intervals, leave-one-team-out "
                "stability, sample-size thresholds, and key-cohort checks all pass. Advancement "
                "means production A/B eligibility only; it never directly changes live Apex."
            ),
        },
    }
