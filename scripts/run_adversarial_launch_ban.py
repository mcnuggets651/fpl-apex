#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.services.cached_launch import load_cached_hardened_launch
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path

CONTRACT = "apex-adversarial-launch-ban-v2"
DEFAULT_TARGETS = "Neave,Coyle,Guéhi,Wieffer,Thiaw,Hughes,Thiago,Gabriel,Schade,Raya"
TRANSFER_CANDIDATE_LIMIT = 180


def _resolve_targets(players: pd.DataFrame, names: list[str]) -> tuple[dict[str, int], list[dict]]:
    mapping: dict[str, int] = {}
    unresolved: list[dict] = []
    for name in names:
        matches = players[players["web_name"].astype(str).str.casefold().eq(name.strip().casefold())]
        if len(matches) == 1:
            mapping[name] = int(matches.iloc[0]["player_id"])
        else:
            unresolved.append({
                "target": name,
                "player_id": None,
                "status": "target_not_uniquely_resolved",
                "candidate_pool_stable": False,
                "certified": False,
                "gw1_delta_vs_baseline": None,
                "future_delta_vs_baseline": None,
                "bank_delta_vs_baseline": None,
                "captain": None,
                "vice_captain": None,
                "first_outfield_bench": None,
                "playable_outfield_bench": None,
                "outfield_bench_order": [],
                "removed_players": [],
                "added_players": [],
                "selected_squad": [],
                "reality_interpretation": "target_resolution_diagnostic",
                "note": f"target resolved to {len(matches)} official players; recorded without aborting the audit",
            })
    return mapping, unresolved


def _eligible_surface(bundle: DecisionBundle):
    out = bundle.to_pipeline_output()
    players, _ = evidence_eligibility(out.players, out.news_audit)
    return out, players, captain_eligible_ids(players), set(players.loc[players["xi_evidence_eligible"], "player_id"].astype(int))


def _run(bundle: DecisionBundle, banned_ids: set[int]):
    out, players, _, _ = _eligible_surface(bundle)
    players = players[~players["player_id"].astype(int).isin(banned_ids)].copy()
    projections = out.projections[~out.projections["player_id"].astype(int).isin(banned_ids)].copy()
    captain_eligible = captain_eligible_ids(players)
    xi_eligible = set(players.loc[players["xi_evidence_eligible"], "player_id"].astype(int))
    settings = bundle.settings
    result = optimise_with_bounded_stability_retry(
        optimise_joint_initial_path,
        players,
        projections,
        out.gameweeks,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=float(settings["fixture_decay"]),
        projection_col="xp",
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        transfer_candidate_limit=TRANSFER_CANDIDATE_LIMIT,
        exact_candidate_limit=int(settings.get("exact_candidate_limit", 16)),
        gw1_regret_tolerance=float(settings.get("exact_near_equivalent_points", 0.25)),
    )
    return result, players, projections, captain_eligible, xi_eligible, out.gameweeks


def _names(players: pd.DataFrame, ids) -> list[str]:
    if not ids:
        return []
    lookup = players.set_index("player_id")["web_name"].astype(str).to_dict()
    return [lookup.get(int(pid), str(pid)) for pid in ids]


