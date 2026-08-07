from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

COMPONENTS = {
    "xp_appearance": "minutes / appearance",
    "xp_attack": "attacking xG/xA",
    "xp_clean_sheet": "clean-sheet probability",
    "xp_defensive_contribution": "defensive contributions",
    "xp_saves": "goalkeeper saves",
    "xp_bonus_prior": "bonus/BPS prior",
    "xp_set_piece_prior": "penalties / set pieces",
}


def component_summary(projections: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the transparent Apex model components into explainable drivers."""
    present = [col for col in COMPONENTS if col in projections.columns]
    if projections.empty or not present:
        return pd.DataFrame(columns=["player_id", "top_drivers"])
    numeric = projections[["player_id", *present]].copy()
    for col in present:
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce").fillna(0.0)
    grouped = numeric.groupby("player_id", as_index=False)[present].sum()

    driver_text = []
    for _, row in grouped.iterrows():
        ranked = sorted(
            ((COMPONENTS[col], float(row[col])) for col in present if float(row[col]) > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        driver_text.append(
            "; ".join(f"{name} {value:.1f} xP" for name, value in ranked[:3])
            if ranked
            else "no positive Apex-model component"
        )
    grouped["top_drivers"] = driver_text
    return grouped


def build_risk_report(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    integrity: pd.DataFrame,
    news_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Create player-level risk flags instead of hiding uncertainty in one score."""
    risks: dict[int, list[str]] = defaultdict(list)
    severity: dict[int, float] = defaultdict(float)

    for _, row in players.iterrows():
        pid = int(row["player_id"])
        minutes = pd.to_numeric(pd.Series([row.get("expected_minutes")]), errors="coerce").iloc[0]
        p_start = pd.to_numeric(pd.Series([row.get("start_probability")]), errors="coerce").iloc[0]
        p_conf = pd.to_numeric(pd.Series([row.get("projection_confidence")]), errors="coerce").iloc[0]
        role_conf = pd.to_numeric(pd.Series([row.get("role_confidence")]), errors="coerce").iloc[0]
        status = str(row.get("status", "a"))

        if status not in {"a", ""}:
            risks[pid].append(f"official FPL status={status}")
            severity[pid] += 0.40
        if pd.notna(minutes) and float(minutes) < 60:
            risks[pid].append(f"expected minutes only {float(minutes):.0f}")
            severity[pid] += min(0.45, (60 - float(minutes)) / 100)
        elif pd.notna(minutes) and float(minutes) < 72:
            risks[pid].append(f"minutes security moderate ({float(minutes):.0f})")
            severity[pid] += 0.12
        if pd.notna(p_start) and float(p_start) < 0.70:
            risks[pid].append(f"start probability {float(p_start):.0%}")
            severity[pid] += 0.18
        if pd.notna(p_conf) and float(p_conf) < 0.55:
            risks[pid].append(f"projection confidence {float(p_conf):.0%}")
            severity[pid] += 0.18
        if pd.notna(role_conf) and float(role_conf) < 0.55:
            risks[pid].append(f"tactical-role confidence {float(role_conf):.0%}")
            severity[pid] += 0.10

    if not integrity.empty and "player_id" in integrity.columns:
        for pid in pd.to_numeric(integrity["player_id"], errors="coerce").dropna().astype(int).unique():
            risks[int(pid)].append("auxiliary identity conflict (official FPL retained)")
            severity[int(pid)] += 0.08

    if not news_audit.empty and "player_id" in news_audit.columns:
        for _, row in news_audit.iterrows():
            pid = int(row["player_id"])
            multiplier = pd.to_numeric(pd.Series([row.get("multiplier")]), errors="coerce").iloc[0]
            event_type = str(row.get("event_type", "news"))
            headline = str(row.get("headline", ""))
            if pd.notna(multiplier) and float(multiplier) < 0.90:
                risks[pid].append(f"{event_type} news: {headline[:90]}")
                severity[pid] += min(0.30, 1.0 - float(multiplier))

    # Expert disagreement is independently useful even if the overall confidence
    # remains acceptable after source weighting.
    if not projections.empty and "expert_disagreement_sd" in projections.columns:
        disagreement = (
            projections.groupby("player_id")["expert_disagreement_sd"]
            .mean()
            .apply(pd.to_numeric, errors="coerce")
        )
        for pid, value in disagreement.dropna().items():
            if float(value) >= 1.5:
                risks[int(pid)].append(f"projection models disagree (SD {float(value):.2f})")
                severity[int(pid)] += min(0.25, float(value) / 10)

    base_cols = [
        col
        for col in [
            "player_id",
            "web_name",
            "team_name",
            "position",
            "price",
            "expected_minutes",
            "start_probability",
            "projection_confidence",
            "horizon_xp",
        ]
        if col in players.columns
    ]
    out = players[base_cols].copy()
    out["risk_flags"] = out["player_id"].map(lambda pid: " | ".join(risks.get(int(pid), [])))
    out["risk_score"] = out["player_id"].map(lambda pid: min(1.0, severity.get(int(pid), 0.0)))
    return out[out["risk_flags"].astype(str).str.len() > 0].sort_values(
        ["risk_score", "horizon_xp"], ascending=[False, False]
    )


def scenario_comparison(scenarios: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarise multiple independent squad structures on comparable metrics."""
    rows: list[dict[str, Any]] = []
    for name, sol in scenarios.items():
        squad = sol.squad
        xi = sol.xi
        captain = sol.captain
        row: dict[str, Any] = {
            "scenario": name,
            "status": sol.status,
            "solver_objective": float(sol.objective),
            "cost": float(pd.to_numeric(squad.get("price"), errors="coerce").sum())
            if not squad.empty
            else 0.0,
            "squad_horizon_xp": float(
                pd.to_numeric(squad.get("horizon_xp"), errors="coerce").sum()
            )
            if not squad.empty
            else 0.0,
            "xi_gw1_xp": float(pd.to_numeric(xi.get("gw1_xp"), errors="coerce").sum())
            if not xi.empty
            else 0.0,
            "captain_gw1_xp": float(
                pd.to_numeric(captain.get("gw1_xp"), errors="coerce").sum()
            )
            if not captain.empty
            else 0.0,
            "mean_squad_confidence": float(
                pd.to_numeric(squad.get("projection_confidence"), errors="coerce").mean()
            )
            if not squad.empty and "projection_confidence" in squad
            else None,
            "player_ids": sorted(squad["player_id"].astype(int).tolist())
            if not squad.empty
            else [],
        }
        row["gw1_total_with_captain"] = row["xi_gw1_xp"] + row["captain_gw1_xp"]
        rows.append(row)

    if not rows:
        return rows
    best_horizon = max(row["squad_horizon_xp"] for row in rows)
    best_gw1 = max(row["gw1_total_with_captain"] for row in rows)
    for row in rows:
        row["horizon_gap_to_best"] = row["squad_horizon_xp"] - best_horizon
        row["gw1_gap_to_best"] = row["gw1_total_with_captain"] - best_gw1
    return rows
