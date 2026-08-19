#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

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
    return optimise_with_bounded_stability_retry(
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


def _names(players: pd.DataFrame, ids: tuple[int, ...] | None) -> list[str]:
    if not ids:
        return []
    lookup = players.set_index("player_id")["web_name"].astype(str).to_dict()
    return [lookup.get(int(pid), str(pid)) for pid in ids]


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

    baseline = _run(bundle, set())
    if not (
        baseline.status == "optimal"
        and baseline.selected is not None
        and baseline.candidate_pool_stable
    ):
        raise SystemExit("baseline launch is not certified; adversarial ban audit cannot compare")
    baseline_ids = tuple(int(pid) for pid in baseline.selected.squad_ids)

    rows: list[dict] = []
    for name, pid in targets.items():
        result = _run(bundle, {pid})
        selected = result.selected
        ids = tuple(int(value) for value in selected.squad_ids) if selected else tuple()
        rows.append(
            {
                "target": name,
                "player_id": pid,
                "status": result.status,
                "candidate_pool_stable": bool(result.candidate_pool_stable),
                "certified": bool(
                    result.status == "optimal"
                    and selected is not None
                    and selected.within_gw1_band
                    and result.candidate_pool_stable
                ),
                "gw1_delta_vs_baseline": (
                    float(selected.gw1_expected_points - baseline.selected.gw1_expected_points)
                    if selected
                    else None
                ),
                "future_delta_vs_baseline": (
                    float(selected.future_objective - baseline.selected.future_objective)
                    if selected
                    else None
                ),
                "bank_delta_vs_baseline": (
                    float(selected.starting_bank - baseline.selected.starting_bank)
                    if selected
                    else None
                ),
                "removed_players": _names(out.players, tuple(sorted(set(baseline_ids) - set(ids)))),
                "added_players": _names(out.players, tuple(sorted(set(ids) - set(baseline_ids)))),
                "selected_squad": _names(out.players, ids),
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
        },
        "targets": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(args.csv, index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
