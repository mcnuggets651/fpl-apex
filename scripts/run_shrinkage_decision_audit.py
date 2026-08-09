#!/usr/bin/env python3
"""Run a shadow pre/post decision audit for validated attacking-rate shrinkage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics
from apex_fpl.services.decision_eligibility import captain_eligible_ids
from apex_fpl.services.pipeline import run_pipeline


def _ids(frame: pd.DataFrame) -> set[int]:
    return set(
        pd.to_numeric(frame["player_id"], errors="coerce")
        .dropna()
        .astype(int)
    )


def _gw_xp(projections: pd.DataFrame, gw: int) -> dict[int, float]:
    values = (
        projections[projections["gw"] == int(gw)]
        .groupby("player_id")["xp"]
        .sum()
    )
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get(
            "appearance_probability",
            pd.Series(1.0, index=players.index),
        ),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): float(prob)
        for pid, prob in zip(
            players["player_id"].astype(int),
            values,
            strict=False,
        )
    }


def _mechanics(solution, projections, gw, players, eligible) -> dict:
    result = optimise_gameweek_mechanics(
        solution.squad,
        solution.xi,
        _gw_xp(projections, gw),
        _appearance(players),
        captain_eligible=eligible,
    ).to_dict()
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    result["captain_name"] = names.get(
        result["captain_id"],
        str(result["captain_id"]),
    )
    result["vice_captain_name"] = names.get(
        result["vice_captain_id"],
        str(result["vice_captain_id"]),
    )
    return result


def _score_squad(
    projections: pd.DataFrame,
    squad_ids: set[int],
    gameweeks: list[int],
    decay: float,
) -> float:
    weights = {
        int(gw): float(decay) ** index
        for index, gw in enumerate(gameweeks)
    }
    selected = projections[
        projections["player_id"].astype(int).isin(squad_ids)
    ].copy()
    selected["weight"] = selected["gw"].astype(int).map(weights).fillna(0.0)
    return float((selected["xp"] * selected["weight"]).sum())


def _solution_payload(solution, mechanics) -> dict:
    return {
        "status": solution.status,
        "objective": float(solution.objective),
        "captain": mechanics["captain_name"],
        "vice_captain": mechanics["vice_captain_name"],
        "gw1_expected_total": float(mechanics["expected_total_points"]),
        "squad_ids": sorted(_ids(solution.squad)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output",
        default="reports/shrinkage_decision_audit.json",
    )
    args = parser.parse_args()

    settings = load_settings()
    raw = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="unrestricted",
        force=args.force,
        plan_transfers=False,
        apply_attack_shrinkage=False,
    )
    shrunk = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="unrestricted",
        force=False,
        plan_transfers=False,
        apply_attack_shrinkage=True,
    )
    if raw.gameweeks != shrunk.gameweeks:
        raise SystemExit("raw/shrunk gameweek surfaces differ")

    players = shrunk.players
    eligible = captain_eligible_ids(players)
    common = {
        "players": players,
        "gameweeks": shrunk.gameweeks,
        "budget": settings.budget,
        "max_per_team": settings.max_per_team,
        "decay": settings.fixture_decay,
        "captain_eligible": eligible,
        "projection_col": "xp",
    }
    raw_solution = optimise_initial_horizon(
        **common,
        projections=raw.projections,
    )
    shrunk_solution = optimise_initial_horizon(
        **common,
        projections=shrunk.projections,
    )
    if raw_solution.status != "Optimal" or shrunk_solution.status != "Optimal":
        raise SystemExit(
            "shrinkage A/B optimiser failed: "
            f"raw={raw_solution.status}, shrunk={shrunk_solution.status}"
        )

    gw = shrunk.gameweeks[0]
    raw_mechanics = _mechanics(
        raw_solution,
        raw.projections,
        gw,
        players,
        eligible,
    )
    shrunk_mechanics = _mechanics(
        shrunk_solution,
        shrunk.projections,
        gw,
        players,
        eligible,
    )
    raw_ids = _ids(raw_solution.squad)
    shrunk_ids = _ids(shrunk_solution.squad)
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    raw_optimum_score = _score_squad(
        raw.projections,
        raw_ids,
        raw.gameweeks,
        settings.fixture_decay,
    )
    shrunk_squad_raw_score = _score_squad(
        raw.projections,
        shrunk_ids,
        raw.gameweeks,
        settings.fixture_decay,
    )
    shrunk_optimum_score = _score_squad(
        shrunk.projections,
        shrunk_ids,
        shrunk.gameweeks,
        settings.fixture_decay,
    )
    raw_squad_shrunk_score = _score_squad(
        shrunk.projections,
        raw_ids,
        shrunk.gameweeks,
        settings.fixture_decay,
    )
    raw_regret = raw_optimum_score - shrunk_squad_raw_score

    report = {
        "contract": "apex-attacking-shrinkage-decision-audit-v1",
        "production_changed": False,
        "canonical_publish_attempted": False,
        "promotion_scope": ["xg90", "xa90"],
        "defcon_promoted": False,
        "gameweeks": shrunk.gameweeks,
        "raw_control": _solution_payload(raw_solution, raw_mechanics),
        "validated_shrinkage": _solution_payload(
            shrunk_solution,
            shrunk_mechanics,
        ),
        "decision_delta": {
            "squad_overlap": len(raw_ids & shrunk_ids),
            "players_in": [
                names[pid] for pid in sorted(shrunk_ids - raw_ids)
            ],
            "players_out": [
                names[pid] for pid in sorted(raw_ids - shrunk_ids)
            ],
            "captain_agreement": (
                raw_mechanics["captain_name"]
                == shrunk_mechanics["captain_name"]
            ),
            "raw_optimum_score": raw_optimum_score,
            "shrunk_squad_scored_on_raw_xp": shrunk_squad_raw_score,
            "raw_xp_regret": raw_regret,
            "raw_xp_regret_pct": (
                raw_regret / raw_optimum_score
                if raw_optimum_score > 0
                else None
            ),
            "shrunk_optimum_score": shrunk_optimum_score,
            "raw_squad_scored_on_shrunk_xp": raw_squad_shrunk_score,
            "gw1_expected_total_delta": (
                shrunk_mechanics["expected_total_points"]
                - raw_mechanics["expected_total_points"]
            ),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
