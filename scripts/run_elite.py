#!/usr/bin/env python3
"""Run Apex Elite 10.0 with canonical xP as the optimisation anchor."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.elite import EliteWeights, build_elite_projection_surface
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.services.decision_eligibility import captain_eligible_ids
from apex_fpl.services.pipeline import run_pipeline


def _records(df: pd.DataFrame) -> list[dict]:
    return [] if df.empty else json.loads(df.to_json(orient="records"))


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty or "player_id" not in frame.columns:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _solution(sol) -> dict:
    return {"status": sol.status, "objective": float(sol.objective), "squad": _records(sol.squad), "xi": _records(sol.xi), "captain": _records(sol.captain), "vice_captain": _records(sol.vice_captain), "bench": _records(sol.bench)}


def _name(frame: pd.DataFrame) -> str | None:
    return None if frame.empty or "web_name" not in frame.columns else str(frame.iloc[0]["web_name"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()
    settings = load_settings()
    out = run_pipeline(settings, horizon=args.horizon, scenario="both", force=args.force, plan_transfers=False)
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        raise SystemExit(f"Elite blocked by Apex production gate: {'; '.join(out.safety.blockers) or 'unknown production blocker'}")

    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    team_ids = official.players[["player_id", "team"]].drop_duplicates("player_id")
    players = out.players.drop(columns=["team"], errors="ignore").merge(team_ids, on="player_id", how="left", validate="one_to_one")
    captain_eligible = captain_eligible_ids(players)
    if len(captain_eligible) < 2:
        raise SystemExit("Elite has fewer than two captain/vice eligible players")

    weights = EliteWeights()
    surface = build_elite_projection_surface(players, out.projections, weights)
    common = dict(players=players, gameweeks=out.gameweeks, budget=settings.budget, max_per_team=settings.max_per_team, decay=settings.fixture_decay, captain_eligible=captain_eligible)
    max_ev = optimise_initial_horizon(**common, projections=surface, projection_col="xp")
    elite = optimise_initial_horizon(**common, projections=surface, projection_col="elite_decision_xp")

    haaland = players[players["web_name"].astype(str).str.casefold().eq("haaland")]
    haaland_id = int(haaland.iloc[0]["player_id"]) if not haaland.empty else None
    candidates = {"unrestricted": elite}
    if haaland_id is not None:
        candidates["haaland"] = optimise_initial_horizon(**common, projections=surface, projection_col="elite_decision_xp", locked={haaland_id})
        candidates["no_haaland"] = optimise_initial_horizon(**common, projections=surface, projection_col="elite_decision_xp", banned={haaland_id})

    rescored = {}
    for name, sol in candidates.items():
        if sol.status == "Optimal":
            rescored[name] = optimise_initial_horizon(**common, projections=surface, projection_col="xp", locked=_ids(sol.squad))
    if elite.status != "Optimal" or max_ev.status != "Optimal":
        raise SystemExit("Elite or maximum-EV optimiser failed")

    elite_ev = rescored.get("unrestricted")
    elite_ev_objective = float(elite_ev.objective) if elite_ev is not None else None
    ev_regret = float(max_ev.objective - elite_ev_objective) if elite_ev_objective is not None else None
    ev_regret_pct = float(ev_regret / max_ev.objective) if ev_regret is not None and max_ev.objective else None
    payload = {
        "contract": "apex-elite-10-v2-xp-anchored",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_to_act": bool(out.safety.safe_to_act), "full_apex_ready": bool(out.safety.full_apex_ready),
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "objective": {"canonical_forecast": "xp", "decision_surface": "elite_decision_xp", "max_xp_adjustment": weights.max_xp_adjustment, "rule": "raw Pinnacle xP multiplied by a bounded +/-5% Elite evidence modifier"},
        "weights": {"expected_attacking_returns": weights.attack, "minutes_start_probability": weights.minutes, "captaincy_value": weights.captaincy, "set_pieces_penalties": weights.set_pieces, "fixture_quality": weights.fixture, "bonus_defcon": weights.bonus_defcon, "price_efficiency": weights.value},
        "maximum_ev_reference": _solution(max_ev), "elite": _solution(elite),
        "elite_raw_ev_rescore": _solution(elite_ev) if elite_ev is not None else None,
        "elite_vs_max_ev": {"squad_overlap": len(_ids(max_ev.squad) & _ids(elite.squad)), "changed_player_ids": sorted(_ids(max_ev.squad) ^ _ids(elite.squad)), "max_ev_objective": float(max_ev.objective), "elite_squad_raw_ev_objective": elite_ev_objective, "raw_ev_regret": ev_regret, "raw_ev_regret_pct": ev_regret_pct},
        "scenarios": {name: {"elite": _solution(sol), "raw_ev_rescore": _solution(rescored[name]) if name in rescored else None} for name, sol in candidates.items()},
    }
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "elite_latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Report real raw xP for the selected squad/XI, never the Elite utility as xP.
    report_sol = elite_ev if elite_ev is not None else elite
    xi = report_sol.xi[[c for c in ["web_name", "team_name", "position", "price", "gw1_xp"] if c in report_sol.xi.columns]]
    squad = report_sol.squad[[c for c in ["web_name", "team_name", "position", "price", "gw1_xp"] if c in report_sol.squad.columns]]
    lines = ["# Apex Elite 10.0 — xP anchored", "", f"Generated: {payload['generated_at']}", "", "## Objective", "", "Pinnacle ensemble xP is canonical. Elite applies only a bounded ±5% evidence modifier using the 35/20/15/10/10/5/5 profile.", "", "## Elite unrestricted", "", f"Captain: **{_name(report_sol.captain)}**", f"Vice-captain: **{_name(report_sol.vice_captain)}**", f"Elite decision objective: **{elite.objective:.3f}**", f"Raw maximum-EV reference: **{max_ev.objective:.3f} xP**", f"Elite squad raw-EV rescore: **{elite_ev_objective:.3f} xP**" if elite_ev_objective is not None else "Elite raw xP rescore unavailable", f"Raw-EV regret: **{ev_regret:.3f} xP ({ev_regret_pct:.2%})**" if ev_regret_pct is not None else "Raw-EV regret unavailable", "", "### GW1 XI — real raw xP", "", xi.to_markdown(index=False), "", "### 15-player squad — real raw xP", "", squad.to_markdown(index=False), "", "## Interpretation", "", "Elite is now a controlled decision modifier around expected points, not an alternative synthetic forecast. Haaland/no-Haaland scenarios are generated on the same surface and must be compared by raw xP rescore before publication."]
    md_path = output_dir / "elite_latest.md"; md_path.write_text("\n".join(lines) + "\n", encoding="utf-8"); print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__": main()