def _submission_metrics(players, projections, gameweeks, result, captain_eligible, xi_eligible) -> dict:
    selected = result.selected
    if selected is None:
        return {"captain": None, "vice_captain": None, "submitted_xi": [], "outfield_bench_order": [], "first_outfield_bench": None, "playable_outfield_bench": 0}
    squad_ids = tuple(int(pid) for pid in selected.squad_ids)
    squad = players[players["player_id"].astype(int).isin(squad_ids)].copy()
    gw = int(gameweeks[0])
    xp_series = projections[projections["gw"].astype(int).eq(gw)].groupby("player_id")["xp"].sum()
    xp = {int(pid): float(value) for pid, value in xp_series.items()}
    appearances = pd.to_numeric(players.get("appearance_probability", pd.Series(1.0, index=players.index)), errors="coerce").fillna(1.0)
    appearance = {int(pid): min(max(float(prob), 0.0), 1.0) for pid, prob in zip(players["player_id"].astype(int), appearances)}
    xi, mechanics = optimise_fixed_squad_gameweek(squad, xp, appearance, captain_eligible=captain_eligible, xi_eligible=xi_eligible)
    names = players.set_index("player_id")["web_name"].astype(str).to_dict()
    expected_minutes = pd.to_numeric(players.get("expected_minutes", pd.Series(0.0, index=players.index)), errors="coerce").fillna(0.0)
    minutes = {int(pid): max(float(value), 0.0) for pid, value in zip(players["player_id"].astype(int), expected_minutes)}
    bench_order = tuple(int(pid) for pid in mechanics.outfield_bench_order)
    playable = sum(1 for pid in bench_order if appearance.get(pid, 0.0) >= 0.60 or minutes.get(pid, 0.0) >= 20.0)
    xi_ids = tuple(int(pid) for pid in xi["player_id"])
    return {
        "captain": names.get(int(mechanics.captain_id), str(mechanics.captain_id)),
        "vice_captain": names.get(int(mechanics.vice_captain_id), str(mechanics.vice_captain_id)),
        "submitted_xi": [names.get(pid, str(pid)) for pid in xi_ids],
        "outfield_bench_order": [names.get(pid, str(pid)) for pid in bench_order],
        "first_outfield_bench": names.get(bench_order[0], str(bench_order[0])) if bench_order else None,
        "playable_outfield_bench": int(playable),
    }


def _interpretation(*, certified: bool, gw1_delta, future_delta) -> str:
    if not certified:
        return "broader_candidate_instability_or_no_certified_solution"
    if gw1_delta is None or future_delta is None:
        return "insufficient_comparable_objective_surface"
    if gw1_delta > 0 and future_delta > 0:
        return "search_surface_defect_signal"
    if gw1_delta < 0 and future_delta < 0:
        return "genuine_value_support"
    if abs(gw1_delta) < 1e-9 and abs(future_delta) < 1e-9:
        return "objective_neutral"
    return "mixed_launch_vs_future_tradeoff"


