#!/usr/bin/env python3
"""Run the Apex Elite 10.0 ceiling-weighted initial-squad optimiser.

Elite is an additional decision lens above Pinnacle, not a replacement for the
maximum-EV surface. Every Elite squad is re-scored on raw ensemble expected points
so a fashionable/high-ceiling weighting cannot silently hide a material EV loss.
"""
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
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty or "player_id" not in frame.columns:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _solution(sol) -> dict:
    return {
        "status": sol.status,
        "objective": float(sol.objective),
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "vice_captain": _records(sol.vice_captain),
        "bench": _records(sol.bench),
    }


def _name(frame: pd.DataFrame) -> str | None:
    if frame.empty or "web_name" not in frame.columns:
        return None
    return str(frame.iloc[0]["web_name"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        blockers = "; ".join(out.safety.blockers) or "unknown production blocker"
        raise SystemExit(f"Elite blocked by Apex production gate: {blockers}")

    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    team_ids = official.players[["player_id", "team"]].drop_duplicates("player_id")
    players = out.players.drop(columns=["team"], errors="ignore").merge(
        team_ids, on="player_id", how="left", validate="one_to_one"
    )
    captain_eligible = captain_eligible_ids(players)
    if len(captain_eligible) < 2:
        raise SystemExit("Elite has fewer than two captain/vice eligible players")

    weights = EliteWeights()
    elite_surface = build_elite_projection_surface(players, out.projections, weights)
    common = dict(
        players=players,
        gameweeks=out.gameweeks,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        captain_eligible=captain_eligible,
    )

    max_ev = optimise_initial_horizon(
        **common,
        projections=elite_surface,
        projection_col="xp",
    )
    elite = optimise_initial_horizon(
        **common,
        projections=elite_surface,
        projection_col="elite_score",
    )

    haaland = players[players["web_name"].astype(str).str.casefold().eq("haaland")]
    haaland_id = int(haaland.iloc[0]["player_id"]) if not haaland.empty else None
    elite_haaland = None
    elite_no_haaland = None
    if haaland_id is not None:
        elite_haaland = optimise_initial_horizon(
            **common,
            projections=elite_surface,
            projection_col="elite_score",
            locked={haaland_id},
        )
        elite_no_haaland = optimise_initial_horizon(
            **common,
            projections=elite_surface,
            projection_col="elite_score",
            banned={haaland_id},
        )

    candidates = {"unrestricted": elite}
    if elite_haaland is not None:
        candidates["haaland"] = elite_haaland
    if elite_no_haaland is not None:
        candidates["no_haaland"] = elite_no_haaland

    rescored: dict[str, object] = {}
    for name, sol in candidates.items():
        if sol.status != "Optimal":
            continue
        # Lock all 15 Elite-selected players and optimise their XI/captain on raw
        # ensemble xP. This publishes the real expected-points cost of the utility lens.
        rescored[name] = optimise_initial_horizon(
            **common,
            projections=elite_surface,
            projection_col="xp",
            locked=_ids(sol.squad),
        )

    if elite.status != "Optimal" or max_ev.status != "Optimal":
        raise SystemExit("Elite or maximum-EV optimiser failed")

    max_ev_ids = _ids(max_ev.squad)
    elite_ids = _ids(elite.squad)
    elite_ev = rescored.get("unrestricted")
    elite_ev_objective = float(elite_ev.objective) if elite_ev is not None else None
    ev_regret = (
        float(max_ev.objective - elite_ev_objective)
        if elite_ev_objective is not None
        else None
    )

    payload = {
        "contract": "apex-elite-10-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_to_act": bool(out.safety.safe_to_act),
        "full_apex_ready": bool(out.safety.full_apex_ready),
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "weights": {
            "expected_attacking_returns": weights.attack,
            "minutes_start_probability": weights.minutes,
            "captaincy_value": weights.captaincy,
            "set_pieces_penalties": weights.set_pieces,
            "fixture_quality": weights.fixture,
            "bonus_defcon": weights.bonus_defcon,
            "price_efficiency": weights.value,
        },
        "maximum_ev_reference": _solution(max_ev),
        "elite": _solution(elite),
        "elite_raw_ev_rescore": _solution(elite_ev) if elite_ev is not None else None,
        "elite_vs_max_ev": {
            "squad_overlap": len(max_ev_ids & elite_ids),
            "changed_player_ids": sorted(max_ev_ids ^ elite_ids),
            "max_ev_objective": float(max_ev.objective),
            "elite_squad_raw_ev_objective": elite_ev_objective,
            "raw_ev_regret": ev_regret,
        },
        "scenarios": {
            name: {
                "elite": _solution(sol),
                "raw_ev_rescore": _solution(rescored[name]) if name in rescored else None,
            }
            for name, sol in candidates.items()
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "elite_latest.json"
    md_path = output_dir / "elite_latest.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    xi = elite.xi[[c for c in ["web_name", "team_name", "position", "price", "gw1_xp"] if c in elite.xi.columns]]
    squad = elite.squad[[c for c in ["web_name", "team_name", "position", "price", "gw1_xp"] if c in elite.squad.columns]]
    lines = [
        "# Apex Elite 10.0",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Objective weights",
        "",
        "- 35% expected attacking returns (xG/xA, shots, big chances)",
        "- 20% expected minutes / start probability",
        "- 15% captaincy value",
        "- 10% set pieces & penalties",
        "- 10% fixture quality",
        "- 5% bonus & DEFCON",
        "- 5% price efficiency",
        "",
        "## Elite unrestricted",
        "",
        f"Captain: **{_name(elite.captain)}**",
        f"Vice-captain: **{_name(elite.vice_captain)}**",
        f"Elite utility objective: **{elite.objective:.3f}**",
        f"Raw maximum-EV reference objective: **{max_ev.objective:.3f}**",
        f"Elite squad re-scored on raw xP: **{elite_ev_objective:.3f}**" if elite_ev_objective is not None else "Elite raw xP rescore unavailable",
        f"Raw-EV regret vs pure maximum-EV: **{ev_regret:.3f}**" if ev_regret is not None else "Raw-EV regret unavailable",
        "",
        "### GW1 XI",
        "",
        xi.to_markdown(index=False),
        "",
        "### 15-player squad",
        "",
        squad.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "Elite is a ceiling-weighted selection lens. The raw-EV rescore is mandatory: if Elite sacrifices too much ensemble expected points, maximum-EV remains the stronger decision.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
