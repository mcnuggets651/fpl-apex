#!/usr/bin/env python3
"""Export one genuine AIrsenal prediction tag into the Apex forecast contract.

Usage:
    python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv

`TAG` may be a literal AIrsenal prediction tag or `LATEST`.

Important identity rule: ``player_prediction.player_id`` is AIrsenal's internal
primary key, *not* the official FPL element ID. The exporter therefore joins the
``player`` table and emits ``player.fpl_api_id``. This prevents an internal
AIrsenal ID from ever being mistaken for a canonical FPL player ID.

AIrsenal does not persist a separate appearance-probability forecast. Its points
model does, however, integrate every forecast over a concrete recent-minutes
sample. Apex exports the marginals of that *same* sample rather than inferring
availability from xP. This keeps expected minutes, P(appearance) and P(60+) tied
to the model that generated the points forecast.

A multi-fixture Gameweek is intentionally different: AIrsenal reuses the same
minute sample per fixture but does not define a joint probability that the player
appears in at least one fixture. Apex therefore leaves Gameweek appearance
probabilities blank for multi-fixture rows so its contingency gate fails closed
instead of inventing an independence assumption.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sqlite3
import sys


def _latest_tag(db: sqlite3.Connection) -> str:
    row = db.execute(
        """
        SELECT tag
        FROM player_prediction
        WHERE tag IS NOT NULL AND tag != ''
        GROUP BY tag
        ORDER BY MAX(id) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise SystemExit("No AIrsenal prediction tags exist in the database")
    return str(row[0])


def minute_marginals(minutes: list[float] | tuple[float, ...]) -> tuple[float, float, float]:
    """Return the mean minutes and empirical appearance/60+ mass of a model sample."""
    values = [float(value) for value in minutes]
    if not values:
        raise ValueError("AIrsenal minute sample must not be empty")
    if any(not math.isfinite(value) or value < 0.0 or value > 90.0 for value in values):
        raise ValueError("AIrsenal minute sample contains a value outside [0, 90]")
    count = float(len(values))
    return (
        sum(values) / count,
        sum(value > 0.0 for value in values) / count,
        sum(value >= 60.0 for value in values) / count,
    )


def _load_model_minute_marginals(
    player_ids: set[int],
    gameweeks: list[int],
    fixture_counts: dict[tuple[int, int], int],
) -> dict[tuple[int, int], tuple[float, float | None, float | None]]:
    """Reconstruct the minute sample used by the pinned AIrsenal prediction model.

    This function is called inside the pinned AIrsenal virtual environment created
    by the production workflow. Imports are deliberately local so Apex's own test
    environment does not need AIrsenal installed.
    """
    if not gameweeks:
        raise ValueError("AIrsenal export has no predicted Gameweeks")

    from airsenal.framework.schema import session  # type: ignore[import-not-found]
    from airsenal.framework.season import CURRENT_SEASON  # type: ignore[import-not-found]
    from airsenal.framework.utils import (  # type: ignore[import-not-found]
        get_player_from_api_id,
        get_recent_minutes_for_player,
    )

    first_gameweek = min(gameweeks)
    sample_size = max(3, len(gameweeks))
    output: dict[tuple[int, int], tuple[float, float | None, float | None]] = {}

    for player_id in sorted(player_ids):
        player = get_player_from_api_id(player_id, dbsession=session)
        if player is None:
            raise RuntimeError(
                f"AIrsenal database cannot resolve official FPL id {player_id}"
            )
        minute_sample = get_recent_minutes_for_player(
            player,
            num_match_to_use=sample_size,
            season=CURRENT_SEASON,
            last_gw=first_gameweek - 1,
            dbsession=session,
        )
        expected_fixture_minutes, p_appearance, p_60 = minute_marginals(minute_sample)

        for gameweek in gameweeks:
            fixture_count = int(fixture_counts.get((player_id, gameweek), 0))
            if fixture_count < 1:
                raise RuntimeError(
                    "AIrsenal prediction row has no underlying fixture for "
                    f"official FPL id {player_id}, GW{gameweek}"
                )
            if player.is_injured_or_suspended(
                CURRENT_SEASON,
                first_gameweek,
                gameweek,
            ):
                output[(player_id, gameweek)] = (0.0, 0.0, 0.0)
                continue

            expected_minutes = expected_fixture_minutes * fixture_count
            if fixture_count == 1:
                output[(player_id, gameweek)] = (
                    expected_minutes,
                    p_appearance,
                    p_60,
                )
            else:
                # The per-fixture minute model has no joint no-show probability for
                # a double/triple Gameweek. Expected minutes remain additive, while
                # autosub/vice probability is intentionally withheld.
                output[(player_id, gameweek)] = (expected_minutes, None, None)

    return output


def _csv_optional(value: float | None) -> str | float:
    return "" if value is None else float(value)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv"
        )

    db_path, requested_tag, output = sys.argv[1:4]
    db = sqlite3.connect(db_path)
    try:
        tag = _latest_tag(db) if requested_tag.upper() == "LATEST" else requested_tag
        rows = db.execute(
            """
            SELECT
                p.fpl_api_id,
                f.gameweek,
                SUM(pp.predicted_points),
                COUNT(DISTINCT pp.fixture_id)
            FROM player_prediction AS pp
            JOIN player AS p ON p.player_id = pp.player_id
            JOIN fixture AS f ON f.fixture_id = pp.fixture_id
            WHERE pp.tag = ?
              AND f.gameweek IS NOT NULL
              AND p.fpl_api_id IS NOT NULL
            GROUP BY p.fpl_api_id, f.gameweek
            ORDER BY p.fpl_api_id, f.gameweek
            """,
            (tag,),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        raise SystemExit(f"No official-ID AIrsenal predictions found for tag {tag!r}")

    player_ids = {int(row[0]) for row in rows}
    gameweeks = sorted({int(row[1]) for row in rows})
    fixture_counts = {
        (int(player_id), int(gameweek)): int(n_fixtures)
        for player_id, gameweek, _xp, n_fixtures in rows
    }
    minute_model = _load_model_minute_marginals(
        player_ids,
        gameweeks,
        fixture_counts,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    source_version = os.getenv("AIRSENAL_SOURCE_VERSION", "")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                "gw",
                "xp",
                "expected_minutes",
                "p_appearance",
                "p_60",
                "generated_at",
                "source_version",
                "prediction_tag",
            ]
        )
        writer.writerows(
            (
                int(player_id),
                int(gameweek),
                float(xp),
                float(minute_model[(int(player_id), int(gameweek))][0]),
                _csv_optional(minute_model[(int(player_id), int(gameweek))][1]),
                _csv_optional(minute_model[(int(player_id), int(gameweek))][2]),
                generated_at,
                source_version,
                tag,
            )
            for player_id, gameweek, xp, _n_fixtures in rows
        )

    print(
        f"Exported {len(rows)} player-gameweek rows for {len(player_ids)} official FPL "
        f"players, GW={gameweeks}, tag={tag!r}, with AIrsenal minute marginals to {path}"
    )


if __name__ == "__main__":
    main()
