from __future__ import annotations

from itertools import product
from pathlib import Path
import tempfile

import pytest
pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st

from apex.decision.mechanics import _best_captain_vice, _state_probability
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.domain.rules import SeasonRules, derive_next_free_transfers
from apex.runtime.snapshot import SnapshotBuilder

PROB = st.floats(min_value=-2.0, max_value=3.0, allow_nan=False, allow_infinity=False, width=32)
XP = st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False, width=32)


@given(
    current_ft=st.integers(-5, 12),
    transfers=st.integers(0, 12),
    max_ft=st.integers(1, 8),
)
def test_free_transfer_transition_is_bounded(current_ft, transfers, max_ft):
    rules = SeasonRules("synthetic", max_rolled_free_transfers=max_ft)
    result = derive_next_free_transfers(current_ft, transfers, rules=rules)
    assert 1 <= result <= max_ft


@given(
    current_ft=st.integers(0, 8),
    transfers=st.integers(0, 8),
    top_up=st.integers(1, 8),
    max_ft=st.integers(1, 8),
)
def test_free_transfer_top_up_is_floor_capped_by_season_max(current_ft, transfers, top_up, max_ft):
    rules = SeasonRules(
        "synthetic",
        max_rolled_free_transfers=max_ft,
        free_transfer_top_ups=((7, top_up),),
    )
    result = derive_next_free_transfers(
        current_ft,
        transfers,
        next_gameweek=7,
        rules=rules,
    )
    assert min(top_up, max_ft) <= result <= max_ft


@given(
    current_ft=st.integers(0, 8),
    transfers=st.integers(0, 8),
    max_ft=st.integers(1, 8),
    chip=st.sampled_from(["wildcard", "freehit", "free_hit", "WILDCARD"]),
)
def test_reset_chips_do_not_spend_rolled_free_transfers(current_ft, transfers, max_ft, chip):
    rules = SeasonRules("synthetic", max_rolled_free_transfers=max_ft)
    result = derive_next_free_transfers(current_ft, transfers, chip=chip, rules=rules)
    assert result == min(max_ft, max(1, current_ft))


@given(a=st.binary(max_size=64), b=st.binary(max_size=64))
def test_snapshot_identity_is_insertion_order_invariant(a: bytes, b: bytes):
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        first = SnapshotBuilder()
        first.add_bytes("a.bin", a)
        first.add_bytes("nested/b.bin", b)
        one = first.freeze(root / "one", metadata={"purpose": "property"})
        second = SnapshotBuilder()
        second.add_bytes("nested/b.bin", b)
        second.add_bytes("a.bin", a)
        two = second.freeze(root / "two", metadata={"purpose": "property"})
        assert one.snapshot_id == two.snapshot_id
        assert one.manifest == two.manifest


@given(a=st.binary(max_size=64), b=st.binary(max_size=64))
def test_snapshot_identity_is_content_sensitive(a: bytes, b: bytes):
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        first = SnapshotBuilder()
        first.add_bytes("payload.bin", a)
        one = first.freeze(root / "one")
        second = SnapshotBuilder()
        second.add_bytes("payload.bin", b)
        two = second.freeze(root / "two")
        assert (one.snapshot_id == two.snapshot_id) is (a == b)


@given(probabilities=st.lists(PROB, min_size=1, max_size=8))
def test_binary_appearance_states_normalise(probabilities):
    total = sum(
        _state_probability(tuple(bits), list(probabilities))
        for bits in product((0, 1), repeat=len(probabilities))
    )
    assert total == pytest.approx(1.0, abs=1e-9)


@given(
    xp_values=st.lists(XP, min_size=11, max_size=11),
    appearances=st.lists(PROB, min_size=11, max_size=11),
)
def test_captain_vice_matches_exhaustive_objective(xp_values, appearances):
    xi = tuple(range(1, 12))
    xp = dict(zip(xi, xp_values, strict=True))
    appearance = dict(zip(xi, appearances, strict=True))
    captain, vice, bonus = _best_captain_vice(xi, xp, appearance)

    def clamp(value):
        return min(max(float(value), 0.0), 1.0)

    expected = max(
        xp[c] + (1.0 - clamp(appearance[c])) * xp[v]
        for c in xi for v in xi if c != v
    )
    assert captain != vice
    assert bonus == pytest.approx(expected, abs=1e-10)


@given(
    flags=st.lists(st.booleans(), min_size=6, max_size=6),
    owned=st.sets(st.integers(1, 6), max_size=6),
)
def test_decision_universe_preserves_owned_official_players(flags, owned):
    players = tuple(
        OfficialPlayer(i, f"P{i}", i, Position.MID, 50, "a", flags[i - 1])
        for i in range(1, 7)
    )
    official = OfficialSnapshot(1, "2026-2027", "2026-09-03T06:00:00Z", "official", players, (), {3: "2026-09-12T10:00:00Z"})
    universe = official.decision_universe(owned)
    assert owned.issubset(universe)
    for player in players:
        assert (player.element_id in universe) is (player.can_transact or player.element_id in owned)
