#!/usr/bin/env python3
"""Select a fixture fallback with clean Premier League-only holdout evidence.

This audit is intentionally promotion-free. It answers three separate questions:
1. Does the frozen Understat challenger beat the neutral league-average fallback
   on untouched 2024/25 and 2025/26 seasons?
2. On 2025/26 Premier League fixtures with genuine pre-match Core Elo, how do
   pure Understat and pure Elo compare out of sample?
3. Does a convex component-specific blend, calibrated only on GW1-19, improve
   on both pure experts on untouched GW20-38?

FPL Core "By Gameweek" files can contain cup rows. Those rows are excluded
before any Elo comparison so cup Elo can never be mistaken for EPL evidence.
The report changes no production setting.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apex_fpl.config import load_settings
from apex_fpl.data.team_mapping import canonical_team
from apex_fpl.data.understat import load_understat_history
from apex_fpl.models.team_goals import TeamGoalConfig
from apex_fpl.services.provenance import load_upstream_pins
from validate_team_strength import (
    _bootstrap_delta,
    _loss_columns,
    _metrics,
    _passes,
    _predict_season,
)

CORE_SEASON = "2025-2026"
FROZEN_CFG = TeamGoalConfig(half_life_days=180.0, prior_matches=5.0)
BLEND_GRID = (0.0, 0.25, 0.50, 0.75, 1.0)
HOME_GOALS_BASELINE = 1.55
AWAY_GOALS_BASELINE = 1.25

_RETRY = Retry(
    total=4,
    connect=4,
    read=4,
    status=4,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    raise_on_status=False,
)
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(max_retries=_RETRY))


def _raw_url(ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{ref}/{path}"


def _read_csv(url: str) -> pd.DataFrame:
    """Read a pinned holdout CSV with bounded transport retries and fail closed.

    Network resets and retriable HTTP status codes may be retried, but a final
    transport failure, non-retriable HTTP failure or malformed CSV is still fatal.
    Validation evidence is never fabricated or silently replaced with stale data.
    """
    response = _SESSION.get(url, timeout=(15, 45))
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _canonical_name(row: pd.Series) -> str | None:
    for column in ("fotmob_name", "name"):
        value = row.get(column)
        if pd.notna(value) and str(value).strip():
            return canonical_team(str(value))
    return None


def _load_core_epl_holdout(ref: str) -> pd.DataFrame:
    teams = _read_csv(_raw_url(ref, f"data/{CORE_SEASON}/teams.csv"))
    mapping: dict[int, str] = {}
    for _, row in teams.iterrows():
        code = pd.to_numeric(pd.Series([row.get("code")]), errors="coerce").iloc[0]
        name = _canonical_name(row)
        if pd.notna(code) and name:
            mapping[int(code)] = name

    rows: list[pd.DataFrame] = []
    for gw in range(1, 39):
        try:
            frame = _read_csv(
                _raw_url(ref, f"data/{CORE_SEASON}/By Gameweek/GW{gw}/fixtures.csv")
            )
        except requests.HTTPError:
            continue
        if "tournament" in frame.columns:
            frame = frame[frame["tournament"].astype(str).str.casefold().eq("prem")]
        current = frame[pd.to_numeric(frame.get("gameweek"), errors="coerce") == gw].copy()
        required = {
            "home_team",
            "away_team",
            "home_team_elo",
            "away_team_elo",
            "home_expected_goals_xg",
            "away_expected_goals_xg",
            "home_score",
            "away_score",
        }
        if current.empty or not required.issubset(current.columns):
            continue
        current["gw"] = gw
        current["team_home"] = pd.to_numeric(current["home_team"], errors="coerce").map(mapping)
        current["team_away"] = pd.to_numeric(current["away_team"], errors="coerce").map(mapping)
        for source, target in (
            ("home_team_elo", "elo_home"),
            ("away_team_elo", "elo_away"),
            ("home_expected_goals_xg", "actual_xg_home"),
            ("away_expected_goals_xg", "actual_xg_away"),
            ("home_score", "goals_home"),
            ("away_score", "goals_away"),
        ):
            current[target] = pd.to_numeric(current[source], errors="coerce")
        rows.append(
            current[
                [
                    "gw",
                    "team_home",
                    "team_away",
                    "elo_home",
                    "elo_away",
                    "actual_xg_home",
                    "actual_xg_away",
                    "goals_home",
                    "goals_away",
                ]
            ]
        )
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True).dropna()
    return out.drop_duplicates(["gw", "team_home", "team_away"]).reset_index(drop=True)


def _elo_lambdas(d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    diff = d["elo_home"].to_numpy(float) - d["elo_away"].to_numpy(float)
    raw = np.clip(np.exp(diff / 1200.0), 0.72, 1.38)
    home_mult = raw**0.45
    away_mult = (1.0 / raw) ** 0.45
    home = np.clip(HOME_GOALS_BASELINE * home_mult, 0.40, 3.35)
    away = np.clip(AWAY_GOALS_BASELINE * away_mult, 0.30, 2.95)
    return home, away


def _metric_summary(d: pd.DataFrame, prefix: str) -> dict:
    return {
        "xg_rmse": math.sqrt(float(d[f"{prefix}_xg_sq"].mean() / 2.0)),
        "clean_sheet_brier": float(d[f"{prefix}_cs_brier"].mean() / 2.0),
        "goal_poisson_nll": float(d[f"{prefix}_goal_nll"].mean() / 2.0),
    }


def _score_models(d: pd.DataFrame, attack_alpha: float, clean_sheet_alpha: float) -> pd.DataFrame:
    under_home = d["pred_home"].to_numpy(float)
    under_away = d["pred_away"].to_numpy(float)
    elo_home, elo_away = _elo_lambdas(d)
    attack_home = attack_alpha * under_home + (1.0 - attack_alpha) * elo_home
    attack_away = attack_alpha * under_away + (1.0 - attack_alpha) * elo_away
    cs_home = clean_sheet_alpha * under_home + (1.0 - clean_sheet_alpha) * elo_home
    cs_away = clean_sheet_alpha * under_away + (1.0 - clean_sheet_alpha) * elo_away

    out = _loss_columns(d, "understat", under_home, under_away)
    out = _loss_columns(out, "elo", elo_home, elo_away)
    out = _loss_columns(out, "component", attack_home, attack_away)
    cs = _loss_columns(d, "component_cs", cs_home, cs_away)
    out["component_cs_brier"] = cs["component_cs_cs_brier"].to_numpy(float)
    return out


def _select_component_weights(train: pd.DataFrame) -> tuple[float, float, list[dict]]:
    grid: list[dict] = []
    best_attack: tuple[float, float, float] | None = None
    best_cs: tuple[float, float] | None = None
    attack_alpha = 0.0
    cs_alpha = 0.0
    for alpha in BLEND_GRID:
        scored = _score_models(train, alpha, alpha)
        metric = _metric_summary(scored, "component")
        grid.append({"understat_weight": alpha, **metric})
        attack_key = (metric["xg_rmse"], metric["goal_poisson_nll"], alpha)
        cs_key = (metric["clean_sheet_brier"], alpha)
        if best_attack is None or attack_key < best_attack:
            best_attack = attack_key
            attack_alpha = alpha
        if best_cs is None or cs_key < best_cs:
            best_cs = cs_key
            cs_alpha = alpha
    return attack_alpha, cs_alpha, grid


def _comparison(d: pd.DataFrame, rival: str) -> dict:
    return {
        "xg_squared_error_delta_bootstrap": _bootstrap_delta(
            d, "component_xg_sq", f"{rival}_xg_sq"
        ),
        "clean_sheet_brier_delta_bootstrap": _bootstrap_delta(
            d, "component_cs_brier", f"{rival}_cs_brier"
        ),
        "goal_nll_delta_bootstrap": _bootstrap_delta(
            d, "component_goal_nll", f"{rival}_goal_nll"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/fixture_fallback_selection.json")
    args = parser.parse_args()

    settings = load_settings()
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    history = load_understat_history(
        range(2018, 2027),
        active_season=2026,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=False,
    )

    neutral_holdout = pd.concat(
        [
            _predict_season(history.matches, season, FROZEN_CFG)
            for season in (2024, 2025)
        ],
        ignore_index=True,
    )
    replacement_metrics = _metrics(neutral_holdout)
    understat_replacement_pass = _passes(replacement_metrics)

    understat_2025 = _predict_season(history.matches, 2025, FROZEN_CFG)[
        ["team_home", "team_away", "pred_home", "pred_away"]
    ]
    core = _load_core_epl_holdout(core_ref)
    paired = core.merge(
        understat_2025,
        on=["team_home", "team_away"],
        how="inner",
        validate="many_to_one",
    )
    if len(paired) < 300:
        raise RuntimeError(f"insufficient clean EPL Elo/Understat overlap: {len(paired)} matches")

    train = paired[paired["gw"] <= 19].copy()
    test = paired[paired["gw"] >= 20].copy()
    if len(test) < 150:
        raise RuntimeError(f"insufficient untouched EPL holdout: {len(test)} matches")
    attack_alpha, cs_alpha, calibration = _select_component_weights(train)
    scored = _score_models(test, attack_alpha, cs_alpha)
    metrics = {
        name: _metric_summary(scored, name)
        for name in ("understat", "elo", "component")
    }
    comparisons = {
        "component_vs_understat": _comparison(scored, "understat"),
        "component_vs_elo": _comparison(scored, "elo"),
    }
    hybrid_metric_dominance = bool(
        metrics["component"]["xg_rmse"] <= min(
            metrics["understat"]["xg_rmse"], metrics["elo"]["xg_rmse"]
        )
        and metrics["component"]["clean_sheet_brier"] <= min(
            metrics["understat"]["clean_sheet_brier"],
            metrics["elo"]["clean_sheet_brier"],
        )
        and metrics["component"]["goal_poisson_nll"] <= min(
            metrics["understat"]["goal_poisson_nll"],
            metrics["elo"]["goal_poisson_nll"],
        )
    )

    best_pure = min(
        ("understat", metrics["understat"]),
        ("elo", metrics["elo"]),
        key=lambda item: (
            item[1]["xg_rmse"],
            item[1]["clean_sheet_brier"],
            item[1]["goal_poisson_nll"],
        ),
    )[0]
    historical_choice = "component_hybrid" if hybrid_metric_dominance else best_pure

    report = {
        "contract": "apex-fixture-fallback-selection-v1",
        "production_changed": False,
        "core_ref": core_ref,
        "core_scope": "Premier League only; cup rows explicitly excluded",
        "understat_config": {
            "half_life_days": FROZEN_CFG.half_life_days,
            "prior_matches": FROZEN_CFG.prior_matches,
        },
        "understat_vs_neutral_replacement": {
            "holdout_seasons": [2024, 2025],
            "n_matches": int(len(neutral_holdout)),
            "metrics": replacement_metrics,
            "pass": bool(understat_replacement_pass),
        },
        "epl_elo_understat_overlap_2025_26": int(len(paired)),
        "hybrid_calibration": {
            "gws": "1-19",
            "grid": list(BLEND_GRID),
            "selected_attack_understat_weight": attack_alpha,
            "selected_clean_sheet_understat_weight": cs_alpha,
            "scores": calibration,
        },
        "untouched_holdout": {
            "gws": "20-38",
            "n_matches": int(len(test)),
            "metrics": metrics,
            "comparisons": comparisons,
            "hybrid_metric_dominance": hybrid_metric_dominance,
            "historical_choice": historical_choice,
        },
        "promotion_rule": (
            "This report is evidence only. Understat may replace the neutral fallback only "
            "when understat_vs_neutral_replacement.pass is true. A hybrid is not live-safe "
            "unless current EPL Elo coverage is complete; historical superiority alone does "
            "not authorize use of missing live Elo."
        ),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "understat_replacement_pass": understat_replacement_pass,
                "historical_choice": historical_choice,
                "selected_attack_understat_weight": attack_alpha,
                "selected_clean_sheet_understat_weight": cs_alpha,
                "output": str(path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
