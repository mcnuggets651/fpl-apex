from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EliteWeights:
    """Apex Elite 10.0 secondary-decision weights.

    Pinnacle ``xp`` remains the canonical forecast and primary optimisation target.
    Elite is used only after a maximum-xP reference has been established. The
    optimiser may then maximise this utility subject to retaining at least
    ``1 - max_ev_regret_fraction`` of the relevant maximum-xP objective.
    """

    attack: float = 0.35
    minutes: float = 0.20
    captaincy: float = 0.15
    set_pieces: float = 0.10
    fixture: float = 0.10
    bonus_defcon: float = 0.05
    value: float = 0.05
    max_ev_regret_fraction: float = 0.005

    def validate(self) -> None:
        values = [
            self.attack,
            self.minutes,
            self.captaincy,
            self.set_pieces,
            self.fixture,
            self.bonus_defcon,
            self.value,
        ]
        if any(v < 0 for v in values):
            raise ValueError("Elite weights must be non-negative")
        if not np.isclose(sum(values), 1.0, atol=1e-9):
            raise ValueError(f"Elite weights must sum to 1.0, got {sum(values):.6f}")
        if not 0.0 <= self.max_ev_regret_fraction <= 0.05:
            raise ValueError("Elite max_ev_regret_fraction must be between 0 and 5%")


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _optional_player_metric(players: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
    for col in candidates:
        if col in players.columns:
            return pd.to_numeric(players[col], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=players.index, dtype=float)


def _rank01(values: pd.Series, groups: pd.Series | None = None) -> pd.Series:
    clean = (
        pd.to_numeric(values, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    if groups is None:
        return clean.rank(method="average", pct=True).clip(0.0, 1.0)
    frame = pd.DataFrame({"value": clean, "group": groups.astype(str)})
    return (
        frame.groupby("group", dropna=False)["value"]
        .rank(method="average", pct=True)
        .clip(0.0, 1.0)
    )


def build_elite_projection_surface(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    weights: EliteWeights | None = None,
) -> pd.DataFrame:
    """Attach the Elite secondary utility to the canonical projection surface.

    This function does not alter ``xp`` and does not manufacture a second expected-
    points forecast. The 35/20/15/10/10/5/5 score exists only to rank solutions
    that already satisfy a strict raw-xP floor in the optimiser.
    """
    w = weights or EliteWeights()
    w.validate()
    if not {"player_id", "gw"}.issubset(projections.columns):
        raise ValueError("projections require player_id and gw")
    if "xp" not in projections.columns:
        raise ValueError("Elite scoring requires the Pinnacle ensemble xp column")

    player_cols = [
        c
        for c in [
            "player_id",
            "position",
            "price",
            "expected_minutes",
            "start_probability",
            "appearance_probability",
        ]
        if c in players.columns
    ]
    p = players.drop_duplicates("player_id")[player_cols].copy()
    extras = players.drop_duplicates("player_id")[["player_id"]].copy()
    base_players = players.drop_duplicates("player_id").reset_index(drop=True)
    extras["shots_signal"] = _optional_player_metric(
        base_players,
        ("shots_per_90", "total_shots_per_90", "shots", "total_shots"),
    ).to_numpy(float)
    extras["big_chances_signal"] = _optional_player_metric(
        base_players,
        ("big_chances_per_90", "big_chances", "big_chance_total"),
    ).to_numpy(float)
    p = p.merge(extras, on="player_id", how="left", validate="one_to_one")

    out = projections.copy().merge(p, on="player_id", how="left", validate="many_to_one")
    out["position"] = out.get("position", pd.Series("MID", index=out.index)).fillna("MID")
    out["price"] = _num(out, "price", 4.5).clip(lower=3.5)

    parts: list[pd.DataFrame] = []
    for _, d in out.groupby("gw", sort=True, dropna=False):
        d = d.copy()
        pos = d["position"].astype(str)

        attack = (
            0.55 * _rank01(_num(d, "xp_attack"), pos)
            + 0.20 * _rank01(_num(d, "model_xg90"), pos)
            + 0.10 * _rank01(_num(d, "model_xa90"), pos)
            + 0.10 * _rank01(_num(d, "shots_signal"), pos)
            + 0.05 * _rank01(_num(d, "big_chances_signal"), pos)
        )
        minutes = (
            0.50 * (_num(d, "expected_minutes") / 90.0).clip(0.0, 1.0)
            + 0.35 * _num(d, "start_probability").clip(0.0, 1.0)
            + 0.15 * _num(d, "appearance_probability").clip(0.0, 1.0)
        )
        captaincy = (
            0.65 * _rank01(_num(d, "xp"))
            + 0.35
            * _rank01(_num(d, "projection_ceiling_80", _num(d, "xp").mean()))
        )
        set_pieces = (
            0.60 * _num(d, "penalty_share").clip(0.0, 1.0)
            + 0.15 * _num(d, "corners_share").clip(0.0, 1.0)
            + 0.15 * _num(d, "direct_freekick_share").clip(0.0, 1.0)
            + 0.10 * _num(d, "indirect_freekick_share").clip(0.0, 1.0)
        )
        set_pieces = 0.75 * set_pieces + 0.25 * _rank01(
            _num(d, "xp_set_piece_prior"), pos
        )
        fixture = _rank01(_num(d, "xp_attack") + _num(d, "xp_clean_sheet"), pos)
        bonus_defcon = 0.50 * _rank01(_num(d, "xp_bonus_prior"), pos) + 0.50 * _rank01(
            _num(d, "xp_defensive_contribution"), pos
        )
        value = _rank01(_num(d, "xp") / d["price"].clip(lower=3.5), pos)

        elite_score = (
            w.attack * attack
            + w.minutes * minutes
            + w.captaincy * captaincy
            + w.set_pieces * set_pieces
            + w.fixture * fixture
            + w.bonus_defcon * bonus_defcon
            + w.value * value
        ).clip(0.0, 1.0)

        d["elite_attack_score"] = attack
        d["elite_minutes_score"] = minutes
        d["elite_captaincy_score"] = captaincy
        d["elite_set_piece_score"] = set_pieces
        d["elite_fixture_score"] = fixture
        d["elite_bonus_defcon_score"] = bonus_defcon
        d["elite_value_score"] = value
        d["elite_score"] = elite_score
        d["elite_weight_profile"] = "35/20/15/10/10/5/5; secondary under xP floor"
        parts.append(d)

    if not parts:
        return out.assign(
            elite_score=0.0,
            elite_weight_profile="35/20/15/10/10/5/5; secondary under xP floor",
        )
    return pd.concat(parts, ignore_index=True)
