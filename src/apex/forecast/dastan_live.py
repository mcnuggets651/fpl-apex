from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


POSITION = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS_RISK = {"a": 0, "d": 1, "s": 2, "i": 3, "u": 4, "n": 4}

# Raw match-result inputs consumed only through shifted/rolling Dastan features. A live
# worker builds the target row twice with different markers and requires identical
# shipped model features before inference. If an upstream change ever lets these target
# placeholders leak into their own prediction, the worker fails closed.
PLAYER_OUTCOME_COLUMNS = (
    "minutes",
    "total_points",
    "influence",
    "creativity",
    "threat",
    "goals_scored",
    "penalties_missed",
    "assists",
    "goals_conceded",
    "own_goals",
    "saves",
    "penalties_saved",
    "yellow_cards",
    "red_cards",
    "bps",
    "bonus",
    "us_shots",
    "us_xG",
    "us_xGChain",
    "us_xGBuildup",
    "us_key_passes",
    "us_xA",
    "defensive_contribution",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
    "starts",
)


def target_gameweek(bootstrap: Mapping[str, Any], *, now: datetime | None = None) -> int:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    future = []
    for event in bootstrap.get("events", []):
        if event.get("id") is None or not event.get("deadline_time"):
            continue
        deadline = datetime.fromisoformat(str(event["deadline_time"]).replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline.astimezone(timezone.utc) > now:
            future.append(int(event["id"]))
    if not future:
        raise RuntimeError("Official FPL has no future deadline")
    return min(future)


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def mapping_by_fpl_code(rows: Iterable[Mapping[str, Any]]) -> dict[int, int]:
    out: dict[int, int] = {}
    for row in rows:
        raw = row.get("understat_id")
        if raw in (None, ""):
            continue
        if str(row.get("mapping_status", "mapped")).casefold() not in {
            "mapped",
            "shared_understat_id",
        }:
            continue
        code = int(row["fpl_code"])
        understat = int(float(raw))
        previous = out.get(code)
        if previous is not None and previous != understat:
            raise RuntimeError(f"stable FPL code {code} maps to multiple Understat IDs")
        out[code] = understat
    return out


def fixture_ids_by_team(fixtures: Iterable[Mapping[str, Any]], gameweek: int) -> dict[int, tuple[int, ...]]:
    by_team: dict[int, list[int]] = {}
    for fixture in fixtures:
        if fixture.get("event") is None or int(fixture["event"]) != int(gameweek):
            continue
        fixture_id = int(fixture["id"])
        for team in (int(fixture["team_h"]), int(fixture["team_a"])):
            by_team.setdefault(team, []).append(fixture_id)
    return {team: tuple(sorted(values)) for team, values in by_team.items()}


def build_target_player_rows(
    bootstrap: Mapping[str, Any],
    fixtures: Iterable[Mapping[str, Any]],
    *,
    gameweek: int,
    understat_by_code: Mapping[int, int],
    understat_name_by_fpl_team: Mapping[str, str],
    outcome_marker: float,
) -> pd.DataFrame:
    elements = list(bootstrap.get("elements", []))
    teams = {int(row["id"]): str(row["name"]) for row in bootstrap.get("teams", [])}
    total_players = int(_float(bootstrap.get("total_players"), 0.0))
    if total_players <= 0:
        raise RuntimeError("Official FPL bootstrap missing positive total_players")
    target_fixtures = [
        row
        for row in fixtures
        if row.get("event") is not None and int(row["event"]) == int(gameweek)
    ]
    by_team: dict[int, list[Mapping[str, Any]]] = {}
    for fixture in target_fixtures:
        if not fixture.get("kickoff_time"):
            raise RuntimeError(f"target fixture {fixture.get('id')} missing kickoff_time")
        by_team.setdefault(int(fixture["team_h"]), []).append(fixture)
        by_team.setdefault(int(fixture["team_a"]), []).append(fixture)

    rows: list[dict[str, Any]] = []
    for player in elements:
        element = int(player["id"])
        code = int(player["code"])
        team = int(player["team"])
        element_type = int(player["element_type"])
        if element_type not in POSITION:
            raise RuntimeError(f"unknown Official element_type {element_type} for {element}")
        selected_percent = _float(player.get("selected_by_percent"), 0.0)
        selected = total_players * selected_percent / 100.0
        for fixture in by_team.get(team, []):
            home = int(fixture["team_h"])
            away = int(fixture["team_a"])
            opponent = away if team == home else home
            opponent_name = teams[opponent]
            opponent_understat = understat_name_by_fpl_team.get(opponent_name)
            if not opponent_understat:
                raise RuntimeError(
                    f"target fixture {fixture.get('id')} missing Understat opponent identity "
                    f"for {opponent_name!r}"
                )
            row: dict[str, Any] = {
                "season": "2026-27",
                "gameweek": int(gameweek),
                "fixture": int(fixture["id"]),
                "fpl_code": code,
                "element": element,
                "player_name": str(player.get("web_name") or element),
                "position": POSITION[element_type],
                "team_name": teams[team],
                "opponent_team": opponent,
                "opponent_team_name": opponent_name,
                "us_opponent": opponent_understat,
                "kickoff_time": str(fixture["kickoff_time"]),
                "match_date": str(fixture["kickoff_time"])[:10],
                "is_home": bool(team == home),
                "understat_id": understat_by_code.get(code, np.nan),
                "expected_points_pre_deadline": _float(player.get("ep_next"), 0.0),
                "value": _float(player.get("now_cost"), 0.0),
                "selected": selected,
                "transfers_balance": _float(player.get("transfers_in_event"), 0.0)
                - _float(player.get("transfers_out_event"), 0.0),
            }
            for column in PLAYER_OUTCOME_COLUMNS:
                row[column] = float(outcome_marker)
            rows.append(row)
    return pd.DataFrame(rows)


def build_target_team_rows(
    bootstrap: Mapping[str, Any],
    fixtures: Iterable[Mapping[str, Any]],
    *,
    gameweek: int,
    understat_name_by_fpl_team: Mapping[str, str],
    sentinel_base: float,
) -> pd.DataFrame:
    teams = {int(row["id"]): str(row["name"]) for row in bootstrap.get("teams", [])}
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        if fixture.get("event") is None or int(fixture["event"]) != int(gameweek):
            continue
        fixture_id = int(fixture["id"])
        kickoff = fixture.get("kickoff_time")
        if not kickoff:
            raise RuntimeError(f"target fixture {fixture_id} missing kickoff_time")
        home_id, away_id = int(fixture["team_h"]), int(fixture["team_a"])
        home_name, away_name = teams[home_id], teams[away_id]
        home_understat = understat_name_by_fpl_team.get(home_name)
        away_understat = understat_name_by_fpl_team.get(away_name)
        if not home_understat or not away_understat:
            raise RuntimeError(
                f"target fixture {fixture_id} missing Understat club identity: "
                f"{home_name!r}->{home_understat!r}, {away_name!r}->{away_understat!r}"
            )
        token = float(sentinel_base) + fixture_id * 10.0
        home = {
            "season": "2026-27",
            "date": str(kickoff),
            "understat_team": home_understat,
            "is_home": 1.0,
            "scored": token + 1,
            "missed": token + 2,
            "xG": token + 3,
            "xGA": token + 4,
            "deep": token + 5,
            "deep_allowed": token + 6,
            "ppda_att": token + 7,
            "ppda_def": token + 8,
            "ppda_allowed_att": token + 9,
            "ppda_allowed_def": token + 10,
            "pts": 0.0,
        }
        away = {
            "season": "2026-27",
            "date": str(kickoff),
            "understat_team": away_understat,
            "is_home": 0.0,
            "scored": home["missed"],
            "missed": home["scored"],
            "xG": home["xGA"],
            "xGA": home["xG"],
            "deep": token + 15,
            "deep_allowed": token + 16,
            "ppda_att": token + 17,
            "ppda_def": token + 18,
            "ppda_allowed_att": token + 19,
            "ppda_allowed_def": token + 20,
            "pts": 0.0,
        }
        rows.extend((home, away))
    return pd.DataFrame(rows)


def add_live_snapshot_features(
    frame: pd.DataFrame,
    bootstrap: Mapping[str, Any],
    *,
    gameweek: int,
) -> pd.DataFrame:
    out = frame.copy()
    by_code = {int(row["code"]): row for row in bootstrap.get("elements", [])}
    if "ar_ep_next" not in out:
        out["ar_ep_next"] = -1.0
    if "sig_status_risk" not in out:
        out["sig_status_risk"] = -1.0
    if "sig_chance_playing" not in out:
        out["sig_chance_playing"] = -1.0
    if "sig_has_news" not in out:
        out["sig_has_news"] = -1.0
    mask = out["gameweek"].eq(int(gameweek)) & out["season"].eq("2026-27")
    for index, code in out.loc[mask, "fpl_code"].items():
        player = by_code.get(int(code))
        if player is None:
            continue
        chance = player.get("chance_of_playing_next_round")
        out.at[index, "ar_ep_next"] = (
            -1.0 if player.get("ep_next") in (None, "") else _float(player.get("ep_next"))
        )
        out.at[index, "sig_status_risk"] = STATUS_RISK.get(
            str(player.get("status") or "a"), 0
        )
        out.at[index, "sig_chance_playing"] = -1.0 if chance is None else _float(chance)
        out.at[index, "sig_has_news"] = float(bool(str(player.get("news") or "").strip()))
    return out


def assert_feature_invariance(
    left: pd.DataFrame,
    right: pd.DataFrame,
    feature_columns: list[str],
) -> None:
    """Prove synthetic future outcome placeholders cannot affect target model inputs."""
    key = ["fpl_code", "fixture"]
    if not left[key].equals(right[key]):
        raise RuntimeError("Dastan placeholder-invariance target keys differ")
    missing = sorted(
        (set(feature_columns) - set(left.columns))
        | (set(feature_columns) - set(right.columns))
    )
    if missing:
        raise RuntimeError(f"Dastan target frame missing shipped features: {missing[:10]}")
    bad: list[str] = []
    for column in feature_columns:
        a = pd.to_numeric(left[column], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(right[column], errors="coerce").to_numpy(dtype=float)
        if not np.allclose(a, b, rtol=0.0, atol=0.0, equal_nan=True):
            bad.append(column)
    if bad:
        raise RuntimeError(
            "future placeholder values leak into Dastan target features: "
            + ", ".join(bad[:20])
        )


def aggregate_prediction_rows(
    predicted: pd.DataFrame,
    bootstrap: Mapping[str, Any],
    fixtures: Iterable[Mapping[str, Any]],
    *,
    gameweek: int,
) -> list[dict[str, Any]]:
    fixture_by_team = fixture_ids_by_team(fixtures, gameweek)
    grouped = {int(element): rows for element, rows in predicted.groupby("element", sort=False)}
    results = []
    for player in bootstrap.get("elements", []):
        element = int(player["id"])
        team = int(player["team"])
        expected_fixtures = fixture_by_team.get(team, ())
        rows = grouped.get(element)
        if not expected_fixtures:
            results.append(
                {
                    "player_id": element,
                    "gameweek": int(gameweek),
                    "xp": 0.0,
                    "expected_minutes": 0.0,
                    "p_any": 0.0,
                    "p60": 0.0,
                    "coverage_status": "FORECAST",
                    "coverage_reason": "NO_OFFICIAL_FIXTURE",
                }
            )
            continue
        if rows is None or len(rows) != len(expected_fixtures):
            results.append(
                {
                    "player_id": element,
                    "gameweek": int(gameweek),
                    "xp": None,
                    "expected_minutes": None,
                    "p_any": None,
                    "p60": None,
                    "coverage_status": "NO_FORECAST",
                    "coverage_reason": "DASTAN_TARGET_FIXTURE_COVERAGE_MISMATCH",
                }
            )
            continue
        p_any = 1.0 - float(np.prod(1.0 - rows["p_any"].clip(0.0, 1.0).to_numpy()))
        p60 = 1.0 - float(np.prod(1.0 - rows["p60"].clip(0.0, 1.0).to_numpy()))
        results.append(
            {
                "player_id": element,
                "gameweek": int(gameweek),
                "xp": float(rows["xpts"].sum()),
                "expected_minutes": float(rows["expected_minutes"].sum()),
                "p_any": p_any,
                "p60": p60,
                "coverage_status": "FORECAST",
                "coverage_reason": "",
            }
        )
    return results
