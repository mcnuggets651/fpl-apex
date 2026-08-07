from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.reporting.explain import (
    build_risk_report,
    component_summary,
    scenario_comparison,
)
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.safety import SafetyAssessment


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _annotate(df: pd.DataFrame, drivers: pd.DataFrame, risks: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if not drivers.empty:
        out = out.merge(
            drivers[[c for c in ["player_id", "top_drivers"] if c in drivers.columns]],
            on="player_id",
            how="left",
        )
    if not risks.empty:
        risk_cols = [c for c in ["player_id", "risk_flags", "risk_score"] if c in risks.columns]
        out = out.merge(risks[risk_cols], on="player_id", how="left")
    if "risk_flags" in out:
        out["risk_flags"] = out["risk_flags"].fillna("")
    if "risk_score" in out:
        out["risk_score"] = pd.to_numeric(out["risk_score"], errors="coerce").fillna(0.0)
    return out


def _scenario_payload(sol, drivers: pd.DataFrame, risks: pd.DataFrame) -> dict[str, Any]:
    return {
        "status": sol.status,
        "objective": sol.objective,
        "squad": _records(_annotate(sol.squad, drivers, risks)),
        "xi": _records(_annotate(sol.xi, drivers, risks)),
        "captain": _records(_annotate(sol.captain, drivers, risks)),
        "vice_captain": _records(_annotate(sol.vice_captain, drivers, risks)),
        "bench": _records(_annotate(sol.bench, drivers, risks)),
    }


def _captain_line(label: str, frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    row = frame.iloc[0]
    name = row.get("web_name", row.get("player_id", "-"))
    parts = [f"{label}: **{name}**"]
    if pd.notna(row.get("gw1_xp")):
        parts.append(f"GW xP {float(row['gw1_xp']):.2f}")
    if pd.notna(row.get("expected_minutes")):
        parts.append(f"xMins {float(row['expected_minutes']):.0f}")
    if pd.notna(row.get("projection_confidence")):
        parts.append(f"confidence {float(row['projection_confidence']):.0%}")
    if row.get("tactical_role"):
        parts.append(str(row["tactical_role"]))
    if row.get("top_drivers"):
        parts.append(str(row["top_drivers"]))
    if row.get("risk_flags"):
        parts.append(f"risk: {row['risk_flags']}")
    return " — ".join(parts)


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
    safety: SafetyAssessment | None = None,
    snapshot: dict | None = None,
    upstreams: dict | None = None,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)

    drivers = component_summary(projections)
    risks = build_risk_report(players, projections, integrity, news_audit)
    comparisons = scenario_comparison(scenarios)

    players_with_drivers = players.merge(drivers, on="player_id", how="left") if not drivers.empty else players.copy()
    players_with_drivers.to_csv(report_dir / "players.csv", index=False)
    projections.to_csv(report_dir / "projections.csv", index=False)
    integrity.to_csv(report_dir / "integrity.csv", index=False)
    news_audit.to_csv(report_dir / "news_audit.csv", index=False)
    drivers.to_csv(report_dir / "player_drivers.csv", index=False)
    risks.to_csv(report_dir / "risk_report.csv", index=False)
    pd.DataFrame([s.to_dict() for s in sources]).to_csv(report_dir / "sources.csv", index=False)
    (report_dir / "scenario_comparison.json").write_text(
        json.dumps(comparisons, indent=2, default=str)
    )
    (report_dir / "risk_report.json").write_text(
        json.dumps(_records(risks), indent=2, default=str)
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gameweeks": gameweeks,
        "safe_to_act": safety.safe_to_act if safety else False,
        "full_apex_ready": safety.full_apex_ready if safety else False,
        "safety": safety.to_dict() if safety else None,
        "official_snapshot": snapshot or {},
        "upstreams": upstreams or {},
        "sources": [s.to_dict() for s in sources],
        "integrity_warnings": _records(integrity),
        "scenario_comparison": comparisons,
        "risk_report": _records(risks),
        "scenarios": {},
        "transfer_plan": None,
    }

    lines = ["# Apex FPL Report", "", f"Generated: {payload['generated_at']}", ""]
    if safety:
        lines += [
            "## Decision gate",
            "",
            f"**safe_to_act:** `{str(safety.safe_to_act).lower()}`",
            f"**full_apex_ready:** `{str(safety.full_apex_ready).lower()}`",
            "",
        ]
        for item in safety.blockers:
            lines.append(f"- BLOCKER: {item}")
        for item in safety.warnings:
            lines.append(f"- WARNING: {item}")
        lines.append("")

    if snapshot:
        lines += [
            "## Official snapshot",
            "",
            f"- ID: `{snapshot.get('snapshot_id', '')}`",
            f"- Players: {snapshot.get('players', '')}",
            f"- Fixtures: {snapshot.get('fixtures', '')}",
            f"- Bootstrap SHA256: `{snapshot.get('bootstrap_sha256', '')}`",
            "",
        ]

    lines += ["## Source health", ""]
    for source in sources:
        mark = "OK" if source.ok else "WARNING"
        configured = "configured" if source.configured else "not configured"
        version = f" @ `{source.version}`" if source.version else ""
        lines.append(
            f"- **{source.name}** — {mark} ({configured}){version}: {source.detail}"
        )
    lines.append("")

    if not integrity.empty:
        lines += [
            f"**Integrity warnings:** {len(integrity)} (official FPL identity retained)",
            "",
        ]

    if comparisons:
        comparison_table = pd.DataFrame(comparisons).drop(columns=["player_ids"], errors="ignore")
        display_cols = [
            c
            for c in [
                "scenario",
                "cost",
                "gw1_total_with_captain",
                "gw1_gap_to_best",
                "squad_horizon_xp",
                "horizon_gap_to_best",
                "mean_squad_confidence",
            ]
            if c in comparison_table.columns
        ]
        lines += [
            "## Scenario comparison",
            "",
            comparison_table[display_cols].to_markdown(index=False, floatfmt=".2f"),
            "",
        ]

    for name, sol in scenarios.items():
        annotated_xi = _annotate(sol.xi, drivers, risks)
        annotated_cap = _annotate(sol.captain, drivers, risks)
        annotated_vice = _annotate(sol.vice_captain, drivers, risks)
        annotated_bench = _annotate(sol.bench, drivers, risks)
        payload["scenarios"][name] = _scenario_payload(sol, drivers, risks)
        lines += [
            f"## {name}",
            f"Status: **{sol.status}**",
            f"Solver objective: **{sol.objective:.2f}**",
            "",
        ]
        cap_line = _captain_line("Captain", annotated_cap)
        vice_line = _captain_line("Vice-captain", annotated_vice)
        if cap_line:
            lines.append(cap_line)
        if vice_line:
            lines.append(vice_line)
        if cap_line or vice_line:
            lines.append("")
        if not annotated_xi.empty:
            show_cols = [
                c
                for c in [
                    "web_name",
                    "team_name",
                    "position",
                    "price",
                    "expected_minutes",
                    "tactical_role",
                    "gw1_xp",
                    "xpts_3",
                    "xpts_5",
                    "xpts_8",
                    "projection_confidence",
                    "top_drivers",
                    "risk_flags",
                ]
                if c in annotated_xi.columns
            ]
            bench_cols = [c for c in show_cols if c in annotated_bench.columns]
            lines += [
                "### XI",
                "",
                annotated_xi[show_cols].to_markdown(index=False, floatfmt=".2f"),
                "",
                "### Bench",
                "",
                annotated_bench[bench_cols].to_markdown(index=False, floatfmt=".2f"),
                "",
            ]

    if not risks.empty:
        risk_cols = [
            c
            for c in [
                "web_name",
                "team_name",
                "position",
                "expected_minutes",
                "projection_confidence",
                "risk_score",
                "risk_flags",
            ]
            if c in risks.columns
        ]
        lines += [
            "## Highest current player risks",
            "",
            risks.head(20)[risk_cols].to_markdown(index=False, floatfmt=".2f"),
            "",
        ]

    if transfer_plan is not None:
        payload["transfer_plan"] = {
            "status": transfer_plan.status,
            "objective": transfer_plan.objective,
            "weeks": transfer_plan.weeks,
        }
        lines += [
            "## Multi-GW transfer plan",
            "",
            f"Status: **{transfer_plan.status}**",
            "",
        ]
        for week in transfer_plan.weeks:
            lines += [
                f"### GW{week['gw']}",
                f"FT before: {week['free_transfers_before']} | Transfers: {week['transfers']} | "
                f"Hit: -{week['hit_cost']} | Bank after: £{week['bank_after']:.1f}m",
            ]
            if week.get("chip"):
                lines.append(f"Chip: **{week['chip']}**")
            ins = (
                ", ".join(str(x.get("web_name", x["player_id"])) for x in week["transfers_in"])
                or "None"
            )
            outs = (
                ", ".join(str(x.get("web_name", x["player_id"])) for x in week["transfers_out"])
                or "None"
            )
            captain = week["captain"][0].get("web_name") if week["captain"] else "-"
            vice = (
                week.get("vice_captain", [{}])[0].get("web_name", "-")
                if week.get("vice_captain")
                else "-"
            )
            lines += [
                f"Transfers in: {ins}",
                f"Transfers out: {outs}",
                f"Captain: **{captain}**",
                f"Vice-captain: **{vice}**",
                "",
            ]

    (report_dir / "latest.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    (report_dir / "latest.md").write_text("\n".join(lines))
