#!/usr/bin/env python3
from __future__ import annotations

import argparse
from itertools import combinations
import json
from pathlib import Path

import pandas as pd

from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.optimisation.mechanics import autosub_weights_ids
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path


CONTRACT = "apex-bench-stress-v1"
TRANSFER_CANDIDATE_LIMIT = 180


def _launch(bundle: DecisionBundle):
    out = bundle.to_pipeline_output()
    players, _ = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(players)
    xi_eligible = set(players.loc[players["xi_evidence_eligible"], "player_id"].astype(int))
    settings = bundle.settings
    result = optimise_with_bounded_stability_retry(
        optimise_joint_initial_path,
        players,
        out.projections,
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
    if not (
        result.status == "optimal"
        and result.selected is not None
        and result.selected.within_gw1_band
        and result.candidate_pool_stable
    ):
        raise SystemExit("hardened launch is not certified; bench stress cannot run")
    return out, players, result, captain_eligible, xi_eligible


def _fixed_total(
    *,
    squad_ids: tuple[int, ...],
    xi_ids: tuple[int, ...],
    positions: dict[int, str],
    xp: dict[int, float],
    appearance: dict[int, float],
    captain_id: int,
    vice_id: int,
    bench_order: tuple[int, ...],
    absent: set[int],
) -> float:
    scenario_appearance = dict(appearance)
    scenario_xp = dict(xp)
    for pid in absent:
        scenario_appearance[int(pid)] = 0.0
        scenario_xp[int(pid)] = 0.0

    bench_ids = tuple(sorted(set(squad_ids) - set(xi_ids)))
    weights = autosub_weights_ids(
        xi_ids,
        bench_ids,
        positions,
        scenario_appearance,
        outfield_order=bench_order,
    )
    xi_points = sum(max(float(scenario_xp.get(pid, 0.0)), 0.0) for pid in xi_ids)
    autosub = sum(
        float(weight) * max(float(scenario_xp.get(pid, 0.0)), 0.0)
        for pid, weight in weights.items()
    )
    p_c = min(max(float(scenario_appearance.get(captain_id, 1.0)), 0.0), 1.0)
    captain_bonus = max(float(scenario_xp.get(captain_id, 0.0)), 0.0) + (
        (1.0 - p_c) * max(float(scenario_xp.get(vice_id, 0.0)), 0.0)
    )
    return float(xi_points + autosub + captain_bonus)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output", default="reports/bench_stress.json")
    parser.add_argument("--csv", default="reports/bench_stress.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out, players, result, captain_eligible, xi_eligible = _launch(bundle)
    selected = result.selected
    assert selected is not None
    squad_ids = tuple(sorted(int(pid) for pid in selected.squad_ids))
    squad = players[players["player_id"].astype(int).isin(squad_ids)].copy()
    gw = int(out.gameweeks[0])
    xp_series = (
        out.projections[out.projections["gw"].astype(int).eq(gw)]
        .groupby("player_id")["xp"]
        .sum()
    )
    xp = {int(pid): float(value) for pid, value in xp_series.items()}
    appearances = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    appearance = {
        int(pid): min(max(float(prob), 0.0), 1.0)
        for pid, prob in zip(players["player_id"].astype(int), appearances)
    }
    xi, mechanics = optimise_fixed_squad_gameweek(
        squad,
        xp,
        appearance,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    xi_ids = tuple(sorted(int(pid) for pid in xi["player_id"]))
    positions = {
        int(row.player_id): str(row.position)
        for row in squad[["player_id", "position"]].itertuples(index=False)
    }
    bench_order = tuple(int(pid) for pid in mechanics.outfield_bench_order)
    baseline = _fixed_total(
        squad_ids=squad_ids,
        xi_ids=xi_ids,
        positions=positions,
        xp=xp,
        appearance=appearance,
        captain_id=int(mechanics.captain_id),
        vice_id=int(mechanics.vice_captain_id),
        bench_order=bench_order,
        absent=set(),
    )
    names = players.set_index("player_id")["web_name"].astype(str).to_dict()

    rows: list[dict] = []
    for size in (1, 2):
        for combo in combinations(xi_ids, size):
            total = _fixed_total(
                squad_ids=squad_ids,
                xi_ids=xi_ids,
                positions=positions,
                xp=xp,
                appearance=appearance,
                captain_id=int(mechanics.captain_id),
                vice_id=int(mechanics.vice_captain_id),
                bench_order=bench_order,
                absent=set(combo),
            )
            rows.append(
                {
                    "absence_count": size,
                    "absent_ids": list(combo),
                    "absent_players": [names.get(pid, str(pid)) for pid in combo],
                    "expected_total": total,
                    "loss_vs_submitted_baseline": baseline - total,
                }
            )

    frame = pd.DataFrame(rows)
    one = frame[frame["absence_count"].eq(1)]
    two = frame[frame["absence_count"].eq(2)]
    worst = two.sort_values("loss_vs_submitted_baseline", ascending=False).head(1)
    payload = {
        "contract": CONTRACT,
        "decision_bundle_id": bundle.bundle_id,
        "gameweek": gw,
        "submitted_xi": [names.get(pid, str(pid)) for pid in xi_ids],
        "captain": names.get(int(mechanics.captain_id), str(mechanics.captain_id)),
        "vice_captain": names.get(int(mechanics.vice_captain_id), str(mechanics.vice_captain_id)),
        "submitted_outfield_bench_order": [names.get(pid, str(pid)) for pid in bench_order],
        "baseline_expected_total": baseline,
        "mean_one_absence_loss": float(one["loss_vs_submitted_baseline"].mean()),
        "mean_two_absence_loss": float(two["loss_vs_submitted_baseline"].mean()),
        "worst_two_absence_loss": float(worst.iloc[0]["loss_vs_submitted_baseline"]),
        "worst_two_absent_players": worst.iloc[0]["absent_players"],
        "fixed_submission": True,
        "bench_reordered_with_hindsight": False,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    frame.to_csv(args.csv, index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
