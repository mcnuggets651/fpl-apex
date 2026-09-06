from __future__ import annotations

from typing import Any

from apex.domain.models import (
    CoverageStatus,
    OfficialFixture,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    TeamState,
)


def _strict_bool(value: Any, *, field: str, default: bool | None = None) -> bool:
    if value is None and default is not None:
        return default
    if type(value) is not bool:
        raise ValueError(f"{field} must be an explicit boolean")
    return value


def official_from_dict(data):
    players = tuple(
        OfficialPlayer(
            int(player["element_id"]),
            player["web_name"],
            int(player["team_id"]),
            Position(player["position"]),
            int(player["price_tenths"]),
            player["status"],
            _strict_bool(
                player.get("can_transact"),
                field=f"player {player['element_id']} can_transact",
                default=True,
            ),
            (
                int(player["fpl_code"])
                if player.get("fpl_code") is not None
                else None
            ),
        )
        for player in data["players"]
    )
    fixtures = tuple(
        OfficialFixture(
            int(fixture["fixture_id"]),
            (
                int(fixture["gameweek"])
                if fixture.get("gameweek") is not None
                else None
            ),
            int(fixture["home_team_id"]),
            int(fixture["away_team_id"]),
            fixture.get("kickoff_time"),
        )
        for fixture in data.get("fixtures", [])
    )
    return OfficialSnapshot(
        int(data["schema_version"]),
        data["season"],
        data["acquired_at"],
        data["source_hash"],
        players,
        fixtures,
        {int(key): value for key, value in data.get("deadlines", {}).items()},
    )


def projection_from_dict(data):
    rows = tuple(
        ProjectionRow(
            int(row["element_id"]),
            int(row["gameweek"]),
            int(row["horizon"]),
            (
                float(row["expected_points"])
                if row.get("expected_points") is not None
                else None
            ),
            tuple(map(int, row.get("fixture_ids", []))),
            int(row.get("n_fixtures", 0)),
            row.get("player_status_at_forecast"),
            (
                float(row["expected_minutes"])
                if row.get("expected_minutes") is not None
                else None
            ),
            (
                float(row["p_appearance"])
                if row.get("p_appearance") is not None
                else None
            ),
            float(row["p_start"]) if row.get("p_start") is not None else None,
            float(row["p_60"]) if row.get("p_60") is not None else None,
            CoverageStatus(row.get("coverage_status", "FORECAST")),
            row.get("coverage_reason"),
            row.get("metadata", {}),
        )
        for row in data["rows"]
    )
    return ProjectionSurface(
        int(data["schema_version"]),
        data["provider_id"],
        data["provider_version"],
        data["generated_at"],
        data["season"],
        data["source_snapshot"],
        data["scoring_rules_version"],
        tuple(map(int, data["supported_horizons"])),
        tuple(data.get("runtime_dependencies", [])),
        rows,
    )


def team_from_dict(data):
    return TeamState(
        int(data["schema_version"]),
        int(data["entry_id"]),
        int(data["published_gw"]),
        tuple(map(int, data["squad_ids"])),
        int(data["bank_tenths"]),
        int(data["free_transfers"]),
        {
            int(key): int(value)
            for key, value in data.get("purchase_prices_tenths", {}).items()
        },
        {
            int(key): int(value)
            for key, value in data.get("selling_prices_tenths", {}).items()
        },
        data.get("active_chip"),
        _strict_bool(
            data.get("state_complete_for_transfers"),
            field="state_complete_for_transfers",
            default=False,
        ),
    )
