from datetime import datetime, timedelta, timezone

from apex_fpl.services.provenance import validate_core_pin


def test_stale_core_commit_fails_runtime_readiness():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    source = {
        "commit": "a" * 40,
        "committed_at": (now - timedelta(hours=19)).isoformat(),
        "resolved_at": now.isoformat(),
        "newer_revision_available": False,
    }
    ok, detail, provenance = validate_core_pin(source, max_age_hours=18, now=now)
    assert not ok
    assert "stale" in detail
    assert provenance["age_hours"] == 19


def test_current_core_commit_passes_and_records_provenance():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    source = {
        "commit": "b" * 40,
        "committed_at": (now - timedelta(hours=3)).isoformat(),
        "resolved_at": now.isoformat(),
        "newer_revision_available": False,
    }
    ok, _, provenance = validate_core_pin(source, max_age_hours=18, now=now)
    assert ok
    assert provenance["commit"] == "b" * 40
    assert provenance["age_hours"] == 3
    assert provenance["newer_revision_available_at_resolution"] is False
