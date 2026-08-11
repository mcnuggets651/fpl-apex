#!/usr/bin/env python3
"""Run Apex Elite 10.0 as a lexicographic xP-first diagnostic layer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.models.elite import EliteWeights, build_elite_projection_surface
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics
from apex_fpl.services.decision_eligibility import captain_eligible_ids
from apex_fpl.services.decision_bundle import DecisionBundle

CONVERGENCE_MIN_OVERLAP = 13
CONVERGENCE_EPSILONS = (0.0025, 0.005, 0.01)


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
    if frame.empty or "web_name" not in frame.columns:
        return None
    return str(frame.iloc[0]["web_name"])


def _convergence(epsilon_rows: list[dict], max_ev_captain: str | None) -> dict:
    by_epsilon = {round(float(row["epsilon"]), 6): row for row in epsilon_rows}
    evaluated = []
    for epsilon in CONVERGENCE_EPSILONS:
        row = by_epsilon.get(round(epsilon, 6))
        if row is None:
            return {
                "converged": False,
                "rule": ">=13/15 overlap with max-EV and same captain at 0.25%, 0.50%, 1.00%",
                "reason": f"missing epsilon frontier row {epsilon:.2%}",
                "fallback": "maximum_ev",
            }
        overlap_ok = int(row["squad_overlap_vs_max_ev"]) >= CONVERGENCE_MIN_OVERLAP
        captain_ok = row.get("captain") == max_ev_captain
        evaluated.append(
            {
                "epsilon": epsilon,
                "overlap": int(row["squad_overlap_vs_max_ev"]),
                "captain": row.get("captain"),
                "overlap_ok": overlap_ok,
                "captain_ok": captain_ok,
                "passes": overlap_ok and captain_ok,
            }
        )
    converged = all(row["passes"] for row in evaluated)
    return {
        "converged": converged,
        "rule": ">=13/15 overlap with max-EV and same captain at 0.25%, 0.50%, 1.00%",
        "minimum_overlap": CONVERGENCE_MIN_OVERLAP,
        "required_same_captain": True,
        "max_ev_captain": max_ev_captain,
        "evaluated": evaluated,
        "fallback": "elite" if converged else "maximum_ev",
    }


def _gw1_xp(projections: pd.DataFrame, gw: int) -> dict[int, float]:
    d = projections[projections["gw"] == int(gw)]
    grouped = d.groupby("player_id")["xp"].sum()
    return {int(pid): float(value) for pid, value in grouped.items()}


def _appearance(players: pd.DataFrame) -> dict[int, float]:
    probs = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): float(prob)
        for pid, prob in zip(players["player_id"].astype(int), probs)
    }


def _mechanics(sol, projections, gw, players, captain_eligible) -> dict:
    result = optimise_gameweek_mechanics(
        sol.squad,
        sol.xi,
        _gw1_xp(projections, gw),
        _appearance(players),
        captain_eligible=captain_eligible,
    ).to_dict()
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]].drop_duplicates("player_id").itertuples(index=False)
    }
    result["captain_name"] = names.get(result["captain_id"], str(result["captain_id"]))
    result["vice_captain_name"] = names.get(result["vice_captain_id"], str(result["vice_captain_id"]))
    result["bench_gk_name"] = names.get(result["bench_gk_id"], str(result["bench_gk_id"]))
    result["outfield_bench_order_names"] = [names.get(pid, str(pid)) for pid in result["outfield_bench_order"]]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deprecated compatibility flag; source refresh occurs only when building the bundle.",
    )
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    settings = bundle.settings
    if [int(gw) for gw in out.gameweeks] != [int(gw) for gw in out.gameweeks[: args.horizon]]:
        raise SystemExit(
            "requested horizon does not match the sealed decision bundle; rebuild the bundle"
        )
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        raise SystemExit(
            "Elite blocked by Apex production gate: "
            + ("; ".join(out.safety.blockers) or "unknown production blocker")
        )

    players = out.players.copy()
    if "team" not in players or players["team"].isna().any():
        raise SystemExit("sealed player universe contains missing official team IDs")
    captain_eligible = captain_eligible_ids(players)
    if len(captain_eligible) < 2:
        raise SystemExit("Elite has fewer than two captain/vice eligible players")

    weights = EliteWeights()
    surface = build_elite_projection_surface(players, out.projections, weights)
    common = dict(
        players=players,
        gameweeks=out.gameweeks,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=float(settings["fixture_decay"]),
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

    selections, final, floors = {}, {}, {}
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

    epsilon_grid = (0.0, 0.0025, weights.max_ev_regret_fraction, 0.01)
    epsilon_rows = []
    for epsilon in dict.fromkeys(float(x) for x in epsilon_grid):
        if abs(epsilon - weights.max_ev_regret_fraction) < 1e-12:
            selection, recommendation = elite_selection, elite
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

    convergence = _convergence(epsilon_rows, _name(max_ev.captain))
    mechanics = {
        name: _mechanics(sol, surface, out.gameweeks[0], players, captain_eligible)
        for name, sol in final.items()
    }
    max_ev_mechanics = _mechanics(max_ev, surface, out.gameweeks[0], players, captain_eligible)

    payload = {
        "contract": "apex-elite-10-v4-diagnostic",
        "generated_at": bundle.created_at,
        "decision_bundle": bundle.lineage_summary(),
        "decision_bundle_id": bundle.bundle_id,
        "safe_to_act": bool(out.safety.safe_to_act),
        "full_apex_ready": bool(out.safety.full_apex_ready),
        "official_snapshot": out.snapshot,
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "role": "diagnostic_secondary_selector_not_user_facing",
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
        "maximum_ev_gw1_mechanics": max_ev_mechanics,
        "elite_secondary_selection": _solution(elite_selection),
        "elite": _solution(elite),
        "elite_gw1_mechanics": mechanics["unrestricted"],
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
        "epsilon_convergence": convergence,
        "canonical_recommendation": convergence["fallback"],
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
            "gw1_mechanics": mechanics[name],
            "raw_ev_floor": floors[name],
            "raw_ev_regret": regret,
            "raw_ev_regret_pct": regret_pct,
        }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "elite_latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    sensitivity_lines = [
        "| epsilon | raw xP | regret | overlap vs max-EV | captain |",
        "|---:|---:|---:|---:|:---|",
    ]
    for row in epsilon_rows:
        sensitivity_lines.append(
            f"| {row['epsilon']:.2%} | {row['raw_ev_objective']:.3f} | {row['raw_ev_regret_pct']:.2%} | "
            f"{row['squad_overlap_vs_max_ev']}/15 | {row['captain'] or ''} |"
        )
    lines = [
        "# Apex Elite diagnostic — xP-first lexicographic",
        "",
        "This file is diagnostic evidence. It is not the user-facing Apex recommendation.",
        "",
        f"Generated: {payload['generated_at']}",
        f"Epsilon frontier convergence: **{'PASS' if convergence['converged'] else 'FAIL'}**",
        f"Selector outcome: **{convergence['fallback']}**",
        "",
        "## Epsilon sensitivity",
        "",
        *sensitivity_lines,
    ]
    md_path = output_dir / "elite_latest.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
