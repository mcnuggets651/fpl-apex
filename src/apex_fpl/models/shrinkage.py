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
    """Equivalent-prior-minute strengths learned by no-hindsight validation.

    These defaults are provisional whenever the evidence resolver changes. The
    dedicated historical validation workflow refits them before production promotion.
    """

    prior_minutes: dict[str, float | dict[str, float]] = field(
        default_factory=lambda: {"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0}
    )
    min_group_players: int = 6
    min_group_minutes: float = 900.0


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _competitive_evidence(
    players: pd.DataFrame,
    current_col: str,
    previous_col: str,
) -> dict[str, pd.Series]:
    """Combine previous- and current-season competitive evidence continuously.

    Previous-season and current-season rates are converted back to event-equivalent
    totals, summed, then converted to one combined competitive rate. This avoids the
    GW1->GW2 evidence reset where a single current-season appearance would otherwise
    replace an established player's full previous-season track record.

    Preseason is intentionally excluded. It remains a separately capped signal in
    the projection layer because the shrinkage hyperparameters are calibrated on
    competitive Premier League evidence only.
    """
    current_rate = _numeric(players, current_col)
    previous_rate = _numeric(players, previous_col)
    current_minutes = _numeric(players, "minutes").fillna(0).clip(lower=0)
    previous_minutes = _numeric(players, "previous_minutes").fillna(0).clip(lower=0)

    current_valid = (current_minutes > 0) & current_rate.notna()
    previous_valid = (previous_minutes > 0) & previous_rate.notna()

    current_used = current_minutes.where(current_valid, 0.0)
    previous_used = previous_minutes.where(previous_valid, 0.0)
    effective_minutes = current_used + previous_used

    weighted_total = (
        current_rate.fillna(0.0) * current_used
        + previous_rate.fillna(0.0) * previous_used
    )
    combined_rate = weighted_total.div(effective_minutes.where(effective_minutes > 0))

    # A zero-minute current rate can still be useful as contextual metadata, but it
    # receives zero posterior evidence weight and therefore cannot overpower the prior.
    context_rate = current_rate.where(current_rate.notna(), previous_rate)
    observed = combined_rate.where(combined_rate.notna(), context_rate)

    source = pd.Series("group_prior", index=players.index, dtype="string")
    source.loc[previous_valid & ~current_valid] = "previous_season"
    source.loc[current_valid & ~previous_valid] = "current_season"
    source.loc[previous_valid & current_valid] = "previous_plus_current"
    source.loc[(effective_minutes <= 0) & context_rate.notna()] = "context_no_minutes"

    return {
        "observed": observed,
        "combined_rate": combined_rate,
        "effective_minutes": effective_minutes,
        "source": source,
        "previous_rate": previous_rate,
        "current_rate": current_rate,
        "previous_minutes": previous_used,
        "current_minutes": current_used,
    }


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
    """Return empirical-Bayes shrunk competitive rates plus full audit fields."""
    cfg = config or RateShrinkageConfig()
    out = pd.DataFrame(index=players.index)
    groups = players.get(
        "position",
        pd.Series("UNKNOWN", index=players.index, dtype="string"),
    ).astype("string")

    for label, (current_col, previous_col) in RATE_COLUMNS.items():
        evidence = _competitive_evidence(players, current_col, previous_col)
        observed = evidence["observed"]
        effective_minutes = evidence["effective_minutes"]
        prior = _leave_one_out_prior(
            observed,
            effective_minutes,
            groups,
            min_group_players=cfg.min_group_players,
            min_group_minutes=cfg.min_group_minutes,
        )
        configured_k = cfg.prior_minutes.get(label, 0.0)
        if isinstance(configured_k, dict):
            group_k = {
                str(group): max(float(value), 0.0)
                for group, value in configured_k.items()
            }
            fallback_k = group_k.get("DEFAULT", 0.0)
            k_values = (
                groups.map(group_k)
                .fillna(fallback_k)
                .astype(float)
                .clip(lower=0.0)
                .to_numpy()
            )
        else:
            k_values = np.full(
                len(players),
                max(float(configured_k), 0.0),
                dtype=float,
            )
        evidence_minutes = effective_minutes.to_numpy(float)
        denominator = evidence_minutes + k_values
        reliability = np.divide(
            evidence_minutes,
            denominator,
            out=np.where(k_values <= 0, 1.0, 0.0),
            where=denominator > 0,
        )
        observed_values = pd.to_numeric(observed, errors="coerce").to_numpy(float)
        prior_values = prior.to_numpy(float)
        clean_observed = np.where(np.isfinite(observed_values), observed_values, prior_values)
        posterior = reliability * clean_observed + (1.0 - reliability) * prior_values

        previous_rate = pd.to_numeric(evidence["previous_rate"], errors="coerce")
        current_rate = pd.to_numeric(evidence["current_rate"], errors="coerce")
        combined_rate = pd.to_numeric(evidence["combined_rate"], errors="coerce")

        out[f"raw_previous_{label}"] = previous_rate.to_numpy(float)
        out[f"raw_current_{label}"] = current_rate.to_numpy(float)
        out[f"combined_competitive_{label}"] = combined_rate.to_numpy(float)
        # Legacy raw_* remains the exact competitive rate fed into shrinkage.
        out[f"raw_{label}"] = clean_observed
        out[f"prior_{label}"] = prior_values
        out[f"shrunk_{label}"] = np.clip(posterior, 0, None)
        out[f"{label}_previous_evidence_minutes"] = evidence["previous_minutes"].to_numpy(float)
        out[f"{label}_current_evidence_minutes"] = evidence["current_minutes"].to_numpy(float)
        out[f"{label}_combined_effective_evidence_minutes"] = effective_minutes.to_numpy(float)
        # Backwards-compatible alias for existing diagnostics.
        out[f"{label}_evidence_minutes"] = effective_minutes.to_numpy(float)
        out[f"{label}_prior_minutes"] = k_values
        out[f"{label}_reliability"] = np.clip(reliability, 0, 1)
        out[f"{label}_evidence_source"] = evidence["source"].to_numpy()

    return out
