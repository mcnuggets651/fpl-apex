#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import audit_understat_player_production_ab as audit


def _load_cvar_result(
    path: str,
    *,
    surface: str,
    bundle_id: str,
    scenario_seed: int,
    scenario_count: int,
) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "contract": "apex-understat-player-cvar-phase-v1",
        "surface": surface,
        "decision_bundle_id": bundle_id,
        "scenario_seed": scenario_seed,
        "scenario_count": scenario_count,
        "status": "Optimal",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise SystemExit(
                f"invalid {surface} CVaR phase result: {key}={payload.get(key)!r}, expected {value!r}"
            )
    return payload


def _robust_result(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        status=str(payload["status"]),
        objective=float(payload["objective"]),
        mean_points=float(payload["mean_points"]),
        lower_tail_cvar=float(payload["lower_tail_cvar"]),
        squad=pd.DataFrame({"player_id": [int(pid) for pid in payload["squad_ids"]]}),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument(
        "--historical-audit",
        default="reports/understat_player_predictive_audit.json",
    )
    parser.add_argument("--baseline-cvar", required=True)
    parser.add_argument("--challenger-cvar", required=True)
    parser.add_argument("--output", default="reports/understat_player_production_ab.json")
    parser.add_argument("--scenario-seed", type=int, default=20260807)
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--alternatives", type=int, default=12)
    args = parser.parse_args()

    bundle = audit.DecisionBundle.load(args.bundle_dir)
    baseline_payload = _load_cvar_result(
        args.baseline_cvar,
        surface="baseline",
        bundle_id=bundle.bundle_id,
        scenario_seed=args.scenario_seed,
        scenario_count=args.stochastic_scenarios,
    )
    challenger_payload = _load_cvar_result(
        args.challenger_cvar,
        surface="challenger",
        bundle_id=bundle.bundle_id,
        scenario_seed=args.scenario_seed,
        scenario_count=args.stochastic_scenarios,
    )
    if baseline_payload.get("official_snapshot") != challenger_payload.get("official_snapshot"):
        raise SystemExit("baseline/challenger CVaR phases did not use the same official snapshot")
    if baseline_payload.get("xg_understat_weight") != challenger_payload.get("xg_understat_weight"):
        raise SystemExit("baseline/challenger CVaR phases disagree on validated xG weight")
    if baseline_payload.get("xa_understat_weight") != challenger_payload.get("xa_understat_weight"):
        raise SystemExit("baseline/challenger CVaR phases disagree on validated xA weight")

    phase_results = {
        "baseline": _robust_result(baseline_payload),
        "challenger": _robust_result(challenger_payload),
    }
    scenario_calls = iter(("baseline", "challenger"))

    def bounded_generate_projection_scenarios(*_args, **_kwargs):
        try:
            return next(scenario_calls)
        except StopIteration as exc:
            raise RuntimeError("unexpected extra scenario-generation call") from exc

    def bounded_optimise_initial_cvar(*, scenarios, **_kwargs):
        if scenarios not in phase_results:
            raise RuntimeError(f"unexpected bounded CVaR surface marker: {scenarios!r}")
        return phase_results[scenarios]

    audit.generate_projection_scenarios = bounded_generate_projection_scenarios
    audit.optimise_initial_cvar = bounded_optimise_initial_cvar

    sys.argv = [
        "audit_understat_player_production_ab.py",
        "--bundle-dir",
        args.bundle_dir,
        "--historical-audit",
        args.historical_audit,
        "--output",
        args.output,
        "--scenario-seed",
        str(args.scenario_seed),
        "--stochastic-scenarios",
        str(args.stochastic_scenarios),
        "--alternatives",
        str(args.alternatives),
    ]
    audit.main()


if __name__ == "__main__":
    main()
