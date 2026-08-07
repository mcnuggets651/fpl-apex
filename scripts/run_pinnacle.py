#!/usr/bin/env python3
"""Generate the final Apex Pinnacle decision snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.scenarios import generate_projection_scenarios
from apex_fpl.optimisation.cvar import optimise_initial_cvar
from apex_fpl.optimisation.frequencies import estimate_decision_frequencies
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics
from apex_fpl.optimisation.stability import selection_regret_analysis
from apex_fpl.services.chips import evaluate_chip_window
from apex_fpl.services.initial_plan import (
    build_initial_squad_contingencies,
    initial_chip_policy,
)
from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload
from apex_fpl.services.pipeline import run_pipeline
from apex_fpl.services.strategy import analyse_receding_horizon


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _solution(sol) -> dict:
    return {
        "status": sol.status,
        "objective": sol.objective,
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "vice_captain": _records(sol.vice_captain),
        "bench": _records(sol.bench),
    }


def _robust_solution(sol) -> dict:
    score = sol.scenario_scores
    return {
        "status": sol.status,
        "objective": sol.objective,
        "mean_points": sol.mean_points,
        "lower_tail_cvar": sol.lower_tail_cvar,
        "cvar_alpha": sol.cvar_alpha,
        "cvar_weight": sol.cvar_weight,
        "scenario_p10": float(np.quantile(score, 0.10)) if len(score) else None,
        "scenario_p50": float(np.quantile(score, 0.50)) if len(score) else None,
        "scenario_p90": float(np.quantile(score, 0.90)) if len(score) else None,
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "vice_captain": _records(sol.vice_captain),
        "bench": _records(sol.bench),
    }


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty or "player_id" not in frame.columns:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _comparison(left, right) -> dict:
    left_squad, right_squad = _ids(left.squad), _ids(right.squad)
    left_xi, right_xi = _ids(left.xi), _ids(right.xi)
    left_cap, right_cap = _ids(left.captain), _ids(right.captain)
    return {
        "squad_overlap": len(left_squad & right_squad),
        "squad_changed": sorted(left_squad ^ right_squad),
        "xi_overlap": len(left_xi & right_xi),
        "captain_agrees": bool(left_cap and left_cap == right_cap),
        "left_objective": float(left.objective),
        "right_objective": float(right.objective),
    }


def _scenario_player_summary(players, scenario_surface, decay: float) -> pd.DataFrame:
    discounts = np.asarray(
        [float(decay) ** t for t in range(len(scenario_surface.gameweeks))],
        dtype=float,
    )
    horizon = np.sum(scenario_surface.values * discounts[None, None, :], axis=2)
    summary = pd.DataFrame(
        {
            "player_id": scenario_surface.player_ids.astype(int),
            "scenario_horizon_mean": np.mean(horizon, axis=0),
            "scenario_horizon_sd": np.std(horizon, axis=0, ddof=0),
            "scenario_horizon_p10": np.quantile(horizon, 0.10, axis=0),
            "scenario_horizon_p50": np.quantile(horizon, 0.50, axis=0),
            "scenario_horizon_p90": np.quantile(horizon, 0.90, axis=0),
        }
    )
    keep = [
        col
        for col in ["player_id", "web_name", "team_name", "position", "price"]
        if col in players.columns
    ]
    return summary.merge(players[keep], on="player_id", how="left").sort_values(
        "scenario_horizon_mean", ascending=False
    )


def _xp_map(
    projections: pd.DataFrame,
    gw: int,
    projection_col: str = "xp",
) -> dict[int, float]:
    d = projections[projections["gw"] == int(gw)]
    if d.empty:
        return {}
    col = projection_col if projection_col in d.columns else "risk_adjusted_xp"
    if col not in d.columns:
        raise ValueError(f"projection table lacks {projection_col!r} and risk_adjusted_xp")
    grouped = d.groupby("player_id")[col].sum()
    return {int(pid): float(value) for pid, value in grouped.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    probs = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): float(prob)
        for pid, prob in zip(players["player_id"].astype(int), probs)
    }


def _mechanics_payload(
    sol,
    xp: dict[int, float],
    appearance: dict[int, float],
    players: pd.DataFrame,
) -> dict:
    mechanics = optimise_gameweek_mechanics(sol.squad, sol.xi, xp, appearance)
    result = mechanics.to_dict()
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    result["captain_name"] = names.get(mechanics.captain_id, str(mechanics.captain_id))
    result["vice_captain_name"] = names.get(
        mechanics.vice_captain_id, str(mechanics.vice_captain_id)
    )
    result["bench_gk_name"] = names.get(mechanics.bench_gk_id, str(mechanics.bench_gk_id))
    result["outfield_bench_order_names"] = [
        names.get(pid, str(pid)) for pid in mechanics.outfield_bench_order
    ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--alternatives", type=int, default=12)
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--scenario-seed", type=int, default=20260807)
    parser.add_argument("--cvar-alpha", type=float, default=0.10)
    parser.add_argument("--cvar-weight", type=float, default=0.20)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=True,
    )
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        blockers = "; ".join(out.safety.blockers) or "unknown production blocker"
        raise SystemExit(f"Pinnacle runner blocked by Apex production gate: {blockers}")

    gws = out.gameweeks
    projections = out.projections
    if not gws:
        raise SystemExit("Pinnacle runner has no actionable future Gameweeks")

    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    team_ids = official.players[["player_id", "team"]].drop_duplicates("player_id")
    decision_players = out.players.drop(columns=["team"], errors="ignore").merge(
        team_ids, on="player_id", how="left", validate="one_to_one"
    )
    if decision_players["team"].isna().any():
        raise SystemExit("Pinnacle player universe contains missing official team IDs")

    common = dict(
        players=decision_players,
        projections=projections,
        gameweeks=gws,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        projection_col="xp",
    )
    deterministic = {"unrestricted": optimise_initial_horizon(**common)}
    haaland = decision_players[
        decision_players["web_name"].astype(str).str.casefold().eq("haaland")
    ]
    haaland_id = int(haaland.iloc[0]["player_id"]) if not haaland.empty else None
    if haaland_id is not None:
        deterministic["haaland"] = optimise_initial_horizon(
            **common, locked={haaland_id}
        )
        deterministic["no-haaland"] = optimise_initial_horizon(
            **common, banned={haaland_id}
        )
    bad = [name for name, sol in deterministic.items() if sol.status != "Optimal"]
    if bad:
        raise SystemExit("Pinnacle EV optimiser failed: " + ", ".join(bad))

    scenario_surface = generate_projection_scenarios(
        decision_players,
        projections,
        gws,
        n_scenarios=args.stochastic_scenarios,
        seed=args.scenario_seed,
    )
    robust_common = dict(
        players=decision_players,
        scenarios=scenario_surface,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        cvar_alpha=args.cvar_alpha,
        cvar_weight=args.cvar_weight,
    )
    robust = {"unrestricted": optimise_initial_cvar(**robust_common)}
    if haaland_id is not None:
        robust["haaland"] = optimise_initial_cvar(
            **robust_common, locked={haaland_id}
        )
        robust["no-haaland"] = optimise_initial_cvar(
            **robust_common, banned={haaland_id}
        )
    bad_robust = [name for name, sol in robust.items() if sol.status != "Optimal"]
    if bad_robust:
        raise SystemExit("Pinnacle CVaR optimiser failed: " + ", ".join(bad_robust))

    regret = selection_regret_analysis(
        decision_players,
        projections,
        gws,
        deterministic["unrestricted"],
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        alternative_limit=args.alternatives,
    )
    legacy_compare = {
        name: _comparison(out.scenarios[name], sol)
        for name, sol in deterministic.items()
        if name in out.scenarios
    }
    robust_compare = {
        name: _comparison(deterministic[name], sol)
        for name, sol in robust.items()
        if name in deterministic
    }

    frequencies = estimate_decision_frequencies(
        decision_players,
        scenario_surface,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        max_solves=24,
    )
    if frequencies.completed_solves < 16:
        raise SystemExit(
            "Pinnacle decision-frequency audit completed fewer than 16 optimal solves: "
            f"{frequencies.completed_solves}/{frequencies.requested_solves}"
        )

    report_dir = Path(args.report_dir)
    output_dir = Path(args.output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    regret.to_csv(report_dir / "pinnacle_selection_regret.csv", index=False)
    scenario_summary = _scenario_player_summary(
        decision_players, scenario_surface, settings.fixture_decay
    )
    scenario_summary.to_csv(
        report_dir / "pinnacle_scenario_player_summary.csv", index=False
    )
    frequencies.rows.to_csv(
        report_dir / "pinnacle_decision_frequencies.csv", index=False
    )

    # The final deadline mechanics use the same raw ensemble mean xP as the
    # deterministic maximum-EV optimiser. Risk is assessed separately by CVaR.
    central_xp = _xp_map(projections, gws[0], "xp")
    appearance = _appearance_map(decision_players)
    gw1_mechanics = {
        name: _mechanics_payload(sol, central_xp, appearance, decision_players)
        for name, sol in deterministic.items()
    }
    robust_gw1_values = np.mean(scenario_surface.values[:, :, 0], axis=0)
    robust_xp = {
        int(pid): float(value)
        for pid, value in zip(scenario_surface.player_ids, robust_gw1_values)
    }
    robust_gw1_mechanics = {
        name: _mechanics_payload(sol, robust_xp, appearance, decision_players)
        for name, sol in robust.items()
    }

    personal_team = _load_json(report_dir / "team_state.json")
    weekly_strategy = None
    chip_window = None
    initial_contingencies = None
    team_state = out.team_state.state if out.team_state is not None else None
    if team_state is not None:
        weekly_strategy = analyse_receding_horizon(
            decision_players,
            projections,
            gws,
            team_state,
            out.transfer_plan,
            max_per_team=settings.max_per_team,
            decay=settings.fixture_decay,
            projection_col="xp",
        ).to_dict()
        chip_window = evaluate_chip_window(
            decision_players,
            projections,
            gws,
            team_state,
            out.transfer_plan,
            max_per_team=settings.max_per_team,
            decay=settings.fixture_decay,
            projection_col="xp",
        ).to_dict()
    elif gws[0] == 1:
        initial_contingencies = build_initial_squad_contingencies(
            deterministic["unrestricted"],
            decision_players,
            projections,
            gws,
            budget=settings.budget,
            max_per_team=settings.max_per_team,
            decay=settings.fixture_decay,
        )

    chip_policy = initial_chip_policy(gws)

    production_report = _load_json(report_dir / "latest.json") or {}
    solver_parity = _load_json(output_dir / "solver_parity.json")
    payload = {
        "contract": "apex-pinnacle-v3-final",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fpl_entry_id": settings.fpl_entry_id,
        "gameweeks": gws,
        "safe_to_act": True,
        "full_apex_ready": True,
        "decision_layer": {
            "deterministic_initial_squad": "full-horizon maximum-EV MILP with per-GW XI/captain",
            "deterministic_projection_surface": "ensemble mean xp",
            "stochastic_covariance_layer": True,
            "stochastic_model": scenario_surface.model_version,
            "stochastic_scenarios": scenario_surface.n_scenarios,
            "scenario_seed": scenario_surface.seed,
            "cvar_alpha": args.cvar_alpha,
            "cvar_weight": args.cvar_weight,
            "covariance_coefficients_walk_forward_calibrated": False,
            "sensitivity": "exact force/ban objective regret",
            "empirical_decision_frequency": True,
            "decision_frequency_solves": frequencies.completed_solves,
            "exact_gw_mechanics": True,
            "captain_vice_rule": "expected no-show fallback value",
            "provisional_captain_safety_floor": {
                "expected_minutes": 60,
                "start_probability": 0.50,
                "appearance_probability": 0.75,
                "projection_confidence": 0.40,
            },
            "autosub_rule": "exact appearance-state enumeration with legal FPL formation",
            "receding_horizon_transfers": True,
            "weekly_transfer_projection_surface": "ensemble mean xp",
            "chip_rules": "2026/27 two chip sets; one of each chip per half; max one active chip per GW",
            "chip_policy": "hold unless calibrated remaining-half opportunity cost is beaten",
            "decision_rule": (
                "maximise expected points first; use CVaR, exact mechanics, selection "
                "regret and independent solver evidence to expose fragility"
            ),
        },
        "official_snapshot": out.snapshot,
        "upstreams": production_report.get("upstreams", {}),
        "sources": [s.to_dict() for s in out.sources],
        "data_quality": out.data_quality.to_dict(),
        "personal_team": personal_team,
        "deterministic_scenarios": {
            name: _solution(sol) for name, sol in deterministic.items()
        },
        "robust_cvar_scenarios": {
            name: _robust_solution(sol) for name, sol in robust.items()
        },
        "legacy_comparison": legacy_compare,
        "robustness_comparison": robust_compare,
        "gw1_mechanics": gw1_mechanics,
        "robust_gw1_mechanics": robust_gw1_mechanics,
        "selection_regret": _records(regret),
        "decision_frequencies": _records(frequencies.rows),
        "scenario_player_summary": _records(scenario_summary.head(150)),
        "transfer_plan": (
            {
                "status": out.transfer_plan.status,
                "objective": out.transfer_plan.objective,
                "weeks": out.transfer_plan.weeks,
                "surface": "legacy risk_adjusted_xp",
            }
            if out.transfer_plan is not None
            else None
        ),
        "weekly_strategy": weekly_strategy,
        "chip_window": chip_window,
        "initial_squad_contingencies": initial_contingencies,
        "initial_chip_policy": chip_policy,
        "solver_parity": solver_parity,
    }

    readiness = evaluate_pinnacle_payload(payload)
    payload["pinnacle_ready"] = readiness.ready
    payload["pinnacle_gate"] = readiness.to_dict()

    output_json = output_dir / "pinnacle_latest.json"
    output_md = output_dir / "pinnacle_latest.md"
    output_json.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    lines = [
        "# Apex Pinnacle decision",
        "",
        f"Generated: {payload['generated_at']}",
        f"Gameweeks: {', '.join(map(str, gws))}",
        "",
        "## Pinnacle gate",
        "",
        f"- pinnacle_ready: `{str(readiness.ready).lower()}`",
        "- base safe_to_act: `true`",
        "- base full_apex_ready: `true`",
        "- deterministic surface: ensemble mean xP",
        f"- covariance-aware scenarios: {scenario_surface.n_scenarios}",
        f"- lower-tail CVaR alpha: {args.cvar_alpha:.0%}",
        f"- CVaR objective weight: {args.cvar_weight:.0%}",
        "- exact captain/vice fallback: `true`",
        "- exact autosub expectation: `true`",
        "- receding-horizon transfer policy: `true`",
        "",
    ]
    for warning in readiness.warnings:
        lines.append(f"- WARNING: {warning}")
    for blocker in readiness.blockers:
        lines.append(f"- BLOCKER: {blocker}")
    lines.append("")

    for name, sol in deterministic.items():
        mechanics = gw1_mechanics[name]
        lines += [
            f"## Maximum-EV {name}",
            "",
            f"Objective: **{sol.objective:.2f}**",
            f"GW1 captain: **{mechanics['captain_name']}**",
            f"GW1 vice-captain: **{mechanics['vice_captain_name']}**",
            "GW1 bench order: **"
            + " → ".join(mechanics["outfield_bench_order_names"])
            + "** (outfield; GK separate)",
            f"GW1 exact-mechanics xP: **{mechanics['expected_total_points']:.2f}**",
            "",
            sol.squad.to_markdown(index=False),
            "",
        ]
    for name, sol in robust.items():
        lines += [
            f"## Robust CVaR {name}",
            "",
            f"Blended objective: **{sol.objective:.2f}**",
            f"Scenario mean: **{sol.mean_points:.2f}**",
            f"Lower-tail CVaR: **{sol.lower_tail_cvar:.2f}**",
            f"Maximum-EV/robust squad overlap: **{robust_compare[name]['squad_overlap']}/15**",
            "",
            sol.squad.to_markdown(index=False),
            "",
        ]
    if weekly_strategy:
        lines += [
            "## Weekly receding-horizon strategy",
            "",
            f"Action now: **{weekly_strategy['recommended_action']}**",
            f"Transfers now: **{weekly_strategy['recommended_transfers']}**",
            f"Hit now: **-{weekly_strategy['recommended_hit']}**",
            f"Value lost by forcing a roll: **{weekly_strategy['roll_regret']:.2f}**",
            "",
            "Future moves are contingencies and must be re-solved after the next deadline.",
            "",
        ]
    if initial_contingencies:
        lines += [
            "## GW1-GW5 contingency route",
            "",
            f"Starting bank: **{initial_contingencies.get('starting_bank', 0):.2f}**",
            "",
            initial_contingencies["execution_trigger"],
            "",
        ]
        for week in initial_contingencies.get("weeks", []):
            names_in = ", ".join(
                str(row.get("web_name", row.get("player_id")))
                for row in week.get("transfers_in", [])
            ) or "none"
            names_out = ", ".join(
                str(row.get("web_name", row.get("player_id")))
                for row in week.get("transfers_out", [])
            ) or "none"
            lines.append(
                f"- GW{week['gw']} contingency: {names_out} → {names_in}; "
                f"hit -{week.get('hit_cost', 0)}; bank {week.get('bank_after', 0):.2f}"
            )
        lines.append("")
    if chip_window:
        lines += [
            "## Chip window",
            "",
            f"Best immediate chip by current-window xP: **{chip_window['best_immediate_chip']}**",
            f"Recommended chip: **{chip_window['recommended_chip'] or 'hold'}**",
            chip_window["policy_reason"],
            "",
        ]
    elif chip_policy:
        lines += [
            "## Initial chip policy",
            "",
            "Recommended chip: **hold**",
            chip_policy["reason"],
            "",
        ]
    if not regret.empty:
        lines += ["## Selection-regret stress test", "", regret.to_markdown(index=False), ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")

    if not readiness.ready:
        raise SystemExit("PINNACLE GATE BLOCKED: " + "; ".join(readiness.blockers))
    print(f"PINNACLE GATE READY: snapshot written to {output_json}")


if __name__ == "__main__":
    main()
