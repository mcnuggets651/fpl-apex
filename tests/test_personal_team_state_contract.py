from __future__ import annotations

from pathlib import Path

import yaml

from apex_fpl.services.team_state import TeamState, _actionable_state_ok


ROOT = Path(__file__).resolve().parents[1]


def _state(**overrides) -> TeamState:
    squad = set(range(1, 16))
    values = {
        "squad": squad,
        "bank": 0.5,
        "free_transfers": 1,
        "source": "public_fpl_entry",
        "entry_id": 63984,
        "published_gw": 1,
        "selling_prices": {pid: 4.5 + pid / 10 for pid in squad},
        "selling_prices_exact": True,
        "transfer_history_complete": True,
        "public_deadline_snapshot": True,
    }
    values.update(overrides)
    return TeamState(**values)


def test_production_config_requires_personal_team_state_source():
    config = yaml.safe_load((ROOT / "config" / "apex.yaml").read_text(encoding="utf-8"))
    assert int(config["fpl_entry_id"]) == 63984
    assert "team_state" in config["required_sources"]


def test_exact_public_15_is_actionable_for_weekly_transfer_optimisation():
    assert _actionable_state_ok(_state()) is True


def test_missing_one_realised_selling_price_blocks_weekly_optimisation():
    prices = {pid: 4.5 + pid / 10 for pid in range(1, 15)}
    assert _actionable_state_ok(_state(selling_prices=prices)) is False


def test_approximate_selling_prices_block_weekly_optimisation():
    assert _actionable_state_ok(_state(selling_prices_exact=False)) is False


def test_invalid_bank_or_free_transfer_state_blocks_weekly_optimisation():
    assert _actionable_state_ok(_state(bank=-0.1)) is False
    assert _actionable_state_ok(_state(free_transfers=0)) is False
    assert _actionable_state_ok(_state(free_transfers=6)) is False


def test_public_deadline_identity_is_preserved_for_gw2_engine():
    state = _state()
    assert state.source == "public_fpl_entry"
    assert state.entry_id == 63984
    assert state.published_gw == 1
    assert state.public_deadline_snapshot is True
    assert state.published_gw + 1 == 2
