#!/usr/bin/env python3
"""Audit the projection surface actually used by Apex without changing production.

This is a diagnostic-only shadow audit. It exposes configured versus effective
expert authority, player-level source contributions, Apex component decomposition,
selected-player exact-shortlist regret, high-disagreement rows and same-mechanics
source ablations. It never mutates canonical weights or recommendations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.models.ensemble import EXPERT_COLUMNS
from apex_fpl.optimisation.exact_decision import optimise_exact_horizon_decision
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.pipeline import run_pipeline


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def build_source_authority(projections: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """Return configured and realised expert authority for each Gameweek."""
    rows: list[dict] = []
    for gw, group in projections.groupby("gw", sort=True):
        total_rows = int(len(group))
        for key, column in EXPERT_COLUMNS.items():
            configured = max(float(weights.get(key, 0.0)), 0.0)
            effective_col = f"effective_weight_{key}"
            contribution_col = f"xp_expert_{key}"
            present = _numeric(group, column).notna()
            effective = _numeric(group, effective_col).fillna(0.0)
            contribution = _numeric(group, contribution_col).fillna(0.0)
            rows.append(
                {
                    "gw": int(gw),
                    "expert": key,
                    "column": column,
                    "configured_weight": configured,
                    "active_rows": int(present.sum()),
                    "total_rows": total_rows,
                    "row_coverage": float(present.mean()) if total_rows else 0.0,
                    "mean_effective_weight": float(effective.mean()) if total_rows else 0.0,
                    "max_effective_weight": float(effective.max()) if total_rows else 0.0,
                    "mean_xp_contribution": float(contribution.mean()) if total_rows else 0.0,
                    "configured_but_inactive": bool(configured > 0 and not present.any()),
                }
            )
    return pd.DataFrame(rows)


def _explicit_blend(frame: pd.DataFrame, keys: tuple[str, ...], weights: dict[str, float]) -> pd.Series:
    numerator = np.zeros(len(frame), dtype=float)
    denominator = np.zeros(len(frame), dtype=float)
    for key in keys:
        column = EXPERT_COLUMNS[key]
        values = _numeric(frame, column).to_numpy(float)
        mask = np.isfinite(values)
        weight = max(float(weights.get(key, 0.0)), 0.0)
        numerator[mask] += values[mask] * weight
        denominator[mask] += weight
    return pd.Series(
        np.where(denominator > 0, numerator / np.maximum(denominator, 1e-12), 0.0),
        index=frame.index,
        dtype=float,
    )


def build_ablation_surfaces(projections: pd.DataFrame, weights: dict[str, float]) -> dict[str, pd.Series]:
    """Build diagnostic xP surfaces from the same sealed projection inputs."""
    current = _numeric(projections, "xp").fillna(0.0)
    apex = _numeric(projections, "apex_xp").fillna(0.0)
    airsenal = _numeric(projections, "airsenal_xp").fillna(0.0)
    apex_airsenal = _explicit_blend(projections, ("apex_model", "airsenal"), weights)
    explicit_available = _explicit_blend(
        projections,
        ("official_ep", "apex_model", "airsenal", "market"),
        weights,
    )
    return {
        "current_effective_blend": current,
        "apex_only": apex,
        "airsenal_only": airsenal,
        "apex_plus_airsenal": apex_airsenal,
        "explicit_available_sources": explicit_available,
    }


def _decision_payload(decision) -> dict:
    if decision.status != "Optimal":
        return {"status": decision.status}
    names = {
        int(row.player_id): str(row.web_name)
        for row in decision.solution.squad[["player_id", "web_name"]].itertuples(index=False)
    }
    weeks = []
    for week in decision.weeks:
        weeks.append(
            {
                "gw": int(week.gw),
                "discount": float(week.discount),
                "xi_ids": [int(x) for x in week.xi_ids],
                "captain_id": int(week.mechanics.captain_id),
                "vice_captain_id": int(week.mechanics.vice_captain_id),
                "expected_total_points": float(week.mechanics.expected_total_points),
            }
        )
    return {
        "status": decision.status,
        "objective": float(decision.objective),
        "squad_ids": sorted(names),
        "squad_names": [names[pid] for pid in sorted(names)],
        "weeks": weeks,
    }


def build_shortlist_regret(decision, players: pd.DataFrame) -> pd.DataFrame:
    """Exact-mechanics regret from the authoritative near-optimal shortlist."""
    columns = [
        "player_id",
        "web_name",
        "baseline_objective",
        "best_without_objective",
        "objective_regret",
        "alternative_found_in_shortlist",
        "replacement_player_ids",
        "replacement_player_names",
    ]
    if decision.status != "Optimal":
        return pd.DataFrame(columns=columns)
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]].drop_duplicates("player_id").itertuples(index=False)
    }
    selected = set(decision.solution.squad["player_id"].astype(int))
    baseline = float(decision.objective)
    rows: list[dict] = []
    for pid in sorted(selected):
        alternatives = [candidate for candidate in decision.candidates if pid not in set(candidate.squad_ids)]
        if alternatives:
            best = max(alternatives, key=lambda candidate: candidate.exact_objective)
            replacement = sorted(set(best.squad_ids) - selected)
            objective = float(best.exact_objective)
            regret = baseline - objective
        else:
            replacement = []
            objective = float("nan")
            regret = float("nan")
        rows.append(
            {
                "player_id": pid,
                "web_name": names.get(pid, str(pid)),
                "baseline_objective": baseline,
                "best_without_objective": objective,
                "objective_regret": regret,
                "alternative_found_in_shortlist": bool(alternatives),
                "replacement_player_ids": replacement,
                "replacement_player_names": [names.get(x, str(x)) for x in replacement],
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_disagreement_report(
    projections: pd.DataFrame,
    players: pd.DataFrame,
    gameweeks: list[int],
    decay: float,
) -> pd.DataFrame:
    frame = projections[projections["gw"].isin(gameweeks)].copy()
    weights = {int(gw): float(decay) ** idx for idx, gw in enumerate(gameweeks)}
    frame["_discount"] = frame["gw"].map(weights).fillna(0.0)
    frame["_apex_raw"] = _numeric(frame, "apex_xp").fillna(0.0)
    frame["_airsenal_raw"] = _numeric(frame, "airsenal_xp").fillna(0.0)
    frame["_apex_discounted_utility"] = frame["_apex_raw"] * frame["_discount"]
    frame["_airsenal_discounted_utility"] = frame["_airsenal_raw"] * frame["_discount"]

    rate_aggregations: dict[str, tuple[str, str]] = {
        "model_xg90": ("model_xg90", "first"),
        "model_xa90": ("model_xa90", "first"),
    }
    for column in [
        "attack_model_xg90",
        "attack_model_xa90",
        "xg_rate_credibility_adjusted",
        "xa_rate_credibility_adjusted",
        "attack_rate_reliability",
    ]:
        if column in frame.columns:
            rate_aggregations[column] = (column, "first")

    summary = frame.groupby("player_id", as_index=False).agg(
        apex_raw_horizon_xp=("_apex_raw", "sum"),
        airsenal_raw_horizon_xp=("_airsenal_raw", "sum"),
        apex_discounted_horizon_utility=("_apex_discounted_utility", "sum"),
        airsenal_discounted_horizon_utility=("_airsenal_discounted_utility", "sum"),
        **rate_aggregations,
    )
    summary["raw_apex_minus_airsenal_xp"] = (
        summary["apex_raw_horizon_xp"] - summary["airsenal_raw_horizon_xp"]
    )
    summary["raw_absolute_disagreement_xp"] = summary["raw_apex_minus_airsenal_xp"].abs()
    summary["discounted_apex_minus_airsenal_utility"] = (
        summary["apex_discounted_horizon_utility"]
        - summary["airsenal_discounted_horizon_utility"]
    )
    summary["discounted_absolute_disagreement_utility"] = (
        summary["discounted_apex_minus_airsenal_utility"].abs()
    )
    keep = [
        col for col in [
            "player_id", "web_name", "position", "price", "minutes", "previous_minutes",
            "expected_goals_per_90", "expected_assists_per_90",
        ] if col in players.columns
    ]
    summary = summary.merge(players[keep].drop_duplicates("player_id"), on="player_id", how="left")
    current = _numeric(summary, "minutes").fillna(0.0)
    previous = _numeric(summary, "previous_minutes").fillna(0.0)
    summary["competitive_evidence_minutes"] = current + previous
    if "position" in summary.columns:
        summary["xg90_position_percentile"] = summary.groupby("position")["model_xg90"].rank(pct=True)
        summary["xa90_position_percentile"] = summary.groupby("position")["model_xa90"].rank(pct=True)
    else:
        summary["xg90_position_percentile"] = np.nan
        summary["xa90_position_percentile"] = np.nan

    # Source-model disagreement and low-sample rate credibility are separate risks.
    # A tiny-sample extreme rate must remain visible even when AIrsenal happens to
    # agree with the player's aggregate xP. Disagreement is retained as an
    # additional prioritisation flag, never as a prerequisite for detecting the
    # unsupported rate itself.
    summary["high_disagreement"] = summary["raw_absolute_disagreement_xp"].ge(3.0)
    summary["low_sample_extreme_rate"] = (
        summary["competitive_evidence_minutes"].lt(270.0)
        & (
            summary["xg90_position_percentile"].ge(0.90)
            | summary["xa90_position_percentile"].ge(0.90)
        )
    )
    summary["low_sample_extreme_rate_with_disagreement"] = (
        summary["low_sample_extreme_rate"]
        & summary["raw_absolute_disagreement_xp"].ge(2.0)
    )
    return summary.sort_values(
        "raw_absolute_disagreement_xp", ascending=False
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="reports/projection_truth")
    parser.add_argument("--ablation-candidates", type=int, default=8)
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    authority = build_source_authority(out.projections, settings.weights)
    authority.to_csv(output_dir / "source_authority.csv", index=False)

    decision_players, eligibility = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(decision_players)
    xi_eligible = set(
        decision_players.loc[decision_players["xi_evidence_eligible"], "player_id"].astype(int)
    )
    common = dict(
        players=decision_players,
        gameweeks=out.gameweeks,
        budget=float(settings.budget),
        max_per_team=int(settings.max_per_team),
        decay=float(settings.fixture_decay),
        shortlist_bench_weight=float(settings.approximate_bench_weight),
        candidate_limit=int(settings.exact_candidate_limit),
        candidate_regret_fraction=float(settings.exact_candidate_regret_fraction),
        near_equivalent_points=float(settings.exact_near_equivalent_points),
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    baseline = optimise_exact_horizon_decision(
        projections=out.projections,
        projection_col="xp",
        **common,
    )
    regret = build_shortlist_regret(baseline, decision_players)
    regret.to_json(output_dir / "selected_player_regret.json", orient="records", indent=2)

    disagreement = build_disagreement_report(
        out.projections,
        out.players,
        out.gameweeks,
        settings.fixture_decay,
    )
    disagreement.to_csv(output_dir / "player_source_disagreement.csv", index=False)

    component_cols = [
        "player_id", "gw", "xp", "official_xp", "apex_xp", "airsenal_xp", "market_xp",
        "xp_expert_official_ep", "xp_expert_apex_model", "xp_expert_airsenal", "xp_expert_market",
        "effective_weight_official_ep", "effective_weight_apex_model",
        "effective_weight_airsenal", "effective_weight_market",
        "xp_appearance", "xp_attack", "xp_clean_sheet", "xp_defensive_contribution",
        "xp_saves", "xp_bonus_prior", "xp_set_piece_prior", "model_xg90", "model_xa90",
        "attack_model_xg90", "attack_model_xa90", "xg_rate_credibility_adjusted",
        "xa_rate_credibility_adjusted", "attack_rate_reliability",
    ]
    component_cols = [column for column in component_cols if column in out.projections.columns]
    components = out.projections[component_cols].copy()
    names = out.players[[c for c in ["player_id", "web_name", "team_name", "position", "price"] if c in out.players.columns]].drop_duplicates("player_id")
    components = components.merge(names, on="player_id", how="left")
    components.to_csv(output_dir / "player_projection_truth.csv", index=False)

    ablations = build_ablation_surfaces(out.projections, settings.weights)
    ablation_results: dict[str, dict] = {}
    for name, surface in ablations.items():
        shadow = out.projections.copy()
        shadow["truth_audit_xp"] = surface
        decision = optimise_exact_horizon_decision(
            projections=shadow,
            projection_col="truth_audit_xp",
            candidate_limit=min(int(args.ablation_candidates), int(settings.exact_candidate_limit)),
            players=decision_players,
            gameweeks=out.gameweeks,
            budget=float(settings.budget),
            max_per_team=int(settings.max_per_team),
            decay=float(settings.fixture_decay),
            shortlist_bench_weight=float(settings.approximate_bench_weight),
            candidate_regret_fraction=float(settings.exact_candidate_regret_fraction),
            near_equivalent_points=float(settings.exact_near_equivalent_points),
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
        )
        ablation_results[name] = _decision_payload(decision)

    inactive = authority[
        authority["configured_but_inactive"].eq(True)  # noqa: E712
    ][["gw", "expert", "configured_weight"]].to_dict("records")
    report = {
        "contract": "apex-projection-truth-audit-v1",
        "diagnostic_only": True,
        "production_selection_changed": False,
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "configured_weights": {key: float(value) for key, value in settings.weights.items()},
        "configured_but_inactive": inactive,
        "baseline_exact_decision": _decision_payload(baseline),
        "eligibility_contract": eligibility,
        "high_disagreement_count": int(disagreement["high_disagreement"].sum()),
        "low_sample_extreme_rate_count": int(disagreement["low_sample_extreme_rate"].sum()),
        "low_sample_extreme_rate_with_disagreement_count": int(
            disagreement["low_sample_extreme_rate_with_disagreement"].sum()
        ),
        "largest_disagreements": disagreement.head(20).to_dict("records"),
        "source_ablations": ablation_results,
        "ablation_candidate_limit": min(int(args.ablation_candidates), int(settings.exact_candidate_limit)),
        "notes": [
            "Ablations reuse the same players, prices, fixture surface, availability, evidence eligibility and exact XI/captain/vice/autosub mechanics.",
            "No source weight or projection component is promoted by this audit.",
            "Low-sample extreme-rate flags are independent of AIrsenal disagreement; a separate joint flag records cases where both risks coincide.",
            "Selected-player regret is exact within the authoritative exact-horizon candidate shortlist; absence of an alternative is reported rather than extrapolated.",
        ],
    }
    (output_dir / "projection_truth_audit.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(output_dir / "projection_truth_audit.json")


if __name__ == "__main__":
    main()
