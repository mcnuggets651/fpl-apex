"""Versioned Fantasy Premier League rules used by live and replay engines.

Historical replay must not silently apply the current season's transitions to an
older season.  Keep the compatibility constants below, but route stateful rules
through :func:`season_rules`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonRules:
    season: str
    max_rolled_free_transfers: int = 5
    initial_free_transfers: int = 0
    first_post_deadline_free_transfers: int = 1
    first_half_end_gw: int = 19
    transfer_hit_cost: float = 4.0
    free_transfer_top_ups: tuple[tuple[int, int], ...] = ()

    def top_up_for_gameweek(self, gameweek: int) -> int | None:
        return dict(self.free_transfer_top_ups).get(int(gameweek))


_SEASON_RULES = {
    "2025-2026": SeasonRules(
        season="2025-2026",
        # After the GW15 deadline all managers were topped up to five free
        # transfers for GW16 to accommodate AFCON departures.
        free_transfer_top_ups=((16, 5),),
    ),
    "2026-2027": SeasonRules(season="2026-2027"),
}


def _normalise_season(value: str) -> str:
    text = str(value).strip().replace("/", "-")
    if len(text) == 7 and text[4] == "-":
        start = int(text[:4])
        return f"{start:04d}-{start // 100 * 100 + int(text[5:]):04d}"
    return text


def season_rules(season: str) -> SeasonRules:
    key = _normalise_season(season)
    if key not in _SEASON_RULES:
        raise ValueError(f"unsupported FPL season rules: {season}")
    return _SEASON_RULES[key]

BUDGET_MILLIONS = 100.0
SQUAD_SIZE = 15
STARTING_XI_SIZE = 11
MAX_PER_TEAM = 3
MAX_ROLLED_FREE_TRANSFERS = _SEASON_RULES["2026-2027"].max_rolled_free_transfers
TRANSFER_HIT_COST = _SEASON_RULES["2026-2027"].transfer_hit_cost

# Two sets: one before the GW19 deadline and one from GW20 onward.
CHIPS_PER_HALF = {"wildcard": 1, "free_hit": 1, "triple_captain": 1, "bench_boost": 1}

# Defensive contribution thresholds. Goalkeepers do not earn DC points.
DEFENSIVE_CONTRIBUTION_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}
DEFENSIVE_CONTRIBUTION_POINTS = 2.0
