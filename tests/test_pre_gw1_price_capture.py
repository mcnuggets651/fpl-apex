from __future__ import annotations

from pathlib import Path

import pandas as pd

from apex_fpl.services.team_state import resolve_team_state


class FakeHttp:
    def get_json(self, url, key, force=False, params=None):
        if url.endswith("/entry/63984/"):
            return {"id": 63984, "name": "Apex XI"}
        if url.endswith("/entry/63984/history/"):
            return {"current": [], "chips": []}
        if url.endswith("/entry/63984/transfers/"):
            return []
        raise RuntimeError(f"unexpected URL: {url}")


def test_resolve_team_state_captures_initial_prices_before_public_gw1_picks(tmp_path: Path):
    players = pd.DataFrame(
        [
            {"player_id": 1, "price": 7.0},
            {"player_id": 2, "price": 5.5},
        ]
    )
    events = pd.DataFrame(
        [{"id": 1, "deadline_time": "2099-08-21T17:30:00Z"}]
    )

    resolution = resolve_team_state(
        http=FakeHttp(),
        players=players,
        events=events,
        cache_dir=tmp_path / "cache",
        current_squad_path=tmp_path / "missing.csv",
        team_state_path=tmp_path / "missing.yaml",
        entry_id=63984,
        force=True,
    )

    assert resolution.ok
    assert resolution.state is None
    price_file = tmp_path / "cache" / "fpl_initial_prices_2026_27.csv"
    assert price_file.exists()
    captured = pd.read_csv(price_file)
    assert captured.set_index("player_id").loc[1, "price"] == 7.0
    assert captured.set_index("player_id").loc[2, "price"] == 5.5
    assert "price universe captured" in resolution.detail
