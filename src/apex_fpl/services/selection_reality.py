from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SelectionRealityResult:
    ready_for_high_confidence: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    playable_outfield_bench: int
    report: pd.DataFrame


def _numeric_map(
    players: pd.DataFrame,
    column: str,
    default: float = 0.0,
    *,
    upper: float | None = None,
) -> dict[int, float]:
    if column not in players.columns:
        return {int(pid): default for pid in players["player_id"].astype(int)}
    values = pd.to_numeric(players[column], errors="coerce").fillna(default)
    result: dict[int, float] = {}
    for pid, value in zip(players["player_id"].astype(int), values):
        parsed = max(float(value), 0.0)
        if upper is not None:
            parsed = min(parsed, upper)
        result[int(pid)] = parsed
    return result


def audit_selected_squad_reality(
    players: pd.DataFrame,
    *,
    selected_ids: set[int],
    xi_ids: set[int],
    bench_ids: list[int],
    specialist_report: pd.DataFrame | None = None,
    hierarchy_evidence: pd.DataFrame | None = None,
    transfer_report: pd.DataFrame | None = None,
    first_bench_min_appearance: float = 0.70,
    first_bench_min_expected_minutes: float = 30.0,
    playable_bench_min_appearance: float = 0.60,
    playable_bench_min_expected_minutes: float = 20.0,
    minimum_playable_outfield_bench: int = 2,
) -> SelectionRealityResult:
    """Fail closed on unresolved real-football selection fragility.

    This audit never changes xP, minutes, roles, club identity or optimiser weights.
    It is a readiness gate applied *after* the optimiser has produced a candidate.
    The purpose is to prevent a mathematically valid squad from being called high
    confidence when selected players rely on unresolved predicted-XI, squad-hierarchy,
    transfer-state, or unusably thin bench assumptions.
    """
    selected_ids = {int(pid) for pid in selected_ids}
    xi_ids = {int(pid) for pid in xi_ids}
    bench_ids = [int(pid) for pid in bench_ids]
    outfield_bench = [pid for pid in bench_ids if pid not in xi_ids]

    appearance = _numeric_map(players, "appearance_probability", 0.0, upper=1.0)
    starts = _numeric_map(players, "start_probability", 0.0, upper=1.0)
    minutes = _numeric_map(players, "expected_minutes", 0.0, upper=90.0)
    names = {
        int(row.player_id): str(getattr(row, "web_name", row.player_id))
        for row in players.itertuples(index=False)
    }
    ids_by_name = {str(name).strip().casefold(): pid for pid, name in names.items()}

    specialist_by_id: dict[int, tuple[str, str]] = {}
    if specialist_report is not None and not specialist_report.empty:
        for row in specialist_report.itertuples(index=False):
            pid = int(getattr(row, "player_id"))
            specialist_by_id[pid] = (
                str(getattr(row, "review_priority", "none")),
                str(getattr(row, "review_reason", "")),
            )

    hierarchy_by_id: dict[int, str] = {}
    if hierarchy_evidence is not None and not hierarchy_evidence.empty:
        frame = hierarchy_evidence.copy()
        if "hierarchy_status" in frame.columns:
            for row in frame.itertuples(index=False):
                pid_value = getattr(row, "player_id", None)
                pid: int | None = None
                if pid_value is not None and not pd.isna(pid_value):
                    try:
                        pid = int(pid_value)
                    except (TypeError, ValueError):
                        pid = None
                if pid is None:
                    name = str(getattr(row, "web_name", "")).strip().casefold()
                    pid = ids_by_name.get(name)
                if pid is not None:
                    hierarchy_by_id[pid] = str(
                        getattr(row, "hierarchy_status")
                    ).strip().casefold()

    transfer_by_id: dict[int, tuple[str, str]] = {}
    if transfer_report is not None and not transfer_report.empty:
        if {"player_id", "review_priority"}.issubset(transfer_report.columns):
            for row in transfer_report.itertuples(index=False):
                transfer_by_id[int(row.player_id)] = (
                    str(getattr(row, "review_priority", "none")),
                    str(getattr(row, "review_reason", "")),
                )

    blockers: list[str] = []
    warnings: list[str] = []
    report_rows: list[dict] = []
    playable_outfield = 0

    weak_hierarchy = {"academy", "u21", "youth", "fringe", "reserve"}
    for pid in sorted(selected_ids):
        name = names.get(pid, str(pid))
        is_xi = pid in xi_ids
        is_bench = pid in outfield_bench
        hierarchy = hierarchy_by_id.get(pid, "unknown")
        specialist_priority, specialist_reason = specialist_by_id.get(pid, ("none", ""))
        transfer_priority, transfer_reason = transfer_by_id.get(pid, ("none", ""))
        app = appearance.get(pid, 0.0)
        start = starts.get(pid, 0.0)
        exp_min = minutes.get(pid, 0.0)

        reasons: list[str] = []
        priority = "none"

        if transfer_priority == "high":
            priority = "blocker"
            reasons.append(transfer_reason or "high transfer risk")
        if specialist_priority == "high":
            priority = "blocker"
            reasons.append(specialist_reason or "high predicted-XI disagreement")
        if hierarchy in weak_hierarchy and (is_xi or is_bench):
            priority = "blocker"
            reasons.append(f"current squad hierarchy is {hierarchy}")

        if is_xi and app > 0 and app < 0.70:
            priority = "blocker"
            reasons.append(f"XI appearance probability only {app:.0%}")
        elif is_xi and start < 0.65:
            if priority != "blocker":
                priority = "warning"
            reasons.append(f"XI start probability only {start:.0%}")

        if is_bench:
            appearance_ok = app >= playable_bench_min_appearance if app > 0 else False
            minutes_ok = exp_min >= playable_bench_min_expected_minutes
            playable = (appearance_ok or minutes_ok) and hierarchy not in weak_hierarchy
            if playable:
                playable_outfield += 1
            if outfield_bench and pid == outfield_bench[0]:
                first_appearance_bad = app > 0 and app < first_bench_min_appearance
                first_minutes_bad = exp_min < first_bench_min_expected_minutes
                if first_appearance_bad or first_minutes_bad:
                    priority = "blocker"
                    details = []
                    if first_appearance_bad:
                        details.append(f"appearance probability {app:.0%}")
                    if first_minutes_bad:
                        details.append(f"expected minutes {exp_min:.1f}")
                    reasons.append(
                        "first outfield bench is not a credible autosub: " + ", ".join(details)
                    )

        if specialist_priority == "medium" and priority == "none":
            priority = "warning"
            reasons.append(specialist_reason or "specialist review required")
        if transfer_priority == "medium" and priority == "none":
            priority = "warning"
            reasons.append(transfer_reason or "transfer review required")

        if priority == "blocker":
            blockers.append(f"{name}: " + "; ".join(dict.fromkeys(reasons)))
        elif priority == "warning":
            warnings.append(f"{name}: " + "; ".join(dict.fromkeys(reasons)))

        report_rows.append(
            {
                "player_id": pid,
                "web_name": name,
                "in_xi": is_xi,
                "on_outfield_bench": is_bench,
                "expected_minutes": exp_min,
                "appearance_probability": app,
                "start_probability": start,
                "hierarchy_status": hierarchy,
                "specialist_priority": specialist_priority,
                "transfer_priority": transfer_priority,
                "reality_priority": priority,
                "reality_reason": "; ".join(dict.fromkeys(reasons)),
            }
        )

    if playable_outfield < int(minimum_playable_outfield_bench):
        blockers.append(
            "bench resilience: only "
            f"{playable_outfield} outfield bench players clear the playable appearance/minutes "
            f"threshold; minimum for high-confidence launch is {minimum_playable_outfield_bench}"
        )

    report = pd.DataFrame(report_rows)
    return SelectionRealityResult(
        ready_for_high_confidence=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        playable_outfield_bench=playable_outfield,
        report=report,
    )
