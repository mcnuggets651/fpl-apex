from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from apex_fpl.data.team_mapping import canonical_team


@dataclass(frozen=True)
class TeamGoalConfig:
    half_life_days: float = 240.0
    prior_matches: float = 10.0
    min_expected_goals: float = 0.30
    max_expected_goals: float = 3.50


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    clean = pd.DataFrame({"value": values, "weight": weights}).dropna()
    if clean.empty or clean["weight"].sum() <= 0:
        return float("nan")
    return float(np.average(clean["value"], weights=clean["weight"]))


def build_team_ratings(
    matches: pd.DataFrame,
    current_teams: pd.DataFrame,
    *,
    as_of: pd.Timestamp | None = None,
    config: TeamGoalConfig | None = None,
) -> pd.DataFrame:
    """Create time-decayed, shrinkage-protected xG ratings for current EPL clubs."""
    cfg = config or TeamGoalConfig()
    required = {"date", "team_home", "team_away", "xg_home", "xg_away"}
    missing = sorted(required - set(matches.columns))
    if missing:
        raise ValueError(f"team-goal history missing columns: {missing}")
    if not {"id", "name"}.issubset(current_teams.columns):
        raise ValueError("current teams require official id and name")

    cutoff = as_of or pd.Timestamp.now(tz="UTC")
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    d = matches.copy()
    d["date"] = pd.to_datetime(d["date"], utc=True, errors="coerce")
    d = d[d["date"] < cutoff].dropna(subset=list(required)).copy()
    if d.empty:
        raise ValueError("team-goal history has no matches before evaluation timestamp")
    d["team_home"] = d["team_home"].map(canonical_team)
    d["team_away"] = d["team_away"].map(canonical_team)
    age_days = (cutoff - d["date"]).dt.total_seconds() / 86400.0
    d["weight"] = np.exp(-math.log(2.0) * age_days / cfg.half_life_days)

    league_home = _weighted_mean(pd.to_numeric(d["xg_home"], errors="coerce"), d["weight"])
    league_away = _weighted_mean(pd.to_numeric(d["xg_away"], errors="coerce"), d["weight"])
    if not np.isfinite(league_home) or not np.isfinite(league_away):
        raise ValueError("team-goal history produced invalid league xG baselines")

    rows: list[dict] = []
    for team in current_teams[["id", "name"]].itertuples(index=False):
        name = canonical_team(team.name)
        home = d[d["team_home"] == name]
        away = d[d["team_away"] == name]
        effective = float(home["weight"].sum() + away["weight"].sum())
        shrink = effective / (effective + cfg.prior_matches) if effective > 0 else 0.0

        raw_attack_home = _weighted_mean(home["xg_home"], home["weight"]) / league_home
        raw_defence_home = _weighted_mean(home["xg_away"], home["weight"]) / league_away
        raw_attack_away = _weighted_mean(away["xg_away"], away["weight"]) / league_away
        raw_defence_away = _weighted_mean(away["xg_home"], away["weight"]) / league_home

        def shrunk(raw: float) -> float:
            if not np.isfinite(raw):
                return 1.0
            return float(np.clip(1.0 + shrink * (raw - 1.0), 0.55, 1.65))

        rows.append(
            {
                "team": int(team.id),
                "team_name": str(team.name),
                "canonical_team_name": name,
                "attack_home": shrunk(raw_attack_home),
                "defence_home": shrunk(raw_defence_home),
                "attack_away": shrunk(raw_attack_away),
                "defence_away": shrunk(raw_defence_away),
                "effective_matches": effective,
                "evidence_confidence": float(np.clip(shrink, 0, 1)),
                "prior_type": "historical_xg" if effective > 0 else "promoted_league_average",
                "league_home_xg": league_home,
                "league_away_xg": league_away,
            }
        )
    return pd.DataFrame(rows).sort_values("team").reset_index(drop=True)


def build_team_goal_surface(
    fixtures: pd.DataFrame,
    ratings: pd.DataFrame,
    gameweeks: list[int],
    *,
    config: TeamGoalConfig | None = None,
) -> pd.DataFrame:
    """Build one team-side prior per immutable Official FPL fixture.

    ``fixture_id`` is the primary identity. Opponent/home fields remain descriptive
    attributes and must never be used as a substitute identity for double or
    rescheduled fixtures.
    """
    cfg = config or TeamGoalConfig()
    required_fixture_columns = {"id", "event", "team_h", "team_a"}
    missing = sorted(required_fixture_columns - set(fixtures.columns))
    if missing:
        raise ValueError("official fixtures missing columns: " + ", ".join(missing))
    fixture_ids = pd.to_numeric(fixtures["id"], errors="coerce")
    if fixture_ids.isna().any() or fixture_ids.astype(int).duplicated().any():
        raise ValueError("official fixtures require unique numeric fixture IDs")

    by_team = ratings.set_index("team")
    rows: list[dict] = []
    for fixture in fixtures[fixtures["event"].isin(gameweeks)].itertuples(index=False):
        fixture_id = int(fixture.id)
        home_id, away_id = int(fixture.team_h), int(fixture.team_a)
        gw = int(fixture.event)
        if home_id not in by_team.index or away_id not in by_team.index:
            raise ValueError(f"team-goal ratings missing fixture teams {home_id}/{away_id}")
        home, away = by_team.loc[home_id], by_team.loc[away_id]
        home_lambda = float(
            np.clip(
                home["league_home_xg"] * home["attack_home"] * away["defence_away"],
                cfg.min_expected_goals,
                cfg.max_expected_goals,
            )
        )
        away_lambda = float(
            np.clip(
                away["league_away_xg"] * away["attack_away"] * home["defence_home"],
                cfg.min_expected_goals,
                cfg.max_expected_goals,
            )
        )
        rows.extend(
            [
                {
                    "fixture_id": fixture_id,
                    "gw": gw,
                    "team": home_id,
                    "opponent": away_id,
                    "is_home": True,
                    "expected_team_goals": home_lambda,
                    "expected_goals_against": away_lambda,
                    "clean_sheet_prob": math.exp(-away_lambda),
                    "team_goal_source": "understat_time_decay_v1",
                },
                {
                    "fixture_id": fixture_id,
                    "gw": gw,
                    "team": away_id,
                    "opponent": home_id,
                    "is_home": False,
                    "expected_team_goals": away_lambda,
                    "expected_goals_against": home_lambda,
                    "clean_sheet_prob": math.exp(-home_lambda),
                    "team_goal_source": "understat_time_decay_v1",
                },
            ]
        )
    surface = pd.DataFrame(rows)
    if not surface.empty and surface.duplicated(["fixture_id", "team"]).any():
        raise ValueError("duplicate team-goal fixture-side rows")
    return surface
