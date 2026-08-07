from __future__ import annotations

import math

import numpy as np
import pandas as pd

HOME_GOALS_BASELINE = 1.55
AWAY_GOALS_BASELINE = 1.25


def next_gameweeks(events: pd.DataFrame, horizon: int) -> list[int]:
    if events.empty:
        return list(range(1, horizon + 1))
    unfinished = events.loc[events["finished"] == False, "id"].tolist()  # noqa: E712
    if unfinished:
        start = int(min(unfinished))
    else:
        start = int(events["id"].max()) + 1
    return list(range(start, start + horizon))


def _median(teams: pd.DataFrame, col: str) -> float:
    if col not in teams:
        return max(float(pd.to_numeric(teams.get("strength", 1000), errors="coerce").median()), 1.0)
    return max(float(pd.to_numeric(teams[col], errors="coerce").median()), 1.0)


def fixture_multipliers(
    fixtures: pd.DataFrame, teams: pd.DataFrame, gameweeks: list[int]
) -> pd.DataFrame:
    """Create per-team/per-fixture attack and clean-sheet priors.

    Official FPL attack/defence strength ratings are normalised to the league
    median. A small Poisson-style score prior turns opponent attack strength into
    an interpretable clean-sheet probability rather than an arbitrary FDR score.
    """
    cols = [
        "team", "gw", "opponent", "is_home", "attack_multiplier",
        "defence_multiplier", "expected_team_goals", "expected_goals_against",
        "clean_sheet_prob",
    ]
    if fixtures.empty or teams.empty:
        return pd.DataFrame(columns=cols)

    strength = teams.set_index("id")
    med_ah = _median(teams, "strength_attack_home")
    med_dh = _median(teams, "strength_defence_home")
    med_aa = _median(teams, "strength_attack_away")
    med_da = _median(teams, "strength_defence_away")

    rows = []
    relevant = fixtures[fixtures["event"].isin(gameweeks)]
    for _, f in relevant.iterrows():
        home, away = int(f["team_h"]), int(f["team_a"])
        hrow, arow = strength.loc[home], strength.loc[away]
        h_att = float(hrow.get("strength_attack_home", hrow.get("strength", med_ah))) / med_ah
        h_def = float(hrow.get("strength_defence_home", hrow.get("strength", med_dh))) / med_dh
        a_att = float(arow.get("strength_attack_away", arow.get("strength", med_aa))) / med_aa
        a_def = float(arow.get("strength_defence_away", arow.get("strength", med_da))) / med_da

        home_lambda = float(np.clip(HOME_GOALS_BASELINE * h_att / max(a_def, 0.35), 0.45, 3.25))
        away_lambda = float(np.clip(AWAY_GOALS_BASELINE * a_att / max(h_def, 0.35), 0.35, 2.85))
        home_attack_mult = home_lambda / HOME_GOALS_BASELINE
        away_attack_mult = away_lambda / AWAY_GOALS_BASELINE
        home_cs = math.exp(-away_lambda)
        away_cs = math.exp(-home_lambda)

        rows.extend(
            [
                {
                    "team": home,
                    "gw": int(f["event"]),
                    "opponent": away,
                    "is_home": True,
                    "attack_multiplier": np.clip(home_attack_mult, 0.60, 1.55),
                    "defence_multiplier": np.clip(AWAY_GOALS_BASELINE / away_lambda, 0.60, 1.55),
                    "expected_team_goals": home_lambda,
                    "expected_goals_against": away_lambda,
                    "clean_sheet_prob": home_cs,
                },
                {
                    "team": away,
                    "gw": int(f["event"]),
                    "opponent": home,
                    "is_home": False,
                    "attack_multiplier": np.clip(away_attack_mult, 0.60, 1.55),
                    "defence_multiplier": np.clip(HOME_GOALS_BASELINE / home_lambda, 0.60, 1.55),
                    "expected_team_goals": away_lambda,
                    "expected_goals_against": home_lambda,
                    "clean_sheet_prob": away_cs,
                },
            ]
        )
    return pd.DataFrame(rows, columns=cols)
