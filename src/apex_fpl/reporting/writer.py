from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.source_gate import SafetyGate


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _scenario_payload(sol) -> dict[str, Any]:
    return {
        "status": sol.status,
        "objective": sol.objective,
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "bench": _records(sol.bench),
    }


def write_reports(
    report_dir: Path,
    players: pd.DataFrame,
    projections: pd.DataFrame,
    integrity: pd.DataFrame,
    news_audit: pd.DataFrame,
    scenarios: dict,
    transfer_plan: TransferPlan | None,
    sources: list[SourceStatus],
    gameweeks: list[int],
    safety: SafetyGate,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    players.to_csv(report_dir / "players.csv", index=False)
    projections.to_csv(report_dir / "projections.csv", index=False)
    integrity.to_csv(report_dir / "integrity.csv", index=False)
    news_audit.to_csv(report_dir / "news_audit.csv", index=False)
    pd.DataFrame([s.to_dict() for s in sources]).to_csv(report_dir / "sources.csv", index=False)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gameweeks": gameweeks,
        "sources": [s.to_dict() for s in sources],
        "integrity_warnings": _records(integrity),
        "scenarios": {},
        "transfer_plan": None,
        "safe_to_act": safety.safe_to_act,
        "apex_confidence": safety.confidence,
        "blockers": safety.blockers,
        "warnings": safety.warnings,
    }
    lines = ["# Apex FPL Report", "", f"Generated: {payload['generated_at']}", ""]
    lines += [
        f"**SAFE TO ACT:** {'YES' if safety.safe_to_act else 'NO'}",
        f"**Pipeline confidence:** {safety.confidence:.0%}",
        "",
    ]
    if safety.blockers:
        lines += ["### Blockers", *[f"- {x}" for x in safety.blockers], ""]
    if safety.warnings:
        lines += ["### Warnings", *[f"- {x}" for x in safety.warnings], ""]
    lines += ["## Source health", ""]
    for s in sources:
        mark = "OK" if s.ok else "WARNING"
        lines.append(f"- **{s.name}** — {mark}: {s.detail}")
    lines.append("")

    if not integrity.empty:
        lines += [f"**Integrity warnings:** {len(integrity)} (official FPL identity retained)", ""]

    for name, sol in scenarios.items():
        payload["scenarios"][name] = _scenario_payload(sol)
        lines += [f"## {name}", f"Status: **{sol.status}**", f"Objective: **{sol.objective:.2f}**", ""]
        if not sol.captain.empty:
            lines += [
                f"Captain: **{sol.captain.iloc[0].get('web_name', sol.captain.iloc[0]['player_id'])}**",
                "",
            ]
        if not sol.xi.empty:
            lines += [
                "### XI", "", sol.xi.to_markdown(index=False), "",
                "### Bench", "", sol.bench.to_markdown(index=False), "",
            ]

    if transfer_plan is not None:
        payload["transfer_plan"] = {
            "status": transfer_plan.status,
            "objective": transfer_plan.objective,
            "weeks": transfer_plan.weeks,
        }
        lines += ["## Multi-GW transfer plan", "", f"Status: **{transfer_plan.status}**", ""]
        for week in transfer_plan.weeks:
            lines += [
                f"### GW{week['gw']}",
                f"FT before: {week['free_transfers_before']} | Transfers: {week['transfers']} | "
                f"Hit: -{week['hit_cost']} | Bank after: £{week['bank_after']:.1f}m",
            ]
            if week.get("chip"):
                lines.append(f"Chip: **{week['chip']}**")
            ins = ", ".join(str(x.get("web_name", x["player_id"])) for x in week["transfers_in"]) or "None"
            outs = ", ".join(str(x.get("web_name", x["player_id"])) for x in week["transfers_out"]) or "None"
            captain = week["captain"][0].get("web_name") if week["captain"] else "-"
            lines += [f"Transfers in: {ins}", f"Transfers out: {outs}", f"Captain: **{captain}**", ""]

    (report_dir / "latest.json").write_text(json.dumps(payload, indent=2, default=str))
    (report_dir / "latest.md").write_text("\n".join(lines))
