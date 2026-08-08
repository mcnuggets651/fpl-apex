#!/usr/bin/env python3
"""Blocked no-hindsight shrinkage validation when older FPL Core history is absent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.services.provenance import load_upstream_pins
from validate_shrinkage import (
    DEFAULT_GRID,
    RATE_FIELDS,
    _choose_k,
    _examples_for_metric,
    _metrics,
    _predict_examples,
    _promotion_gate,
    _season_frame,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2025-2026")
    parser.add_argument("--window-gws", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="reports/shrinkage_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    http = CachedHttp(settings.cache_dir)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    stats = _season_frame(FPLCoreClient(http, args.season, ref=ref), args.force)

    report = {
        "contract": "apex-shrinkage-validation-v1",
        "evidence_design": "blocked_within_completed_prior_season",
        "season": args.season,
        "window_gws": args.window_gws,
        "grid_prior_minutes": DEFAULT_GRID,
        "metrics": {},
        "evidence_note": (
            "Pinned FPL Core does not expose the requested older season. Hyperparameters "
            "are calibrated on early 2025/26 cutoffs and evaluated only on untouched later "
            "2025/26 cutoffs. This is no-hindsight but weaker than a cross-season holdout."
        ),
    }
    all_pass = True
    for metric in RATE_FIELDS:
        examples = _examples_for_metric(stats, metric, window_gws=args.window_gws)
        cutoffs = sorted(examples["cutoff_gw"].unique()) if not examples.empty else []
        if len(cutoffs) < 4:
            report["metrics"][metric] = {
                "status": "insufficient_history",
                "cutoffs": cutoffs,
                "promotion_gate": {"pass": False},
            }
            all_pass = False
            continue
        split = max(2, int(len(cutoffs) * 0.6))
        split = min(split, len(cutoffs) - 2)
        train_cutoffs = cutoffs[:split]
        test_cutoffs = cutoffs[split:]
        train = examples[examples["cutoff_gw"].isin(train_cutoffs)].copy()
        test = examples[examples["cutoff_gw"].isin(test_cutoffs)].copy()
        chosen_k, grid_scores = _choose_k(train, metric, DEFAULT_GRID)
        scored = _predict_examples(test, metric, chosen_k)
        validation = _metrics(scored)
        gate = _promotion_gate(validation)
        report["metrics"][metric] = {
            "status": "validated" if gate["pass"] else "validation_failed",
            "chosen_prior_minutes": chosen_k,
            "train_cutoffs": train_cutoffs,
            "test_cutoffs": test_cutoffs,
            "train_n": int(len(train)),
            "test_n": int(len(test)),
            "grid_scores": grid_scores,
            "test": validation,
            "promotion_gate": gate,
        }
        all_pass = all_pass and bool(gate["pass"])

    report["promotion_ready"] = bool(all_pass)
    report["promotion_rule"] = (
        "Each metric needs statistically clear low-minute improvement, no increase in overall "
        "held-out RMSE, and no statistically clear harm in the >=1800-minute bucket."
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"promotion_ready": report["promotion_ready"], "output": str(path)}, indent=2))
    raise SystemExit(0 if report["promotion_ready"] else 2)


if __name__ == "__main__":
    main()
