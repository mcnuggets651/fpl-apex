from __future__ import annotations

from typing import Any


ADVERSARIAL_CONTRACT = "apex-adversarial-launch-ban-v2"


def adversarial_certification_blockers(payload: dict[str, Any]) -> tuple[str, ...]:
    """Return release blockers from an adversarial launch-ban report.

    Diagnostics are allowed to record hostile perturbations that fail to solve. A
    release certificate is not: every configured target must resolve, every target
    perturbation must be stable/certified (or explicitly neutral because the target
    is absent from the baseline), and no certified ban may improve both the first
    actionable Gameweek and future objective.
    """
    blockers: list[str] = []
    if payload.get("contract") != ADVERSARIAL_CONTRACT:
        blockers.append("unexpected adversarial audit contract")
    if not payload.get("decision_bundle_id"):
        blockers.append("adversarial audit is not bound to a DecisionBundle")

    summary = payload.get("summary")
    targets = payload.get("targets")
    if not isinstance(summary, dict):
        blockers.append("adversarial audit summary is missing")
        summary = {}
    if not isinstance(targets, list) or not targets:
        blockers.append("adversarial audit target results are missing")
        targets = []

    if summary.get("audit_complete") is not True:
        blockers.append("adversarial audit did not cover every configured target")

    for row in targets:
        if not isinstance(row, dict):
            blockers.append("adversarial audit contains a malformed target result")
            continue
        name = str(row.get("target") or row.get("player_id") or "unknown")
        status = str(row.get("status") or "")
        interpretation = str(row.get("reality_interpretation") or "")
        if status == "target_not_uniquely_resolved":
            blockers.append(f"adversarial target is not uniquely resolved: {name}")
            continue
        if status == "ban_solve_error":
            blockers.append(f"adversarial ban solve failed: {name}")
            continue
        if interpretation == "search_surface_defect_signal":
            blockers.append(
                f"adversarial ban improves both launch and future objective: {name}"
            )
        if row.get("certified") is not True:
            blockers.append(f"adversarial perturbation is not certified: {name}")

    # Cross-check summary so a malformed producer cannot hide a row-level defect.
    for name in summary.get("search_surface_defect_signals") or []:
        message = f"adversarial ban improves both launch and future objective: {name}"
        if message not in blockers:
            blockers.append(message)
    for name in summary.get("ban_solve_errors") or []:
        message = f"adversarial ban solve failed: {name}"
        if message not in blockers:
            blockers.append(message)

    return tuple(dict.fromkeys(blockers))
