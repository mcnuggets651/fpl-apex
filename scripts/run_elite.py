#!/usr/bin/env python3
"""Run Apex Elite 10.0 as a lexicographic xP-first decision layer."""
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
    return (
        None
        if frame.empty or "web_name" not in frame.columns
        else str(frame.iloc[0]["web_name"])
    )


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
        raise SystemExit(
            "Elite blocked by Apex production gate: "
            + ("; ".join(out.safety.blockers) or "unknown production blocker")
        )

    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    team_ids = official.players[["player_id", "team"]].drop_duplicates("player_id")
    players = out.players.drop(columns=["team"], errors="ignore").merge(
        team_ids, on="player_id", how="left", validate="one_to_one"
    )
    captain_eligible = captain_eligible_ids(players)
    if len(captain_eligible) < 2:
        raise SystemExit("Elite has fewer than two captain/vice eligible players")

    weights = EliteWeights()
    surface = build_elite_projection_surface(players, out.projections, weights)
    common = dict(
        players=players,
        gameweeks=out.gameweeks,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        captain_eligible=captain_eligible,
    )

    haaland = players[players["web_name"].astype(str).str.casefold().eq("haaland")]
    haaland_id = int(haaland.iloc[0]["player_id"]) if not haaland.empty else None

    scenario_rules: dict[str, dict[str, set[int]]] = {
        "unrestricted": {"locked": set(), "banned": set()}
    }
    if haaland_id is not None:
        scenario_rules["haaland"] = {"locked": {haaland_id}, "banned": set()}
        scenario_rules["no_haaland"] = {"locked": set(), "banned": {haaland_id}}

    # Stage 1: establish the true maximum-xP reference in each scenario.
    references = {}
    for name, rule in scenario_rules.items():
        references[name] = optimise_initial_horizon(
            **common,
            projections=surface,
            projection_col="xp",
            locked=rule["locked"],
            banned=rule["banned"],
        )
        if references[name].status != "Optimal":
            raise SystemExit(f"maximum-EV reference failed for scenario: {name}")

    # Stage 2: maximise Elite utility only inside a tight raw-xP near-optimal band.
    selections = {}
    final = {}
    floors = {}
    for name, rule in scenario_rules.items():
        reference = references[name]
        floor = float(reference.objective) * (1.0 - weights.max_ev_regret_fraction)
        floors[name] = floor
        selections[name] = optimise_initial_horizon(
            **common,
            projections=surface,
            projection_col="elite_score",
            reference_projection_col="xp",
            min_reference_objective=floor,
            display_projection_col="xp",
            locked=rule["locked"],
            banned=rule["banned"],
        )
        if selections[name].status != "Optimal":
            raise SystemExit(f"Elite near-optimal selection failed for scenario: {name}")

        # The 15-player squad comes from Elite's secondary objective. XI/captain/vice
        # are then re-optimised on canonical xP, because those deadline mechanics
        # should not be decided by a non-points utility.
        final[name] = optimise_initial_horizon(
            **common,
            projections=surface,
            projection_col="xp",
            locked=_ids(selections[name].squad),
        )
        if final[name].status != "Optimal":
            raise SystemExit(f"raw-xP rescore failed for scenario: {name}")

    max_ev = references["unrestricted"]
    elite_selection = selections["unrestricted"]
    elite = final["unrestricted"]
    ev_regret = float(max_ev.objective - elite.objective)
    ev_regret_pct = float(ev_regret / max_ev.objective) if max_ev.objective else 0.0

    # The epsilon is deliberately provisional rather than treated as a magic
    # calibrated constant. Generate a small Pareto/sensitivity frontier on the same
    # live surface so the final decision can see whether Elite is stable or merely
    # exploiting an arbitrary regret allowance. The configured 0.5% solution reuses
    # the solve above; other rows add only the minimum extra solves needed.
    epsilon_grid = (0.0, 0.0025, weights.max_ev_regret_fraction, 0.01)
    epsilon_rows = []
    for epsilon in dict.fromkeys(float(x) for x in epsilon_grid):
        if abs(epsilon - weights.max_ev_regret_fraction) < 1e-12:
            selection = elite_selection
            recommendation = elite
        else:
            floor = float(max_ev.objective) * (1.0 - epsilon)
            selection = optimise_initial_horizon(
                **common,
                projections=surface,
                projection_col="elite_score",
                reference_projection_col="xp",
                min_reference_objective=floor,
                display_projection_col="xp",
            )
            if selection.status != "Optimal":
                raise SystemExit(f"Elite epsilon sensitivity solve failed: {epsilon:.4%}")
            recommendation = optimise_initial_horizon(
                **common,
                projections=surface,
                projection_col="xp",
                locked=_ids(selection.squad),
            )
            if recommendation.status != "Optimal":
                raise SystemExit(f"Elite epsilon raw-xP rescore failed: {epsilon:.4%}")

        regret = float(max_ev.objective - recommendation.objective)
        regret_pct = float(regret / max_ev.objective) if max_ev.objective else 0.0
        epsilon_rows.append(
            {
                "epsilon": epsilon,
                "raw_ev_floor": float(max_ev.objective) * (1.0 - epsilon),
                "raw_ev_objective": float(recommendation.objective),
                "raw_ev_regret": regret,
                "raw_ev_regret_pct": regret_pct,
                "squad_overlap_vs_max_ev": len(_ids(max_ev.squad) & _ids(recommendation.squad)),
                "changed_player_ids_vs_max_ev": sorted(_ids(max_ev.squad) ^ _ids(recommendation.squad)),
                "captain": _name(recommendation.captain),
                "squad_player_ids": sorted(_ids(recommendation.squad)),
            }
        )

    payload = {
        "contract": "apex-elite-10-v3-lexicographic",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_to_act": bool(out.safety.safe_to_act),
        "full_apex_ready": bool(out.safety.full_apex_ready),
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "objective": {
            "primary": "maximise canonical Pinnacle ensemble xp",
            "secondary": "maximise Elite 35/20/15/10/10/5/5 utility",
            "method": "epsilon-constraint / lexicographic optimisation",
            "max_raw_ev_regret_fraction": weights.max_ev_regret_fraction,
            "epsilon_is_calibrated": False,
            "epsilon_sensitivity_grid": [row["epsilon"] for row in epsilon_rows],
            "unrestricted_raw_ev_floor": floors["unrestricted"],
            "deadline_lineup_and_captain_surface": "xp",
        },
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
        "elite_secondary_selection": _solution(elite_selection),
        "elite": _solution(elite),
        "elite_vs_max_ev": {
            "squad_overlap": len(_ids(max_ev.squad) & _ids(elite.squad)),
            "changed_player_ids": sorted(_ids(max_ev.squad) ^ _ids(elite.squad)),
            "max_ev_objective": float(max_ev.objective),
            "elite_squad_raw_ev_objective": float(elite.objective),
            "raw_ev_regret": ev_regret,
            "raw_ev_regret_pct": ev_regret_pct,
            "configured_max_regret_pct": weights.max_ev_regret_fraction,
        },
        "epsilon_sensitivity": epsilon_rows,
        "scenarios": {},
    }

    for name in scenario_rules:
        reference = references[name]
        recommendation = final[name]
        regret = float(reference.objective - recommendation.objective)
        regret_pct = float(regret / reference.objective) if reference.objective else 0.0
        payload["scenarios"][name] = {
            "maximum_ev_reference": _solution(reference),
            "elite_secondary_selection": _solution(selections[name]),
            "elite": _solution(recommendation),
            "raw_ev_floor": floors[name],
            "raw_ev_regret": regret,
            "raw_ev_regret_pct": regret_pct,
        }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "elite_latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    xi = elite.xi[
        [
            c
            for c in ["web_name", "team_name", "position", "price", "gw1_xp"]
            if c in elite.xi.columns
        ]
    ]
    squad = elite.squad[
        [
            c
            for c in ["web_name", "team_name", "position", "price", "gw1_xp"]
            if c in elite.squad.columns
        ]
    ]
    sensitivity_lines = [
        "| epsilon | raw xP | regret | overlap vs max-EV | captain |",
        "|---:|---:|---:|---:|:---|",
    ]
    for row in epsilon_rows:
        sensitivity_lines.append(
            f"| {row['epsilon']:.2%} | {row['raw_ev_objective']:.3f} | "
            f"{row['raw_ev_regret_pct']:.2%} | {row['squad_overlap_vs_max_ev']}/15 | "
            f"{row['captain'] or ''} |"
        )

    lines = [
        "# Apex Elite 10.0 — xP-first lexicographic",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Decision rule",
        "",
        "1. Maximise canonical Pinnacle ensemble xP.",
        "2. Define a near-optimal xP band; the current 0.5% band is provisional, not calibrated.",
        "3. Inside that band, maximise the Elite 35/20/15/10/10/5/5 secondary utility.",
        "4. Re-optimise XI, captain and vice on raw xP for the selected 15.",
        "5. Inspect the epsilon sensitivity frontier before treating Elite as superior to max-EV.",
        "",
        "## Elite unrestricted",
        "",
        f"Captain: **{_name(elite.captain)}**",
        f"Vice-captain: **{_name(elite.vice_captain)}**",
        f"Raw maximum-EV reference: **{max_ev.objective:.3f} xP**",
        f"Elite selected-squad raw EV: **{elite.objective:.3f} xP**",
        f"Raw-EV regret: **{ev_regret:.3f} xP ({ev_regret_pct:.2%})**",
        f"Configured provisional maximum regret: **{weights.max_ev_regret_fraction:.2%}**",
        "",
        "## Epsilon sensitivity — unrestricted",
        "",
        *sensitivity_lines,
        "",
        "### GW1 XI — raw xP",
        "",
        xi.to_markdown(index=False),
        "",
        "### 15-player squad — raw xP",
        "",
        squad.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "Elite never creates or modifies expected points. It is a secondary selector among squads that are already near maximum-EV. If tiny changes in epsilon materially change the squad, maximum-EV remains the safer canonical recommendation until no-hindsight calibration establishes a regret band.",
    ]
    md_path = output_dir / "elite_latest.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
