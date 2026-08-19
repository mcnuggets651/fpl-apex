#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path


CONTRACT = "apex-adversarial-launch-ban-v1"
DEFAULT_TARGETS = "Neave,Coyle,Guéhi,Wieffer,Thiaw,Hughes,Thiago,Gabriel,Schade,Raya"
TRANSFER_CANDIDATE_LIMIT = 180


def _resolve_targets(players: pd.DataFrame, names: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for name in names:
        matches = players[
            players["web_name"].astype(str).str.casefold().eq(str(name).strip().casefold())
        ]
        if len(matches) != 1:
            raise SystemExit(f"ban target {name!r} does not uniquely resolve: {len(matches)} matches")
        mapping[name] = int(matches.iloc[0]["player_id"])
    return mapping


def _run(bundle: DecisionBundle, banned_ids: set[int]):
    out = bundle.to_pipeline_output()
    players, _ = evidence_eligibility(out.players, out.news_audit)
    players = players[~players["player_id"].astype(int).isin(banned_ids)].copy()
    projections = out.projections[
        ~out.projections["player_id"].astype(int).isin(banned_ids)
    ].copy()
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


def _names(players: pd.DataFrame, ids: tuple[int, ...] | None) -> list[str]:
    if not ids:
        return []
    lookup = players.set_index("player_id")["web_name"].astype(str).to_dict()
    return [lookup.get(int(pid), str(pid)) for pid in ids]


def _submission_metrics(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    result,
    captain_eligible: set[int],
    xi_eligible: set[int],
) -> dict:
    selected = result.selected
    if selected is None:
        return {
            "captain": None,
            "vice_captain": None,
            "submitted_xi": [],
            "outfield_bench_order": [],
            "first_outfield_bench": None,
            "playable_outfield_bench": 0,
        }
    squad_ids = tuple(int(pid) for pid in selected.squad_ids)
    squad = players[players["player_id"].astype(int).isin(squad_ids)].copy()
    gw = int(gameweeks[0])
    xp_series = (
        projections[projections["gw"].astype(int).eq(gw)]
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
    names = players.set_index("player_id")["web_name"].astype(str).to_dict()
    expected_minutes = pd.to_numeric(
        players.get("expected_minutes", pd.Series(0.0, index=players.index)),
        errors="coerce",
    ).fillna(0.0)
    minutes = {
        int(pid): max(float(value), 0.0)
        for pid, value in zip(players["player_id"].astype(int), expected_minutes)
    }
    bench_order = tuple(int(pid) for pid in mechanics.outfield_bench_order)
    playable = sum(
        1
        for pid in bench_order
        if appearance.get(pid, 0.0) >= 0.60 or minutes.get(pid, 0.0) >= 20.0
    )
    xi_ids = tuple(int(pid) for pid in xi["player_id"])
    return {
        "captain": names.get(int(mechanics.captain_id), str(mechanics.captain_id)),
        "vice_captain": names.get(
            int(mechanics.vice_captain_id), str(mechanics.vice_captain_id)
        ),
        "submitted_xi": [names.get(pid, str(pid)) for pid in xi_ids],
        "outfield_bench_order": [names.get(pid, str(pid)) for pid in bench_order],
        "first_outfield_bench": (
            names.get(bench_order[0], str(bench_order[0])) if bench_order else None
        ),
        "playable_outfield_bench": int(playable),
    }


def _interpretation(*, certified: bool, gw1_delta: float | None, future_delta: float | None) -> str:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--output", default="reports/adversarial_launch_bans.json")
    parser.add_argument("--csv", default="reports/adversarial_launch_bans.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    target_names = [row.strip() for row in args.targets.split(",") if row.strip()]
    targets = _resolve_targets(out.players, target_names)

    (
        baseline,
        baseline_players,
        baseline_projections,
        baseline_captain_eligible,
        baseline_xi_eligible,
        baseline_gameweeks,
    ) = _run(bundle, set())
    if not (
        baseline.status == "optimal"
        and baseline.selected is not None
        and baseline.candidate_pool_stable
    ):
        raise SystemExit("baseline launch is not certified; adversarial ban audit cannot compare")
    baseline_ids = tuple(int(pid) for pid in baseline.selected.squad_ids)
    baseline_submission = _submission_metrics(
        baseline_players,
        baseline_projections,
        baseline_gameweeks,
        baseline,
        baseline_captain_eligible,
        baseline_xi_eligible,
    )

    rows: list[dict] = []
    for name, pid in targets.items():
        result, players, projections, captain_eligible, xi_eligible, gameweeks = _run(
            bundle, {pid}
        )
        selected = result.selected
        ids = tuple(int(value) for value in selected.squad_ids) if selected else tuple()
        certified = bool(
            result.status == "optimal"
            and selected is not None
            and selected.within_gw1_band
            and result.candidate_pool_stable
        )
        gw1_delta = (
            float(selected.gw1_expected_points - baseline.selected.gw1_expected_points)
            if selected
            else None
        )
        future_delta = (
            float(selected.future_objective - baseline.selected.future_objective)
            if selected
            else None
        )
        submission = _submission_metrics(
            players,
            projections,
            gameweeks,
            result,
            captain_eligible,
            xi_eligible,
        )
        rows.append(
            {
                "target": name,
                "player_id": pid,
                "status": result.status,
                "candidate_pool_stable": bool(result.candidate_pool_stable),
                "certified": certified,
                "gw1_delta_vs_baseline": gw1_delta,
                "future_delta_vs_baseline": future_delta,
                "bank_delta_vs_baseline": (
                    float(selected.starting_bank - baseline.selected.starting_bank)
                    if selected
                    else None
                ),
                "captain": submission["captain"],
                "vice_captain": submission["vice_captain"],
                "first_outfield_bench": submission["first_outfield_bench"],
                "playable_outfield_bench": submission["playable_outfield_bench"],
                "outfield_bench_order": submission["outfield_bench_order"],
                "removed_players": _names(out.players, tuple(sorted(set(baseline_ids) - set(ids)))),
                "added_players": _names(out.players, tuple(sorted(set(ids) - set(baseline_ids)))),
                "selected_squad": _names(out.players, ids),
                "reality_interpretation": _interpretation(
                    certified=certified,
                    gw1_delta=gw1_delta,
                    future_delta=future_delta,
                ),
                "note": result.note,
            }
        )

    payload = {
        "contract": CONTRACT,
        "decision_bundle_id": bundle.bundle_id,
        "baseline": {
            "gw1_expected_points": baseline.selected.gw1_expected_points,
            "future_objective": baseline.selected.future_objective,
            "starting_bank": baseline.selected.starting_bank,
            "squad": _names(out.players, baseline_ids),
            **baseline_submission,
        },
        "targets": rows,
        "interpretation_policy": {
            "search_surface_defect_signal": "certified ban improves both GW1 and future objective",
            "genuine_value_support": "certified ban worsens both GW1 and future objective",
            "mixed_launch_vs_future_tradeoff": "certified ban moves GW1 and future objectives in opposite directions",
            "broader_candidate_instability_or_no_certified_solution": "ban result is not stable/certified and must not be promoted",
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(args.csv, index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