def _failure_row(name: str, pid: int, exc: Exception) -> dict:
    return {
        "target": name, "player_id": pid, "status": "ban_solve_error", "candidate_pool_stable": False,
        "certified": False, "gw1_delta_vs_baseline": None, "future_delta_vs_baseline": None,
        "bank_delta_vs_baseline": None, "captain": None, "vice_captain": None,
        "first_outfield_bench": None, "playable_outfield_bench": None, "outfield_bench_order": [],
        "removed_players": [], "added_players": [], "selected_squad": [],
        "reality_interpretation": "broader_candidate_instability_or_no_certified_solution",
        "note": f"{type(exc).__name__}: {exc}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--canonical", default="data/generated/apex_recommendation_latest.json")
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--output", default="reports/adversarial_launch_bans.json")
    parser.add_argument("--csv", default="reports/adversarial_launch_bans.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out, baseline_players, baseline_captain_eligible, baseline_xi_eligible = _eligible_surface(bundle)
    target_names = [row.strip() for row in args.targets.split(",") if row.strip()]
    targets, unresolved_rows = _resolve_targets(out.players, target_names)

    baseline = load_cached_hardened_launch(args.canonical, decision_bundle_id=bundle.bundle_id)
    baseline_source = "canonical_hardened_launch_cache"
    if baseline is None:
        baseline, baseline_players, baseline_projections, baseline_captain_eligible, baseline_xi_eligible, baseline_gameweeks = _run(bundle, set())
        baseline_source = "fresh_hardened_launch_solve"
    else:
        baseline_projections = out.projections
        baseline_gameweeks = out.gameweeks
    if not (baseline.status == "optimal" and baseline.selected is not None and baseline.selected.within_gw1_band and baseline.candidate_pool_stable):
        raise SystemExit("baseline launch is not certified; adversarial ban audit cannot compare")

    baseline_ids = tuple(int(pid) for pid in baseline.selected.squad_ids)
    baseline_id_set = set(baseline_ids)
    baseline_submission = _submission_metrics(baseline_players, baseline_projections, baseline_gameweeks, baseline, baseline_captain_eligible, baseline_xi_eligible)
    rows: list[dict] = list(unresolved_rows)

    for name, pid in targets.items():
        # A ban on a player absent from the certified launch cannot alter that launch.
        # Record the fact instead of spending another expensive horizon solve.
        if pid not in baseline_id_set:
            rows.append({
                "target": name, "player_id": pid, "status": "not_in_baseline_launch", "candidate_pool_stable": True,
                "certified": True, "gw1_delta_vs_baseline": 0.0, "future_delta_vs_baseline": 0.0,
                "bank_delta_vs_baseline": 0.0, "captain": baseline_submission["captain"],
                "vice_captain": baseline_submission["vice_captain"], "first_outfield_bench": baseline_submission["first_outfield_bench"],
                "playable_outfield_bench": baseline_submission["playable_outfield_bench"], "outfield_bench_order": baseline_submission["outfield_bench_order"],
                "removed_players": [], "added_players": [], "selected_squad": _names(out.players, baseline_ids),
                "reality_interpretation": "objective_neutral", "note": "target absent from certified baseline; ban is launch-neutral by construction",
            })
            continue
        try:
            result, players, projections, captain_eligible, xi_eligible, gameweeks = _run(bundle, {pid})
            selected = result.selected
            ids = tuple(int(value) for value in selected.squad_ids) if selected else tuple()
            certified = bool(result.status == "optimal" and selected is not None and selected.within_gw1_band and result.candidate_pool_stable)
            gw1_delta = float(selected.gw1_expected_points - baseline.selected.gw1_expected_points) if selected else None
            future_delta = float(selected.future_objective - baseline.selected.future_objective) if selected else None
            submission = _submission_metrics(players, projections, gameweeks, result, captain_eligible, xi_eligible)
            rows.append({
                "target": name, "player_id": pid, "status": result.status, "candidate_pool_stable": bool(result.candidate_pool_stable),
                "certified": certified, "gw1_delta_vs_baseline": gw1_delta, "future_delta_vs_baseline": future_delta,
                "bank_delta_vs_baseline": float(selected.starting_bank - baseline.selected.starting_bank) if selected else None,
                "captain": submission["captain"], "vice_captain": submission["vice_captain"],
                "first_outfield_bench": submission["first_outfield_bench"], "playable_outfield_bench": submission["playable_outfield_bench"],
                "outfield_bench_order": submission["outfield_bench_order"],
                "removed_players": _names(out.players, tuple(sorted(baseline_id_set - set(ids)))),
                "added_players": _names(out.players, tuple(sorted(set(ids) - baseline_id_set))),
                "selected_squad": _names(out.players, ids),
                "reality_interpretation": _interpretation(certified=certified, gw1_delta=gw1_delta, future_delta=future_delta),
                "note": result.note,
            })
        except Exception as exc:
            # One deliberately hostile perturbation must not destroy evidence from all
            # other bans. It remains explicitly uncertified and visible in the report.
            rows.append(_failure_row(name, pid, exc))

    defect_signals = [row["target"] for row in rows if row.get("reality_interpretation") == "search_surface_defect_signal"]
    solve_errors = [row["target"] for row in rows if row.get("status") == "ban_solve_error"]
    payload = {
        "contract": CONTRACT,
        "decision_bundle_id": bundle.bundle_id,
        "baseline_source": baseline_source,
        "baseline": {"gw1_expected_points": baseline.selected.gw1_expected_points, "future_objective": baseline.selected.future_objective, "starting_bank": baseline.selected.starting_bank, "squad": _names(out.players, baseline_ids), **baseline_submission},
        "targets": rows,
        "summary": {"target_count": len(rows), "search_surface_defect_signals": defect_signals, "ban_solve_errors": solve_errors, "audit_complete": len(rows) == len(target_names)},
        "interpretation_policy": {
            "search_surface_defect_signal": "certified ban improves both GW1 and future objective",
            "genuine_value_support": "certified ban worsens both GW1 and future objective",
            "mixed_launch_vs_future_tradeoff": "certified ban moves GW1 and future objectives in opposite directions",
            "broader_candidate_instability_or_no_certified_solution": "ban result is not stable/certified and must not be promoted",
            "objective_neutral": "ban cannot improve the certified launch on the evaluated surface",
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
