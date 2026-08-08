from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


RATE_COLUMNS = {
    "xg90": ("expected_goals_per_90", "previous_expected_goals_per_90"),
    "xa90": ("expected_assists_per_90", "previous_expected_assists_per_90"),
    "defcon90": (
        "defensive_contribution_per_90",
        "previous_defensive_contribution_per_90",
    ),
}


@dataclass(frozen=True)
class RateShrinkageConfig:
    """Equivalent-prior-minute strengths learned by no-hindsight validation."""

    prior_minutes: dict[str, float] = field(
        default_factory=lambda: {"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0}
    )
    min_group_players: int = 6
    min_group_minutes: float = 900.0


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _evidence_rate(
    players: pd.DataFrame,
    current_col: str,
    previous_col: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Resolve a rate and the minutes that actually support it.

    Before GW1, FPL can expose non-zero per-90 context while current-season minutes
    are still zero. Such a value must not be treated as a fresh sample. Prefer the
    explicitly bridged prior-season rate/minutes when available. Once competitive
    current-season minutes exist, use the current cumulative rate with those minutes.
    """
    current_rate = _numeric(players, current_col)
    previous_rate = _numeric(players, previous_col)
    current_minutes = _numeric(players, "minutes").fillna(0).clip(lower=0)
    previous_minutes = _numeric(players, "previous_minutes").fillna(0).clip(lower=0)

    has_current_sample = current_minutes > 0
    has_previous_sample = (previous_minutes > 0) & previous_rate.notna()
    observed = current_rate.where(has_current_sample)
    observed = observed.where(observed.notna(), previous_rate.where(has_previous_sample))
    # Last-resort rate context with zero evidence is retained only for audit. Its
    # posterior weight is zero, so it cannot overpower the group prior.
    observed = observed.where(observed.notna(), current_rate)
    sample_minutes = current_minutes.where(has_current_sample, previous_minutes)
    sample_minutes = sample_minutes.where(observed.notna(), 0.0).fillna(0.0)
    source = pd.Series("group_prior", index=players.index, dtype="string")
    source.loc[has_previous_sample] = "previous_season"
    source.loc[has_current_sample & current_rate.notna()] = "current_season"
    source.loc[(sample_minutes <= 0) & current_rate.notna()] = "context_no_minutes"
    return observed, sample_minutes, source


def _leave_one_out_prior(
    values: pd.Series,
    minutes: pd.Series,
    groups: pd.Series,
    *,
    min_group_players: int,
    min_group_minutes: float,
) -> pd.Series:
    """Minutes-weighted leave-one-out group mean with league fallback."""
    value = pd.to_numeric(values, errors="coerce")
    weight = pd.to_numeric(minutes, errors="coerce").fillna(0).clip(lower=0)
    valid = value.notna() & (weight > 0)
    weighted = value.fillna(0) * weight
    league_weight = float(weight[valid].sum())
    league_total = float(weighted[valid].sum())
    league_mean = league_total / league_weight if league_weight > 0 else 0.0

    frame = pd.DataFrame(
        {
            "group": groups.astype("string").fillna("UNKNOWN"),
            "value": value,
            "weight": weight,
            "weighted": weighted,
            "valid": valid.astype(int),
        },
        index=values.index,
    )
    totals = frame.groupby("group", dropna=False).agg(
        group_weight=("weight", "sum"),
        group_total=("weighted", "sum"),
        group_players=("valid", "sum"),
    )
    prior = pd.Series(league_mean, index=frame.index, dtype=float)
    for idx, row in frame.iterrows():
        group = row["group"]
        summary = totals.loc[group]
        own_weight = float(row["weight"]) if bool(row["valid"]) else 0.0
        own_total = float(row["weighted"]) if bool(row["valid"]) else 0.0
        remaining_weight = float(summary["group_weight"]) - own_weight
        remaining_total = float(summary["group_total"]) - own_total
        remaining_players = int(summary["group_players"]) - int(row["valid"])
        if (
            remaining_players >= int(min_group_players)
            and remaining_weight >= float(min_group_minutes)
        ):
            prior.loc[idx] = remaining_total / remaining_weight
    return prior.clip(lower=0)


def shrink_player_rates(
    players: pd.DataFrame,
    config: RateShrinkageConfig | None = None,
) -> pd.DataFrame:
    """Return empirical-Bayes shrunk xG90/xA90/DEFCON rates plus audit columns.

    The prior is a minutes-weighted leave-one-out position mean. A player's own
    observed rate receives weight ``minutes / (minutes + prior_minutes)``. Therefore
    established high-minute players retain most of their signal while low-minute or
    zero-minute context is pulled strongly toward the position prior.
    """
    cfg = config or RateShrinkageConfig()
    out = pd.DataFrame(index=players.index)
    groups = players.get(
        "position",
        pd.Series("UNKNOWN", index=players.index, dtype="string"),
    ).astype("string")

    for label, (current_col, previous_col) in RATE_COLUMNS.items():
        observed, sample_minutes, source = _evidence_rate(players, current_col, previous_col)
        prior = _leave_one_out_prior(
            observed,
            sample_minutes,
            groups,
            min_group_players=cfg.min_group_players,
            min_group_minutes=cfg.min_group_minutes,
        )
        k = max(float(cfg.prior_minutes.get(label, 0.0)), 0.0)
        reliability = np.divide(
            sample_minutes.to_numpy(float),
            sample_minutes.to_numpy(float) + k,
            out=np.ones(len(players), dtype=float) if k <= 0 else np.zeros(len(players), dtype=float),
            where=(sample_minutes.to_numpy(float) + k) > 0,
        )
        observed_values = pd.to_numeric(observed, errors="coerce").to_numpy(float)
        prior_values = prior.to_numpy(float)
        clean_observed = np.where(np.isfinite(observed_values), observed_values, prior_values)
        posterior = reliability * clean_observed + (1.0 - reliability) * prior_values

        out[f"raw_{label}"] = clean_observed
        out[f"prior_{label}"] = prior_values
        out[f"shrunk_{label}"] = np.clip(posterior, 0, None)
        out[f"{label}_evidence_minutes"] = sample_minutes.to_numpy(float)
        out[f"{label}_reliability"] = np.clip(reliability, 0, 1)
        out[f"{label}_evidence_source"] = source.to_numpy()

    return out
