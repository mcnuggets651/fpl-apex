#!/usr/bin/env python3
"""Run the single canonical Apex decision workflow.

User-facing rule: run this command, then read apex_recommendation_latest.json.
Pinnacle and Elite files are internal diagnostics only. The workflow is deliberately
one-way: sealed surface -> non-actionable staging -> identity/statistical truth ->
selection-reality evidence -> all-player truth -> one final strategy selector ->
final selected-player evidence -> actionable output.

The sealed bundle is the source-coherence boundary: Official FPL, AIrsenal and the
immutable FPL Core pin used to build it must remain the exact inputs consumed by all
later gates in this invocation. A newer upstream revision belongs to the next build;
it must never be mixed into an already-sealed decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def _explicit_readiness_block(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    gate = payload.get("pinnacle_gate")
    blockers = gate.get("blockers") if isinstance(gate, dict) else None
    return payload.get("pinnacle_ready") is False and bool(blockers)


def _run(command: list[str]) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def _fail_close_strategy_output(output_dir: Path, reason: str) -> None:
    """Never leave an invalid or intermediate decision actionable."""
    recommendation_path = output_dir / "apex_recommendation_latest.json"
    context_path = output_dir / "apex_answer_context.json"
    markdown_path = output_dir / "apex_recommendation_latest.md"
    blocker = f"canonical decision gate failed: {reason}"

    if recommendation_path.exists():
        try:
            payload = json.loads(recommendation_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["ready_to_act"] = False
    payload["strategy_stage"] = "blocked"
    payload["recommendation"] = None
    payload["blockers"] = list(
        dict.fromkeys([*(payload.get("blockers") or []), blocker])
    )
    recommendation_path.parent.mkdir(parents=True, exist_ok=True)
    recommendation_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if context_path.exists():
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except Exception:
            context = {}
    else:
        context = {}
    if not isinstance(context, dict):
        context = {}
    context["safe_to_act"] = False
    context["ready_to_act"] = False
    context["recommendation"] = None
    context["production_result"] = None
    context["blockers"] = list(
        dict.fromkeys([*(context.get("blockers") or []), blocker])
    )
    context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        "# Apex Unified Recommendation — NOT READY\n\n"
        f"- {blocker}\n",
        encoding="utf-8",
    )


def _required_gate(command: list[str], output_dir: Path, label: str) -> None:
    status = _run(command)
    if status != 0:
        _fail_close_strategy_output(output_dir, f"{label} failed with exit status {status}")
        raise SystemExit(status)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--cvar-alpha", type=float, default=0.10)
    parser.add_argument("--cvar-weight", type=float, default=0.20)
    parser.add_argument("--output-dir", default="data/generated")
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument(
        "--reuse-bundle",
        action="store_true",
        help="Replay an existing sealed bundle without fetching any live input.",
    )
    parser.add_argument(
        "--reuse-pinnacle",
        action="store_true",
        help="Reuse a just-generated Pinnacle artifact after same-surface parity was embedded.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    bundle_dir = Path(args.bundle_dir)
    pinnacle_path = output_dir / "pinnacle_latest.json"
    elite_path = output_dir / "elite_latest.json"
    truth_path = Path("reports/player_truth_audit.json")

    if not args.reuse_bundle and not args.reuse_pinnacle:
        bundle_cmd = [
            sys.executable,
            "scripts/build_decision_bundle.py",
            "--horizon",
            str(args.horizon),
            "--bundle-dir",
            str(bundle_dir),
        ]
        if args.force:
            bundle_cmd.append("--force")
        status = _run(bundle_cmd)
        if status != 0:
            raise SystemExit(status)
    elif not (bundle_dir / "manifest.json").exists():
        raise SystemExit(f"cannot reuse missing decision bundle: {bundle_dir}")

    pinnacle_cmd = [
        sys.executable,
        "scripts/run_pinnacle.py",
        "--horizon",
        str(args.horizon),
        "--stochastic-scenarios",
        str(args.stochastic_scenarios),
        "--cvar-alpha",
        str(args.cvar_alpha),
        "--cvar-weight",
        str(args.cvar_weight),
        "--output-dir",
        str(output_dir),
        "--bundle-dir",
        str(bundle_dir),
    ]

    if not args.reuse_pinnacle:
        status = _run(pinnacle_cmd)
        if status != 0 and not _explicit_readiness_block(pinnacle_path):
            raise SystemExit(status)
    elif not pinnacle_path.exists():
        raise SystemExit(f"cannot reuse missing Pinnacle artifact: {pinnacle_path}")

    elite_status = _run(
        [
            sys.executable,
            "scripts/run_elite.py",
            "--horizon",
            str(args.horizon),
            "--output-dir",
            str(output_dir),
            "--bundle-dir",
            str(bundle_dir),
        ]
    )
    if elite_status != 0:
        raise SystemExit(elite_status)

    staging_status = _run(
        [
            sys.executable,
            "scripts/build_canonical_recommendation.py",
            "--pinnacle",
            str(pinnacle_path),
            "--elite",
            str(elite_path),
            "--output-dir",
            str(output_dir),
            "--bundle-dir",
            str(bundle_dir),
        ]
    )
    if staging_status != 0:
        _fail_close_strategy_output(output_dir, f"staging exit status {staging_status}")
        raise SystemExit(staging_status)

    _required_gate(
        [
            sys.executable,
            "scripts/audit_player_identity.py",
            "--bundle-dir",
            str(bundle_dir),
        ],
        output_dir,
        "player identity audit",
    )
    _required_gate(
        [
            sys.executable,
            "scripts/audit_statistical_truth.py",
            "--bundle-dir",
            str(bundle_dir),
        ],
        output_dir,
        "statistical truth audit",
    )
    _required_gate(
        [
            sys.executable,
            "scripts/materialize_selection_reality_evidence.py",
            "--bundle-dir",
            str(bundle_dir),
            "--output-dir",
            str(output_dir),
        ],
        output_dir,
        "selection reality evidence materialization",
    )

    truth_status = _run(
        [
            sys.executable,
            "scripts/audit_player_truth.py",
            "--recommendation",
            str(output_dir / "apex_recommendation_latest.json"),
            "--output",
            str(truth_path),
            "--csv",
            "reports/player_truth_audit.csv",
        ]
    )
    if truth_status != 0:
        _fail_close_strategy_output(
            output_dir,
            f"player truth audit failed with exit status {truth_status}",
        )
        raise SystemExit(truth_status)

    promotion_status = _run(
        [
            sys.executable,
            "scripts/apply_joint_path_promotion_rebased.py",
            "--output-dir",
            str(output_dir),
            "--bundle-dir",
            str(bundle_dir),
            "--truth-audit",
            str(truth_path),
        ]
    )
    if promotion_status != 0:
        _fail_close_strategy_output(output_dir, f"final strategy exit status {promotion_status}")
    raise SystemExit(promotion_status)


if __name__ == "__main__":
    main()
