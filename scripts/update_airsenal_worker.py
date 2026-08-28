#!/usr/bin/env python3
"""Update a pinned AIrsenal database for forecasting without manager-team state.

AIrsenal's public ``airsenal_update_db`` CLI also updates the configured FPL
manager's transfer history. That is useful when AIrsenal itself is managing a
specific team, but it is irrelevant to Apex's independent player forecast worker
and would make the worker depend on an arbitrary public team ID after GW1.

Run this script *inside the pinned AIrsenal environment*. It reuses the exact
upstream update functions for players, attributes, fixtures and results while
deliberately skipping only ``update_transactions``.

Two Apex-owned transport/cache guards sit outside the forecast model itself:
- bounded retry for transient Official FPL HTTP 429/5xx responses;
- deterministic rewind of only the current-season PlayerAttributes window that
  upstream itself intends to rebuild from the last completed GW onward.

Neither guard substitutes cached forecasts, changes projection logic, or weakens
freshness/coverage qualification. Persistent failures remain fatal.
"""
from __future__ import annotations

from airsenal.framework.data_fetcher import FPLDataFetcher
from airsenal.framework.env import AIRSENAL_DB_FILE
from airsenal.framework.schema import database_is_empty, session_scope
from airsenal.framework.utils import (
    CURRENT_SEASON,
    get_last_complete_gameweek_in_db,
)
from airsenal.scripts.fill_fixture_table import fill_fixtures_from_api
from airsenal.scripts.fill_player_attributes_table import fill_attributes_table_from_api
from airsenal.scripts.update_db import update_players, update_results

from airsenal_attribute_refresh import rewind_player_attributes
from airsenal_transient_retry import retry_transient_http


def _install_transient_http_retry() -> None:
    current = FPLDataFetcher._get_request
    if getattr(current, "_apex_transient_retry", False):
        return

    original = current

    def wrapped(
        self,
        url,
        err_msg="Unable to access FPL API",
        attempts=3,
        **params,
    ):
        def operation():
            return original(
                self,
                url,
                err_msg=err_msg,
                attempts=attempts,
                **params,
            )

        def on_retry(
            attempt: int,
            status: int,
            delay: float,
            _exc: BaseException,
        ) -> None:
            print(
                "AIrsenal worker: transient FPL HTTP "
                f"{status} for {url}; retrying after {delay:g}s "
                f"(attempt {attempt + 1}/4)"
            )

        return retry_transient_http(
            operation,
            max_attempts=4,
            base_delay_seconds=1.0,
            on_retry=on_retry,
        )

    wrapped._apex_transient_retry = True  # type: ignore[attr-defined]
    FPLDataFetcher._get_request = wrapped


def main() -> None:
    _install_transient_http_retry()

    # Update identity first and commit it before touching the mutable attributes
    # window. The upstream function commits its own player-table changes, and the
    # surrounding scope preserves the same fail-closed transaction semantics.
    with session_scope() as session:
        if database_is_empty(session):
            raise SystemExit(
                "AIrsenal database is empty; run airsenal_setup_initial_db first"
            )
        new_players = update_players(CURRENT_SEASON, session)
        last_complete = get_last_complete_gameweek_in_db(
            CURRENT_SEASON,
            dbsession=session,
        )

    # Upstream update_attributes() refills from and including last_complete (or
    # from 0 before any completed GW). A restored cache can already contain those
    # mutable rows. Since the pinned session uses autoflush=False, repeated rows
    # encountered during the same refresh can collide only at commit. Rewinding
    # exactly the upstream rebuild window makes the operation deterministic and
    # idempotent without touching stable earlier history.
    if not AIRSENAL_DB_FILE:
        raise SystemExit("AIRSENAL_DB_FILE must be set for the isolated Apex worker")
    refresh_from = max(1, int(last_complete or 0))
    removed = rewind_player_attributes(
        AIRSENAL_DB_FILE,
        season=CURRENT_SEASON,
        from_gameweek=refresh_from,
    )
    print(
        "AIrsenal worker: rewound "
        f"{removed} mutable attribute row(s) from GW{refresh_from} onward"
    )

    with session_scope() as session:
        fill_attributes_table_from_api(
            season=CURRENT_SEASON,
            gw_start=int(last_complete or 0),
            dbsession=session,
        )
        print(f"AIrsenal worker: added {new_players} new player(s)")

        print("AIrsenal worker: updating fixtures")
        fill_fixtures_from_api(CURRENT_SEASON, session)
        update_results(CURRENT_SEASON, session)

    print("AIrsenal forecasting database updated without manager transaction state")


if __name__ == "__main__":
    main()
