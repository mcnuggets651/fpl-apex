from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apex_fpl.replay.context import AsOfContext, SourceManifestEntry
from apex_fpl.replay.state import ReplayState, WeeklyAction, advance_free_transfers


UTC = timezone.utc
DIGEST = "a" * 64


def _source(*, available_at: datetime) -> SourceManifestEntry:
    return SourceManifestEntry(
        name="fpl_core",
        revision="abc123",
        content_sha256=DIGEST,
        published_at=available_at - timedelta(minutes=5),
        available_at=available_at,
        retrieved_at=available_at + timedelta(minutes=5),
    )


def test_as_of_context_rejects_future_information() -> None:
    deadline = datetime(2025, 8, 16, 10, tzinfo=UTC)
    cutoff = deadline - timedelta(hours=2)
    with pytest.raises(ValueError, match="future information"):
        AsOfContext(
            season="2025-2026",
            gameweek=1,
            deadline_utc=deadline,
            cutoff_utc=cutoff,
            code_sha="deadbeef",
            config_sha256=DIGEST,
            random_seed=1,
            sources=(_source(available_at=cutoff + timedelta(seconds=1)),),
        )


def test_manifest_hash_is_order_independent_and_deterministic() -> None:
    deadline = datetime(2025, 8, 16, 10, tzinfo=UTC)
    cutoff = deadline - timedelta(hours=2)
    source_a = _source(available_at=cutoff - timedelta(hours=1))
    source_b = SourceManifestEntry(
        name="official_fpl",
        revision="def456",
        content_sha256="b" * 64,
        published_at=cutoff - timedelta(hours=2),
        available_at=cutoff - timedelta(hours=1),
        retrieved_at=cutoff,
    )
    common = dict(
        season="2025-2026",
        gameweek=1,
        deadline_utc=deadline,
        cutoff_utc=cutoff,
        code_sha="deadbeef",
        config_sha256=DIGEST,
        random_seed=1,
    )
    first = AsOfContext(sources=(source_a, source_b), **common)
    second = AsOfContext(sources=(source_b, source_a), **common)
    assert first.manifest_sha256 == second.manifest_sha256


def test_versioned_free_transfer_transitions() -> None:
    assert advance_free_transfers(
        season="2026-2027",
        gameweek=1,
        free_transfers_before=0,
        permanent_transfers=0,
        active_chip=None,
    ) == 1
    assert advance_free_transfers(
        season="2025-2026",
        gameweek=15,
        free_transfers_before=1,
        permanent_transfers=1,
        active_chip=None,
    ) == 5
    assert advance_free_transfers(
        season="2026-2027",
        gameweek=15,
        free_transfers_before=1,
        permanent_transfers=1,
        active_chip=None,
    ) == 1


def test_replay_state_and_weekly_action_are_hashable_legal_contracts() -> None:
    squad = tuple(range(1, 16))
    state = ReplayState(
        season="2025-2026",
        next_gameweek=1,
        squad=squad,
        bank=0.0,
        free_transfers=0,
        purchase_prices=tuple((player_id, 5.0) for player_id in squad),
    )
    action = WeeklyAction(
        gameweek=1,
        transfers=(),
        chip=None,
        squad=squad,
        xi=tuple(range(1, 12)),
        bench_order=(12, 13, 14, 15),
        captain_id=1,
        vice_captain_id=2,
        hit_cost=0,
    )
    assert len(state.state_sha256) == 64
    assert action.to_dict()["captain_id"] == 1
