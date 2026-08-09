from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


CANDIDATE_ATTACK_PRIOR_MINUTES: dict[str, dict[str, float]] = {
    "xg90": {
        "DEFAULT": 360.0,
        "GK": 2400.0,
        "DEF": 1200.0,
        "MID": 180.0,
        "FWD": 720.0,
    },
    "xa90": {
        "DEFAULT": 360.0,
        "GK": 2400.0,
        "DEF": 180.0,
        "MID": 360.0,
        "FWD": 540.0,
    },
}


RATE_COLUMNS = {
    "xg90": ("expected_goals_per_90", "previous_expected_goals_per_90"),
    "xa90": ("expected_assists_per_90", "previous_expected_assists_per_90"),
    "defcon90": (
        "defensive_contribution_per_90",
        "previous_defensive_contribution_per_90",
    ),
}


def position_price_tier_groups(
    players: pd.DataFrame,
    *,
    price_column: str | None = None,
) -> pd.Series:
    """Return deterministic position-by-live-price-tercile prior groups.

    The validator uses this helper. Any future production integration must call
    the same function so cohort construction cannot drift between the two paths.
    """
    positions = players.get(
        "position",
        pd.Series("UNKNOWN", index=players.index, dtype="string"),
    ).astype("string")
    candidates = (
        [price_column]
        if price_column is not None
        else ["price", "now_cost", "price_value"]
    )
    selected = next(
        (column for column in candidates if column and column in players.columns),
        None,
    )
    if selected is None:
        return positions
    live_price = pd.to_numeric(players[selected], errors="coerce")
    if not live_price.notna().any():
        return positions
    price_rank = (
        live_price.groupby(positions)
        .rank(method="average", pct=True)
        .fillna(0.5)
    )
    price_tier = pd.cut(
        price_rank,
        bins=[-np.inf, 1 / 3, 2 / 3, np.inf],
        labels=["LOW", "MID", "HIGH"],
    ).astype("string")
    return positions + "|" + price_tier


@dataclass(frozen=True)
class RateShrinkageConfig:
    """Candidate equivalent-prior-minute strengths for shadow evaluation.

    These defaults are provisional whenever the evidence resolver changes. The
    dedicated historical validation workflow refits them. Historical pass status alone
    does not authorise production promotion because the evaluation seasons have been
    inspected during development.
    """

    prior_minutes: dict[str, float | dict[str, float]] = field(
        default_factory=lambda: {
            "xg90": dict(CANDIDATE_ATTACK_PRIOR_MINUTES["xg90"]),
            "xa90": dict(CANDIDATE_ATTACK_PRIOR_MINUTES["xa90"]),
            # DEFCON failed the evidence gate and is therefore a no-op by default.
            "defcon90": 0.0,
        }
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
    positions: pd.Series,
    *,
    min_group_players: int,
    min_group_minutes: float,
) -> tuple[pd.Series, pd.Series]:
    """Hierarchical leave-one-out prior: tier, then position, then league.

    Every fallback excludes the target player's own evidence.  This matters for
    sparse price tiers and positions: falling back to a league mean that still
    contains the target lets a low-minute outlier partially define its own prior.
    """
    value = pd.to_numeric(values, errors="coerce")
    weight = pd.to_numeric(minutes, errors="coerce").fillna(0).clip(lower=0)
    valid = value.notna() & (weight > 0)
    weighted = value.fillna(0) * weight
    league_weight = float(weight[valid].sum())
    league_total = float(weighted[valid].sum())

    frame = pd.DataFrame(
        {
            "group": groups.astype("string").fillna("UNKNOWN"),
            "position": positions.astype("string").fillna("UNKNOWN"),
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
    position_totals = frame.groupby("position", dropna=False).agg(
        group_weight=("weight", "sum"),
        group_total=("weighted", "sum"),
        group_players=("valid", "sum"),
    )
    own_weight = frame["weight"].where(frame["valid"].eq(1), 0.0)
    own_total = frame["weighted"].where(frame["valid"].eq(1), 0.0)
    own_player = frame["valid"]

    league_remaining_weight = league_weight - own_weight
    league_remaining_total = league_total - own_total
    prior = league_remaining_total.div(
        league_remaining_weight.where(league_remaining_weight > 0)
    ).fillna(0.0)
    level = pd.Series("league", index=frame.index, dtype="string")

    for fallback_level, key, summary in (
        ("position", "position", position_totals),
        ("group", "group", totals),
    ):
        remaining_weight = frame[key].map(summary["group_weight"]) - own_weight
        remaining_total = frame[key].map(summary["group_total"]) - own_total
        remaining_players = frame[key].map(summary["group_players"]) - own_player
        eligible = (
            remaining_players.ge(int(min_group_players))
            & remaining_weight.ge(float(min_group_minutes))
            & remaining_weight.gt(0)
        )
        prior.loc[eligible] = (
            remaining_total.loc[eligible] / remaining_weight.loc[eligible]
        )
        level.loc[eligible] = fallback_level

    return prior.clip(lower=0), level


def shrink_player_rates(
    players: pd.DataFrame,
    config: RateShrinkageConfig | None = None,
) -> pd.DataFrame:
    """Return empirical-Bayes shrunk competitive rates plus full audit fields."""
    cfg = config or RateShrinkageConfig()
    out = pd.DataFrame(index=players.index)
    positions = players.get(
        "position",
        pd.Series("UNKNOWN", index=players.index, dtype="string"),
    ).astype("string")
    groups = players.get("shrinkage_group", positions).astype("string")

    for label, (current_col, previous_col) in RATE_COLUMNS.items():
        evidence = _competitive_evidence(players, current_col, previous_col)
        observed = evidence["observed"]
        effective_minutes = evidence["effective_minutes"]
        prior, prior_level = _leave_one_out_prior(
            observed,
            effective_minutes,
            groups,
            positions,
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
                positions.map(group_k)
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
        out[f"prior_{label}_level"] = prior_level.to_numpy()
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
