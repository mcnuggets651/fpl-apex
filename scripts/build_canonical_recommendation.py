#!/usr/bin/env python3
"""Build the single user-facing Apex recommendation from internal diagnostics.

Internal layers may disagree. This script is the only authority that turns those
layers into a user-facing team. It never invents a new xP forecast.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apex_fpl.services.answer_context import build_answer_context


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required diagnostic: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"unreadable diagnostic {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"diagnostic is not a JSON object: {path}")
    return payload


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    snap = payload.get("official_snapshot")
    return snap if isinstance(snap, dict) else {}


def _snapshot_fingerprint(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    snap = _snapshot(payload)
    bootstrap = snap.get("bootstrap_sha256")
    fixtures = snap.get("fixtures_sha256")
    return (
        str(bootstrap) if bootstrap else None,
        str(fixtures) if fixtures else None,
    )


def _name(rows: Any) -> str | None:
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return str(row.get("web_name")) if isinstance(row, dict) and row.get("web_name") else None


def _table(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| Player | Club | Pos | Price | GW1 xP |", "|:--|:--|:--:|--:|--:|"]
    for row in rows:
        lines.append(
            "| {web_name} | {team_name} | {position} | {price:.1f} | {gw1_xp:.2f} |".format(
                web_name=row.get("web_name", ""),
                team_name=row.get("team_name", ""),
                position=row.get("position", ""),
                price=float(row.get("price") or 0.0),
                gw1_xp=float(row.get("gw1_xp") or 0.0),
            )
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pinnacle", default="data/generated/pinnacle_latest.json")
    parser.add_argument("--elite", default="data/generated/elite_latest.json")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    pinnacle = _load(Path(args.pinnacle))
    elite = _load(Path(args.elite))

    blockers: list[str] = []
    if not pinnacle.get("safe_to_act"):
        blockers.append("Apex safety gate is not green")
    if not pinnacle.get("full_apex_ready"):
        blockers.append("full Apex data gate is not green")
    if not pinnacle.get("pinnacle_ready"):
        blockers.append("Pinnacle decision-readiness gate is not green")
        gate = pinnacle.get("pinnacle_gate")
        if isinstance(gate, dict):
            for blocker in gate.get("blockers") or []:
                blockers.append(str(blocker))
    if not elite.get("safe_to_act") or not elite.get("full_apex_ready"):
        blockers.append("Elite diagnostic did not run on a fully green Apex surface")

    pinnacle_fp = _snapshot_fingerprint(pinnacle)
    elite_fp = _snapshot_fingerprint(elite)
    if None in pinnacle_fp or None in elite_fp:
        blockers.append("diagnostic Official FPL content hashes are missing")
    elif pinnacle_fp != elite_fp:
        blockers.append("Pinnacle/Elite Official FPL content hashes do not match")

    convergence = elite.get("epsilon_convergence")
    converged = bool(isinstance(convergence, dict) and convergence.get("converged"))
    selector = "elite_lexicographic" if converged else "maximum_ev"
    if selector == "elite_lexicographic":
        selected = elite.get("elite")
        mechanics = elite.get("elite_gw1_mechanics")
    else:
        selected = elite.get("maximum_ev_reference")
        mechanics = elite.get("maximum_ev_gw1_mechanics")

    if not isinstance(selected, dict) or selected.get("status") != "Optimal":
        blockers.append(f"selected canonical solution is not optimal: {selector}")
        selected = selected if isinstance(selected, dict) else {}
    squad = selected.get("squad") or []
    xi = selected.get("xi") or []
    if not isinstance(squad, list) or len(squad) != 15:
        blockers.append("canonical squad is not a legal 15-player selection")
        squad = squad if isinstance(squad, list) else []
    if not isinstance(xi, list) or len(xi) != 11:
        blockers.append("canonical starting XI does not contain 11 players")
        xi = xi if isinstance(xi, list) else []
    if not isinstance(mechanics, dict):
        blockers.append("exact GW1 captain/vice/bench mechanics are missing")
        mechanics = {}

    captain = mechanics.get("captain_name") or _name(selected.get("captain"))
    vice_captain = mechanics.get("vice_captain_name") or _name(selected.get("vice_captain"))
    if not captain or not vice_captain:
        blockers.append("canonical captain/vice could not be resolved")

    ready = not blockers
    recommendation = {
        "selector": selector,
        "selector_reason": (
            "Elite epsilon frontier passed the explicit convergence rule"
            if converged
            else "Elite epsilon frontier did not pass; maximum-EV is the mandatory fallback"
        ),
        "objective": selected.get("objective"),
        "squad": squad,
        "xi": xi,
        "captain": captain,
        "vice_captain": vice_captain,
        "bench_gk": mechanics.get("bench_gk_name"),
        "outfield_bench_order": mechanics.get("outfield_bench_order_names") or [],
        "gw1_expected_total_with_mechanics": mechanics.get("expected_total_points"),
    }

    payload = {
        "contract": "apex-unified-recommendation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical": True,
        "user_facing_source_of_truth": True,
        "ready_to_act": ready,
        "blockers": blockers,
        "official_snapshot": pinnacle.get("official_snapshot"),
        "gameweeks": pinnacle.get("gameweeks") or elite.get("gameweeks") or [],
        "decision_policy": {
            "primary_forecast": "canonical ensemble xp",
            "primary_selection": "maximum expected FPL points under legal FPL constraints",
            "secondary_selection": "Elite 35/20/15/10/10/5/5 only inside an epsilon-audited near-optimal xP set",
            "elite_convergence_rule": ">=13/15 overlap with max-EV and same captain at 0.25%, 0.50%, 1.00%",
            "elite_failure_fallback": "maximum_ev",
            "ownership_in_points_objective": False,
            "minutes_model": "first-class",
            "uncertainty": "correlated scenarios/CVaR/regret are diagnostics, not a second hidden forecast",
            "deadline_mechanics": "exact captain/vice/autosub mechanics",
            "same_surface_check": "Official FPL bootstrap/fixtures SHA-256 hashes must match",
            "next_projection_upgrade": "empirical-Bayes shrinkage of small-sample player rates toward role/position priors",
        },
        "recommendation": recommendation,
        "epsilon_convergence": convergence,
        "epsilon_sensitivity": elite.get("epsilon_sensitivity") or [],
        "haaland_scenario": (elite.get("scenarios") or {}).get("haaland"),
        "no_haaland_scenario": (elite.get("scenarios") or {}).get("no_haaland"),
        "robustness": {
            "cvar_scenarios": pinnacle.get("robust_scenarios"),
            "robust_compare": pinnacle.get("robust_compare"),
            "selection_regret": pinnacle.get("selection_regret"),
            "solver_parity": pinnacle.get("solver_parity"),
            "pinnacle_gate": pinnacle.get("pinnacle_gate"),
        },
        "internal_diagnostics": {
            "pinnacle_contract": pinnacle.get("contract"),
            "elite_contract": elite.get("contract"),
            "pinnacle_snapshot_id": _snapshot(pinnacle).get("snapshot_id"),
            "elite_snapshot_id": _snapshot(elite).get("snapshot_id"),
            "pinnacle_content_fingerprint": pinnacle_fp,
            "elite_content_fingerprint": elite_fp,
            "same_official_surface": pinnacle_fp == elite_fp and None not in pinnacle_fp,
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "apex_recommendation_latest.json"
    md_path = output_dir / "apex_recommendation_latest.md"
    answer_context = build_answer_context(payload, pinnacle)
    if not answer_context["safe_to_act"]:
        payload["ready_to_act"] = False
        payload["blockers"] = list(
            dict.fromkeys([*payload["blockers"], *answer_context["blockers"]])
        )
        answer_context = build_answer_context(payload, pinnacle)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "apex_answer_context.json").write_text(
        json.dumps(answer_context, indent=2), encoding="utf-8"
    )

    if ready:
        lines = [
            "# Apex Unified Recommendation",
            "",
            f"Generated: {payload['generated_at']}",
            f"Official surface: `{pinnacle_fp[0][:12]}` / `{pinnacle_fp[1][:12]}`",
            f"Canonical selector: **{selector}**",
            f"Reason: {recommendation['selector_reason']}",
            "",
            "## GW1",
            "",
            f"Captain: **{recommendation['captain']}**",
            f"Vice-captain: **{recommendation['vice_captain']}**",
            f"Expected total with exact mechanics: **{float(recommendation['gw1_expected_total_with_mechanics'] or 0):.2f}**",
            "",
            "### Starting XI",
            "",
            *_table(xi),
            "",
            "### Full 15",
            "",
            *_table(squad),
            "",
            f"Bench GK: **{recommendation['bench_gk']}**",
            "Outfield bench: **" + " → ".join(recommendation["outfield_bench_order"]) + "**",
            "",
            "## Canonical rule",
            "",
            "This is the only user-facing Apex team. Pinnacle max-EV, Elite, CVaR and other solver outputs are internal diagnostics/challengers and must not be presented as separate competing recommendations.",
        ]
    else:
        lines = [
            "# Apex Unified Recommendation — NOT READY",
            "",
            f"Generated: {payload['generated_at']}",
            "",
            "The unified engine withheld a team because the canonical gate is blocked:",
            "",
            *[f"- {blocker}" for blocker in blockers],
        ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))

    if not ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
