from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.evaluation.historical_minutes_preseason import (
    GitCoreReader,
    HistoricalSeasonSource,
    load_source_manifest,
)
from apex_fpl.services.enrichment import stabilise_low_sample_attack_context


def _numeric(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _aggregate_attack(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
    frame["minutes_played"] = _numeric(frame, "minutes_played", 0.0).fillna(0.0)
    frame["xg"] = _numeric(frame, "xg", np.nan)
    frame["xa"] = _numeric(frame, "xa", np.nan)
    frame = frame.dropna(subset=["player_id"])
    frame["player_id"] = frame["player_id"].astype(int)
    frame = frame[frame["minutes_played"].gt(0)].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["player_id", "minutes", "xg", "xa", "xg90", "xa90"]
        )

    grouped = frame.groupby("player_id", as_index=False).agg(
        minutes=("minutes_played", "sum"),
        xg=("xg", lambda values: values.sum(min_count=1)),
        xa=("xa", lambda values: values.sum(min_count=1)),
    )
    mins = pd.to_numeric(grouped["minutes"], errors="coerce")
    grouped["xg90"] = pd.to_numeric(grouped["xg"], errors="coerce") * 90 / mins
    grouped["xa90"] = pd.to_numeric(grouped["xa"], errors="coerce") * 90 / mins
    return grouped


def _identity_bridge(
    current_players: pd.DataFrame,
    prior_players: pd.DataFrame,
) -> pd.DataFrame:
    current_cols = [
        col
        for col in ["player_code", "player_id", "web_name", "position"]
        if col in current_players.columns
    ]
    current = current_players[current_cols].drop_duplicates().copy()
    prior = prior_players[["player_code", "player_id"]].drop_duplicates().copy()
    current["player_id"] = pd.to_numeric(current["player_id"], errors="coerce")
    prior["player_id"] = pd.to_numeric(prior["player_id"], errors="coerce")
    current = current.dropna(subset=["player_code", "player_id"])
    prior = prior.dropna(subset=["player_code", "player_id"])
    current["player_id"] = current["player_id"].astype(int)
    prior["player_id"] = prior["player_id"].astype(int)

    if current.groupby("player_code")["player_id"].nunique().gt(1).any():
        raise ValueError("historical current-player identity mapping is ambiguous")
    if prior.groupby("player_code")["player_id"].nunique().gt(1).any():
        raise ValueError("historical prior-player identity mapping is ambiguous")

    current = current.drop_duplicates("player_code").rename(
        columns={"player_id": "current_player_id"}
    )
    prior = prior.drop_duplicates("player_code").rename(
        columns={"player_id": "prior_player_id"}
    )
    return current.merge(prior, on="player_code", how="inner", validate="one_to_one")


def build_historical_attack_frame(
    reader: GitCoreReader,
    source: HistoricalSeasonSource,
) -> pd.DataFrame:
    current_players = reader.csv(source.feature_ref, source.current_players_path)
    prior_players = reader.csv(source.feature_ref, source.prior_players_path)
    identity = _identity_bridge(current_players, prior_players)

    prior_parts = []
    for gw in source.prior_gameweeks:
        frame = reader.csv(source.feature_ref, source.prior_stats_template.format(gw=gw))
        frame["gw"] = gw
        prior_parts.append(frame)
    prior_rates = _aggregate_attack(pd.concat(prior_parts, ignore_index=True)).rename(
        columns={
            "player_id": "prior_player_id",
            "minutes": "previous_minutes",
            "xg90": "raw_xg90",
            "xa90": "raw_xa90",
        }
    )

    prediction = identity.merge(
        prior_rates[
            ["prior_player_id", "previous_minutes", "raw_xg90", "raw_xa90"]
        ],
        on="prior_player_id",
        how="left",
        validate="one_to_one",
    ).rename(columns={"current_player_id": "player_id"})
    prediction["minutes"] = 0.0
    prediction["expected_goals_per_90"] = prediction["raw_xg90"]
    prediction["expected_assists_per_90"] = prediction["raw_xa90"]
    corrected = stabilise_low_sample_attack_context(prediction)
    prediction["adjusted_xg90"] = corrected["expected_goals_per_90"]
    prediction["adjusted_xa90"] = corrected["expected_assists_per_90"]
    prediction["xg90_adjusted"] = corrected.get(
        "xg90_low_sample_adjusted", pd.Series(False, index=prediction.index)
    ).astype(bool)
    prediction["xa90_adjusted"] = corrected.get(
        "xa90_low_sample_adjusted", pd.Series(False, index=prediction.index)
    ).astype(bool)

    outcome_parts = []
    for gw in source.outcome_gameweeks:
        frame = reader.csv(source.outcome_ref, source.outcome_stats_template.format(gw=gw))
        frame["gw"] = gw
        outcome_parts.append(frame)
    outcomes = _aggregate_attack(pd.concat(outcome_parts, ignore_index=True)).rename(
        columns={
            "minutes": "future_minutes",
            "xg": "future_xg",
            "xa": "future_xa",
            "xg90": "actual_xg90",
            "xa90": "actual_xa90",
        }
    )
    return prediction.merge(outcomes, on="player_id", how="left", validate="one_to_one")


def _rate_metrics(frame: pd.DataFrame, label: str, mask: pd.Series) -> dict:
    raw = pd.to_numeric(frame[f"raw_{label}90"], errors="coerce")
    adjusted = pd.to_numeric(frame[f"adjusted_{label}90"], errors="coerce")
    actual = pd.to_numeric(frame[f"actual_{label}90"], errors="coerce")
    future_minutes = pd.to_numeric(frame["future_minutes"], errors="coerce").fillna(0.0)
    use = mask & raw.notna() & adjusted.notna() & actual.notna() & future_minutes.gt(0)
    if not use.any():
        return {
            "rows": 0,
            "future_minutes": 0.0,
            "raw_mae": None,
            "adjusted_mae": None,
            "raw_minutes_weighted_mae": None,
            "adjusted_minutes_weighted_mae": None,
            "better_rows": 0,
            "worse_rows": 0,
            "equal_rows": 0,
        }

    raw_error = (raw.loc[use] - actual.loc[use]).abs()
    adjusted_error = (adjusted.loc[use] - actual.loc[use]).abs()
    weights = future_minutes.loc[use]
    raw_weighted = float(np.average(raw_error, weights=weights))
    adjusted_weighted = float(np.average(adjusted_error, weights=weights))
    return {
        "rows": int(use.sum()),
        "future_minutes": float(weights.sum()),
        "raw_mae": float(raw_error.mean()),
        "adjusted_mae": float(adjusted_error.mean()),
        "raw_minutes_weighted_mae": raw_weighted,
        "adjusted_minutes_weighted_mae": adjusted_weighted,
        "better_rows": int((adjusted_error < raw_error).sum()),
        "worse_rows": int((adjusted_error > raw_error).sum()),
        "equal_rows": int(np.isclose(adjusted_error, raw_error).sum()),
    }


def score_historical_attack_frame(frame: pd.DataFrame) -> dict:
    result: dict[str, dict] = {}
    for label in ("xg", "xa"):
        changed = frame[f"{label}90_adjusted"].fillna(False).astype(bool)
        result[label] = {
            "all_evaluable": _rate_metrics(frame, label, pd.Series(True, index=frame.index)),
            "adjusted_cohort": _rate_metrics(frame, label, changed),
            "adjusted_players": int(changed.sum()),
        }
    return result


def _season_payload(
    reader: GitCoreReader,
    source: HistoricalSeasonSource,
) -> tuple[dict, pd.DataFrame]:
    frame = build_historical_attack_frame(reader, source)
    metrics = score_historical_attack_frame(frame)
    changed = frame[
        frame["xg90_adjusted"].fillna(False) | frame["xa90_adjusted"].fillna(False)
    ].copy()
    columns = [
        col
        for col in [
            "player_id",
            "web_name",
            "position",
            "previous_minutes",
            "raw_xg90",
            "adjusted_xg90",
            "actual_xg90",
            "raw_xa90",
            "adjusted_xa90",
            "actual_xa90",
            "future_minutes",
            "xg90_adjusted",
            "xa90_adjusted",
        ]
        if col in changed.columns
    ]
    rows = changed[columns].sort_values("previous_minutes").head(30).to_dict("records")
    return (
        {
            "season": source.season,
            "feature_ref": source.feature_ref,
            "outcome_ref": source.outcome_ref,
            "outcome_gameweeks": list(source.outcome_gameweeks),
            "metrics": metrics,
            "changed_examples": rows,
        },
        frame,
    )


def run_low_sample_attack_audit(core_root, manifest_path) -> dict:
    sources, _ = load_source_manifest(manifest_path)
    reader = GitCoreReader(core_root)
    seasons = []
    frames = []
    for source in sources:
        payload, frame = _season_payload(reader, source)
        seasons.append(payload)
        frame["season"] = source.season
        frames.append(frame)

    combined_frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined = score_historical_attack_frame(combined_frame) if not combined_frame.empty else {}
    checks = []
    for label in ("xg", "xa"):
        cohort = combined.get(label, {}).get("adjusted_cohort", {})
        rows = int(cohort.get("rows", 0) or 0)
        raw = cohort.get("raw_minutes_weighted_mae")
        adjusted = cohort.get("adjusted_minutes_weighted_mae")
        if rows == 0 or raw is None or adjusted is None:
            checks.append({"rate": label, "status": "inconclusive", "rows": rows})
        else:
            checks.append(
                {
                    "rate": label,
                    "status": "pass" if adjusted <= raw else "fail",
                    "rows": rows,
                    "raw_minutes_weighted_mae": raw,
                    "adjusted_minutes_weighted_mae": adjusted,
                    "delta": adjusted - raw,
                }
            )

    if any(check["status"] == "fail" for check in checks):
        result = "mixed_or_worse"
    elif any(check["status"] == "inconclusive" for check in checks):
        result = "inconclusive"
    else:
        result = "improves_or_neutral"

    return {
        "contract": "apex-low-sample-attack-reliability-audit-v1",
        "diagnostic_scope": (
            "bounded returning-player correction only; not activation of the retired "
            "general Bayesian shrinkage path"
        ),
        "independent_historical_seasons": len(seasons),
        "result": result,
        "checks": checks,
        "combined_metrics": combined,
        "seasons": seasons,
    }
