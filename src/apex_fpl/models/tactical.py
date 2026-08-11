from __future__ import annotations

import numpy as np
import pandas as pd


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _optional_num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _blend_observed_rate(
    primary: pd.Series, preseason: pd.Series, preseason_minutes: pd.Series
) -> pd.Series:
    base = pd.to_numeric(primary, errors="coerce").fillna(0.0)
    observed = pd.to_numeric(preseason, errors="coerce")
    weight = (
        np.clip(pd.to_numeric(preseason_minutes, errors="coerce").fillna(0.0) / 270.0, 0.0, 0.35)
        * observed.notna().astype(float)
    )
    return base * (1.0 - weight) + observed.fillna(0.0) * weight


def _per90(total: pd.Series, minutes: pd.Series) -> pd.Series:
    return total * 90.0 / np.maximum(minutes, 90.0)


def infer_tactical_roles(players: pd.DataFrame) -> pd.DataFrame:
    """Infer a conservative FPL-relevant tactical role from current/preseason data.

    This is not a formation-tracking oracle. It converts observable involvement
    (xG/xA, box touches, chance creation, crossing and defensive work) into a small
    role prior that can be overridden by verified manager/line-up evidence. The
    output uses ``inferred_*`` columns so it can never overwrite a manual verified
    tactical role silently.
    """
    if players.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "inferred_tactical_role",
                "inferred_role_multiplier",
                "inferred_role_confidence",
                "tactical_attack_index",
                "tactical_defence_index",
            ]
        )

    d = players.copy()
    minutes = _num(d, "minutes", 0.0)
    preseason_minutes = _num(d, "preseason_minutes", 0.0)

    xg90 = _num(d, "expected_goals_per_90", 0.0)
    xa90 = _num(d, "expected_assists_per_90", 0.0)
    xg90 = _blend_observed_rate(xg90, _optional_num(d, "preseason_xg90"), preseason_minutes)
    xa90 = _blend_observed_rate(xa90, _optional_num(d, "preseason_xa90"), preseason_minutes)

    box90 = _per90(_num(d, "touches_opposition_box", 0.0), minutes)
    chances90 = _per90(_num(d, "chances_created", 0.0), minutes)
    crosses90 = _per90(_num(d, "accurate_crosses", 0.0), minutes)
    defensive90 = _num(d, "defensive_contribution_per_90", 0.0)
    defensive90 = _blend_observed_rate(
        defensive90, _optional_num(d, "preseason_defcon90"), preseason_minutes
    )

    attack_index = (
        1.45 * xg90
        + 1.15 * xa90
        + 0.085 * box90
        + 0.18 * chances90
        + 0.10 * crosses90
    )
    defence_index = defensive90 / 12.0

    evidence_minutes = np.maximum(minutes, preseason_minutes)
    evidence = np.clip(evidence_minutes / 900.0, 0.0, 1.0)
    role = []
    multiplier = []
    confidence = []

    for idx, row in d.iterrows():
        pos = str(row.get("position", ""))
        attack = float(attack_index.loc[idx])
        defence = float(defence_index.loc[idx])
        gx = float(xg90.loc[idx])
        ax = float(xa90.loc[idx])
        sample = float(evidence.loc[idx])

        if pos == "GK":
            label, mult, margin = "goalkeeper", 1.00, 1.0
        elif pos == "DEF":
            if attack >= 1.00 or (ax >= 0.18 and float(crosses90.loc[idx]) >= 1.0):
                label, mult, margin = "attacking full-back / wing-back", 1.08, min(1.0, attack)
            elif attack >= 0.52:
                label, mult, margin = "progressive / balanced defender", 1.03, min(1.0, attack)
            else:
                label, mult, margin = "central / defensive defender", 0.98, min(1.0, max(defence, 0.35))
        elif pos == "MID":
            if attack >= 1.15 or gx >= 0.36:
                label, mult, margin = "advanced midfielder / winger", 1.07, min(1.0, attack)
            elif defence >= 0.78 and attack < 0.62:
                label, mult, margin = "holding / defensive midfielder", 0.93, min(1.0, defence)
            elif ax >= max(0.18, gx * 1.30):
                label, mult, margin = "creative midfielder", 1.04, min(1.0, 0.5 + ax)
            else:
                label, mult, margin = "central / balanced midfielder", 1.00, 0.5
        elif pos == "FWD":
            if gx >= 0.42 and gx >= ax * 1.35:
                label, mult, margin = "central striker", 1.05, min(1.0, 0.5 + gx)
            elif ax >= 0.20 and attack >= 0.75:
                label, mult, margin = "wide / creative forward", 1.02, min(1.0, attack)
            else:
                label, mult, margin = "forward", 1.00, 0.45
        else:
            label, mult, margin = "unknown", 1.00, 0.2

        # Automated role inference is deliberately capped below verified manual
        # evidence. A large sample and clear involvement profile increase confidence.
        conf = float(np.clip(0.42 + 0.26 * sample + 0.12 * margin, 0.40, 0.80))
        role.append(label)
        multiplier.append(mult)
        confidence.append(conf)

    return pd.DataFrame(
        {
            "player_id": pd.to_numeric(d["player_id"], errors="raise").astype(int),
            "inferred_tactical_role": role,
            "inferred_role_multiplier": multiplier,
            "inferred_role_confidence": confidence,
            "tactical_attack_index": np.asarray(attack_index, dtype=float),
            "tactical_defence_index": np.asarray(defence_index, dtype=float),
        }
    )
