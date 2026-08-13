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
        return max(
            float(pd.to_numeric(teams.get("strength", 1000), errors="coerce").median()),
            1.0,
        )
    return max(float(pd.to_numeric(teams[col], errors="coerce").median()), 1.0)


def _elo_lookup(core_elos: pd.DataFrame | None) -> dict[tuple[int, int, int, bool], tuple[float, float]]:
    if core_elos is None or core_elos.empty:
        return {}
    required = {"gw", "team", "opponent", "is_home", "team_elo", "opponent_elo"}
    if not required.issubset(core_elos.columns):
        return {}
    lookup: dict[tuple[int, int, int, bool], tuple[float, float]] = {}
    for _, row in core_elos.iterrows():
        values = [row.get("gw"), row.get("team"), row.get("opponent"), row.get("team_elo"), row.get("opponent_elo")]
        if any(pd.isna(value) for value in values):
            continue
        lookup[
            (
                int(row["gw"]),
                int(row["team"]),
                int(row["opponent"]),
                bool(row["is_home"]),
            )
        ] = (float(row["team_elo"]), float(row["opponent_elo"]))
    return lookup


def fixture_multipliers(
    fixtures: pd.DataFrame,
    teams: pd.DataFrame,
    gameweeks: list[int],
    core_elos: pd.DataFrame | None = None,
    use_official_strength: bool | None = None,
    team_goal_surface: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create per-team/per-fixture attack, defence and clean-sheet priors.

    Official FPL home/away attack/defence ratings remain the base when they are
    usable. Reconciled FPL Core Elo is a deliberately modest fallback adjustment
    to that native/neutral goal surface. A validated external team-goal surface is
    already a complete expected-goals model, so Elo is not multiplied into it;
    any Understat/Elo hybrid must be explicitly calibrated and constructed as its
    own surface rather than created accidentally by double-counting evidence.
    """
    cols = [
        "team",
        "gw",
        "opponent",
        "is_home",
        "attack_multiplier",
        "defence_multiplier",
        "expected_team_goals",
        "expected_goals_against",
        "clean_sheet_prob",
        "team_elo",
        "opponent_elo",
        "elo_multiplier",
        "team_goal_source",
    ]
    if fixtures.empty or teams.empty:
        return pd.DataFrame(columns=cols)

    strength = teams.set_index("id")
    strength_columns = [
        "strength_attack_home",
        "strength_defence_home",
        "strength_attack_away",
        "strength_defence_away",
    ]
    if use_official_strength is None:
        if all(col in teams.columns for col in strength_columns):
            values = teams[strength_columns].apply(pd.to_numeric, errors="coerce")
            use_official_strength = bool(
                values.notna().all().all()
                and (values > 0).all().all()
                and ((values.max() - values.min()) > 0).all()
            )
        else:
            use_official_strength = False
    med_ah = _median(teams, "strength_attack_home")
    med_dh = _median(teams, "strength_defence_home")
    med_aa = _median(teams, "strength_attack_away")
    med_da = _median(teams, "strength_defence_away")
    elo = _elo_lookup(core_elos)
    team_goals: dict[tuple[int, int, int, bool], dict] = {}
    if team_goal_surface is not None and not team_goal_surface.empty:
        required = {
            "gw",
            "team",
            "opponent",
            "is_home",
            "expected_team_goals",
            "expected_goals_against",
            "clean_sheet_prob",
        }
        if not required.issubset(team_goal_surface.columns):
            raise ValueError(
                "team goal surface missing columns: "
                f"{sorted(required - set(team_goal_surface.columns))}"
            )
        for prior in team_goal_surface.to_dict("records"):
            key = (
                int(prior["gw"]),
                int(prior["team"]),
                int(prior["opponent"]),
                bool(prior["is_home"]),
            )
            if key in team_goals:
                raise ValueError(f"duplicate team-goal prior: {key}")
            team_goals[key] = prior

    rows = []
    relevant = fixtures[fixtures["event"].isin(gameweeks)]
    for _, fixture in relevant.iterrows():
        home, away = int(fixture["team_h"]), int(fixture["team_a"])
        gw = int(fixture["event"])
        hrow, arow = strength.loc[home], strength.loc[away]
        if use_official_strength:
            h_att = float(
                hrow.get("strength_attack_home", hrow.get("strength", med_ah))
            ) / med_ah
            h_def = float(
                hrow.get("strength_defence_home", hrow.get("strength", med_dh))
            ) / med_dh
            a_att = float(
                arow.get("strength_attack_away", arow.get("strength", med_aa))
            ) / med_aa
            a_def = float(
                arow.get("strength_defence_away", arow.get("strength", med_da))
            ) / med_da
        else:
            # Official FPL commonly publishes zeroed/non-informative strength
            # fields before GW1. Treating those zeroes as genuine ratings pushes
            # every expected-goals value into its lower clip and manufactures
            # inflated clean-sheet probabilities. Neutral league baselines are an
            # explicit fallback; reconciled Elo can still differentiate teams.
            h_att = h_def = a_att = a_def = 1.0

        home_prior = team_goals.get((gw, home, away, True))
        away_prior = team_goals.get((gw, away, home, False))
        external_surface = home_prior is not None and away_prior is not None
        if external_surface:
            home_lambda = float(home_prior["expected_team_goals"])
            away_lambda = float(away_prior["expected_team_goals"])
            team_goal_source = str(
                home_prior.get("team_goal_source") or "external_team_goal_surface"
            )
        else:
            home_lambda = float(
                np.clip(HOME_GOALS_BASELINE * h_att / max(a_def, 0.35), 0.45, 3.25)
            )
            away_lambda = float(
                np.clip(AWAY_GOALS_BASELINE * a_att / max(h_def, 0.35), 0.35, 2.85)
            )
            team_goal_source = (
                "official_fpl_strength" if use_official_strength else "league_average_fallback"
            )

        home_elo, away_elo = np.nan, np.nan
        home_elo_mult, away_elo_mult = 1.0, 1.0
        found = elo.get((gw, home, away, True))
        if found and not external_surface:
            home_elo, away_elo = found
            # Elo is useful independent evidence, but should not dominate the
            # native/neutral fixture prior. The 0.45 exponent shrinks the factor.
            raw = float(np.clip(math.exp((home_elo - away_elo) / 1200.0), 0.72, 1.38))
            home_elo_mult = raw**0.45
            away_elo_mult = (1.0 / raw) ** 0.45
            home_lambda *= home_elo_mult
            away_lambda *= away_elo_mult
            home_lambda = float(np.clip(home_lambda, 0.40, 3.35))
            away_lambda = float(np.clip(away_lambda, 0.30, 2.95))

        home_attack_mult = home_lambda / HOME_GOALS_BASELINE
        away_attack_mult = away_lambda / AWAY_GOALS_BASELINE
        home_cs = math.exp(-away_lambda)
        away_cs = math.exp(-home_lambda)

        rows.extend(
            [
                {
                    "team": home,
                    "gw": gw,
                    "opponent": away,
                    "is_home": True,
                    "attack_multiplier": np.clip(home_attack_mult, 0.55, 1.65),
                    "defence_multiplier": np.clip(
                        AWAY_GOALS_BASELINE / away_lambda, 0.55, 1.65
                    ),
                    "expected_team_goals": home_lambda,
                    "expected_goals_against": away_lambda,
                    "clean_sheet_prob": home_cs,
                    "team_elo": home_elo,
                    "opponent_elo": away_elo,
                    "elo_multiplier": home_elo_mult,
                    "team_goal_source": team_goal_source,
                },
                {
                    "team": away,
                    "gw": gw,
                    "opponent": home,
                    "is_home": False,
                    "attack_multiplier": np.clip(away_attack_mult, 0.55, 1.65),
                    "defence_multiplier": np.clip(
                        HOME_GOALS_BASELINE / home_lambda, 0.55, 1.65
                    ),
                    "expected_team_goals": away_lambda,
                    "expected_goals_against": home_lambda,
                    "clean_sheet_prob": away_cs,
                    "team_elo": away_elo,
                    "opponent_elo": home_elo,
                    "elo_multiplier": away_elo_mult,
                    "team_goal_source": team_goal_source,
                },
            ]
        )
    return pd.DataFrame(rows, columns=cols)
