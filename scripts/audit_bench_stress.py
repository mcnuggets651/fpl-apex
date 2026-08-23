#!/usr/bin/env python3
from __future__ import annotations

import argparse
from itertools import combinations
import json
from pathlib import Path
from typing import Any

import pandas as pd

from apex_fpl.optimisation.mechanics import autosub_weights_ids
from apex_fpl.services.decision_bundle import DecisionBundle


CONTRACT = "apex-bench-stress-v2"


def _load(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _ids(rows: list[dict] | None) -> tuple[int, ...]:
    return tuple(
        int(row["player_id"])
        for row in (rows or [])
        if isinstance(row, dict) and row.get("player_id") is not None
    )


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


def audit_canonical_bench_stress(
    *,
    bundle: DecisionBundle,
    canonical: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    if canonical.get("decision_bundle_id") != bundle.bundle_id:
        raise ValueError("bench stress canonical payload does not match the DecisionBundle")
    recommendation = canonical.get("recommendation") or {}
    squad_ids = _ids(recommendation.get("squad"))
    xi_ids = _ids(recommendation.get("xi"))
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        raise ValueError("bench stress requires the exact canonical 15")
    if len(xi_ids) != 11 or len(set(xi_ids)) != 11 or not set(xi_ids).issubset(squad_ids):
        raise ValueError("bench stress requires the exact canonical XI")

    captain_id = int(recommendation.get("captain_id") or 0)
    vice_id = int(recommendation.get("vice_captain_id") or 0)
    bench_gk_id = int(recommendation.get("bench_gk_id") or 0)
    bench_order = tuple(int(pid) for pid in recommendation.get("outfield_bench_order_ids") or [])
    bench_ids = set(squad_ids) - set(xi_ids)
    if (
        captain_id not in xi_ids
        or vice_id not in xi_ids
        or captain_id == vice_id
        or len(bench_order) != 3
        or len(set(bench_order)) != 3
        or {bench_gk_id, *bench_order} != bench_ids
    ):
        raise ValueError("bench stress canonical mechanics do not reconcile to the submitted 15/XI")

    out = bundle.to_pipeline_output()
    gw = int(recommendation.get("current_gameweek") or (out.gameweeks[0] if out.gameweeks else 0))
    if not out.gameweeks or gw != int(out.gameweeks[0]):
        raise ValueError("bench stress gameweek does not match the sealed actionable horizon")
    players = out.players.drop_duplicates("player_id").copy()
    selected = players[players["player_id"].astype(int).isin(set(squad_ids))].copy()
    if len(selected) != 15:
        raise ValueError("bench stress canonical identities are missing from sealed players")

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
    positions = {
        int(row.player_id): str(row.position)
        for row in selected[["player_id", "position"]].itertuples(index=False)
    }
    names = selected.set_index("player_id")["web_name"].astype(str).to_dict()
    baseline = _fixed_total(
        squad_ids=squad_ids,
        xi_ids=xi_ids,
        positions=positions,
        xp=xp,
        appearance=appearance,
        captain_id=captain_id,
        vice_id=vice_id,
        bench_order=bench_order,
        absent=set(),
    )

    rows: list[dict[str, Any]] = []
    for size in (1, 2):
        for combo in combinations(xi_ids, size):
            total = _fixed_total(
                squad_ids=squad_ids,
                xi_ids=xi_ids,
                positions=positions,
                xp=xp,
                appearance=appearance,
                captain_id=captain_id,
                vice_id=vice_id,
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
        "selector": recommendation.get("selector"),
        "canonical_submission_source": "apex_recommendation_latest",
        "gameweek": gw,
        "submitted_squad_ids": list(squad_ids),
        "submitted_xi_ids": list(xi_ids),
        "captain_id": captain_id,
        "vice_captain_id": vice_id,
        "bench_gk_id": bench_gk_id,
        "submitted_outfield_bench_order_ids": list(bench_order),
        "baseline_expected_total": baseline,
        "mean_one_absence_loss": float(one["loss_vs_submitted_baseline"].mean()),
        "mean_two_absence_loss": float(two["loss_vs_submitted_baseline"].mean()),
        "worst_two_absence_loss": float(worst.iloc[0]["loss_vs_submitted_baseline"]),
        "worst_two_absent_players": worst.iloc[0]["absent_players"],
        "fixed_submission": True,
        "bench_reordered_with_hindsight": False,
    }
    return payload, frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--canonical", default="data/generated/apex_recommendation_latest.json")
    parser.add_argument("--output", default="reports/bench_stress.json")
    parser.add_argument("--csv", default="reports/bench_stress.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    canonical = _load(args.canonical)
    payload, frame = audit_canonical_bench_stress(bundle=bundle, canonical=canonical)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    frame.to_csv(args.csv, index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
