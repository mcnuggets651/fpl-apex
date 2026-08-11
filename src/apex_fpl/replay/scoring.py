from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from apex_fpl.constants import XI_MAX, XI_MIN
from apex_fpl.replay.state import WeeklyAction


@dataclass(frozen=True)
class WeeklyScore:
    gameweek: int
    gross_points: int
    hit_cost: int
    net_points: int
    starters: tuple[int, ...]
    autosubs: tuple[tuple[int, int], ...]
    captain_scored: int
    captain_multiplier: int
    bench_points: int

    def to_dict(self) -> dict:
        return {
            "gameweek": self.gameweek,
            "gross_points": self.gross_points,
            "hit_cost": self.hit_cost,
            "net_points": self.net_points,
            "starters": list(self.starters),
            "autosubs": [
                {"player_out": player_out, "player_in": player_in}
                for player_out, player_in in self.autosubs
            ],
            "captain_scored": self.captain_scored,
            "captain_multiplier": self.captain_multiplier,
            "bench_points": self.bench_points,
        }


def _outcomes(frame: pd.DataFrame) -> dict[int, dict]:
    required = {"player_id", "position", "minutes", "total_points"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"outcome file missing columns: {missing}")
    data = frame[list(required)].copy()
    for column in ("player_id", "minutes", "total_points"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    grouped = data.groupby(["player_id", "position"], as_index=False).agg(
        minutes=("minutes", "sum"), total_points=("total_points", "sum")
    )
    return {int(row["player_id"]): row for row in grouped.to_dict("records")}


def _formation_legal(player_ids: set[int], outcomes: dict[int, dict]) -> bool:
    counts = Counter(str(outcomes[pid]["position"]) for pid in player_ids)
    return all(XI_MIN[pos] <= counts.get(pos, 0) <= XI_MAX[pos] for pos in XI_MIN)


def score_weekly_action(action: WeeklyAction, outcome_frame: pd.DataFrame) -> WeeklyScore:
    """Score a sealed action. This is the only boundary allowed to see outcomes."""
    outcomes = _outcomes(outcome_frame)
    missing = sorted(set(action.squad) - set(outcomes))
    if missing:
        raise ValueError(f"outcome file is missing submitted players: {missing}")
    minutes = {pid: int(outcomes[pid]["minutes"]) for pid in action.squad}
    points = {pid: int(outcomes[pid]["total_points"]) for pid in action.squad}

    submitted = set(action.xi)
    autosubs: list[tuple[int, int]] = []
    if action.chip != "bench_boost":
        active = {pid for pid in action.xi if minutes[pid] > 0}
        nominal = set(action.xi)
        missing_gk = [pid for pid in action.xi if outcomes[pid]["position"] == "GK" and minutes[pid] == 0]
        bench_gk = [pid for pid in action.bench_order if outcomes[pid]["position"] == "GK"]
        if missing_gk and bench_gk and minutes[bench_gk[0]] > 0:
            active.add(bench_gk[0])
            nominal.remove(missing_gk[0])
            nominal.add(bench_gk[0])
            autosubs.append((missing_gk[0], bench_gk[0]))

        missing_outfield = [
            pid for pid in action.xi
            if outcomes[pid]["position"] != "GK" and minutes[pid] == 0
        ]
        bench_outfield = [
            pid for pid in action.bench_order
            if outcomes[pid]["position"] != "GK" and minutes[pid] > 0
        ]
        for bench_player in bench_outfield:
            valid_out = next(
                (
                    player_out
                    for player_out in missing_outfield
                    if _formation_legal((nominal - {player_out}) | {bench_player}, outcomes)
                ),
                None,
            )
            if valid_out is not None:
                active.add(bench_player)
                nominal.remove(valid_out)
                nominal.add(bench_player)
                missing_outfield.remove(valid_out)
                autosubs.append((valid_out, bench_player))
        scored = active
    else:
        scored = set(action.squad)

    gross = sum(points[pid] for pid in scored)
    captain = action.captain_id if minutes[action.captain_id] > 0 else action.vice_captain_id
    captain_multiplier = 3 if action.chip == "triple_captain" else 2
    if minutes[captain] > 0:
        gross += points[captain] * (captain_multiplier - 1)
    else:
        captain_multiplier = 1
    bench_points = sum(points[pid] for pid in set(action.squad) - submitted)
    return WeeklyScore(
        gameweek=action.gameweek,
        gross_points=int(gross),
        hit_cost=int(action.hit_cost),
        net_points=int(gross - action.hit_cost),
        starters=tuple(sorted(scored)),
        autosubs=tuple(autosubs),
        captain_scored=int(captain),
        captain_multiplier=int(captain_multiplier),
        bench_points=int(bench_points),
    )
