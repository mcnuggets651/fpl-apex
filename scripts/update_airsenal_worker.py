#!/usr/bin/env python3
"""Update a pinned AIrsenal database for forecasting without manager-team state.

AIrsenal's public ``airsenal_update_db`` CLI also updates the configured FPL
manager's transfer history. That is useful when AIrsenal itself is managing a
specific team, but it is irrelevant to Apex's independent player forecast worker
and would make the worker depend on an arbitrary public team ID after GW1.

Run this script *inside the pinned AIrsenal environment*. It reuses the exact
upstream update functions for players, attributes, fixtures, results and player
scores while deliberately skipping only ``update_transactions``.
"""
from __future__ import annotations

from airsenal.framework.schema import database_is_empty, session_scope
from airsenal.framework.utils import CURRENT_SEASON
from airsenal.scripts.fill_fixture_table import fill_fixtures_from_api
from airsenal.scripts.update_db import update_attributes, update_players, update_results


def main() -> None:
    with session_scope() as session:
        if database_is_empty(session):
            raise SystemExit("AIrsenal database is empty; run airsenal_setup_initial_db first")

        new_players = update_players(CURRENT_SEASON, session)
        # Keep the same upstream behaviour: new players require current attributes,
        # and otherwise refresh attributes on every worker run for current price,
        # team, FPL position and availability context inside the forecast model.
        update_attributes(CURRENT_SEASON, session)
        print(f"AIrsenal worker: added {new_players} new player(s)")

        print("AIrsenal worker: updating fixtures")
        fill_fixtures_from_api(CURRENT_SEASON, session)
        update_results(CURRENT_SEASON, session)

    print("AIrsenal forecasting database updated without manager transaction state")


if __name__ == "__main__":
    main()
