from pathlib import Path


ROOT = Path(__file__).parents[1]
ACTIVE = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "archive" / "workflows"
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


def _v2_production() -> str:
    return (ACTIVE / "apex-v2-daily-production.yml").read_text(encoding="utf-8")


def test_v2_production_uses_non_cancelling_authenticated_concurrency_group():
    text = _v2_production()
    assert "group: apex-v2-fpl-auth" in text
    assert "cancel-in-progress: false" in text


def test_v2_production_is_frozen_and_does_not_direct_push_main():
    text = _v2_production()
    assert FROZEN_SHA in text
    assert 'APEX_CODE_SHA: "' + FROZEN_SHA + '"' in text
    assert "apex-v2 publish" in text
    assert "git push" not in text
    assert "git rebase" not in text
    assert "git pull --rebase" not in text
    assert "scripts/run_apex.py" not in text
    assert "run_pinnacle.py" not in text


def test_v2_production_publishes_only_after_a_frozen_offline_solve():
    text = _v2_production()
    acquire = text.index("apex-v2 acquire")
    offline = text.index('APEX_ALLOW_NETWORK_DURING_SOLVE: "0"')
    solve = text.index("apex-v2 solve")
    publish = text.index("apex-v2 publish")
    assert acquire < offline < solve < publish
    assert "Official FPL pre-provider hash" in text
    assert "Re-anchor Official truth and freeze all inputs once" in text


def test_retired_direct_publishers_are_not_in_active_actions_surface():
    for name in ("pinnacle.yml", "airsenal.yml", "refresh-core-pin.yml", "gw1-final-2026.yml"):
        assert not (ACTIVE / name).exists(), name
        assert (ARCHIVE / name).is_file(), name


def test_archived_pinnacle_preserves_fail_closed_publication_forensics():
    text = (ARCHIVE / "pinnacle.yml").read_text(encoding="utf-8")
    finalize = text.index("- name: Finalize fail-closed production status")
    publish = text.index("- name: Publish latest canonical status and durable forecast archive")
    assert finalize < publish
    assert "if: always()" in text[finalize:publish]
    assert "scripts/finalize_production_status.py" in text[finalize:publish]
    assert "data/history/production_runs" in text[publish:]


def test_archived_gw1_deadline_source_preserves_stricter_core_age_forensics():
    text = (ARCHIVE / "gw1-final-2026.yml").read_text(encoding="utf-8")
    assert 'APEX_MAX_CORE_AGE_HOURS: "12"' in text
