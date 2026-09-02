from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "archive" / "workflows"
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
RETIRED = (
    "gw1-final-2026.yml",
    "pinnacle.yml",
    "airsenal.yml",
    "refresh-core-pin.yml",
)


def test_retired_legacy_publishers_are_archived_not_executable():
    for name in RETIRED:
        assert not (ACTIVE / name).exists(), name
        archived = ARCHIVE / name
        assert archived.is_file(), name
        assert archived.stat().st_size > 0, name


def test_v2_production_keeps_airsenal_worker_manager_independent():
    workflow = (ACTIVE / "apex-v2-daily-production.yml").read_text(encoding="utf-8")

    assert FROZEN_SHA in workflow
    assert 'FPL_TEAM_ID: "1"' in workflow
    assert "airsenal_setup_initial_db --fpl_team_id 1" in workflow
    assert "python \"$GITHUB_WORKSPACE/scripts/update_airsenal_worker.py\"" in workflow
    assert "airsenal_update_db" not in workflow
    assert "run_airsenal_worker.py" in workflow
    assert "--horizon 8" in workflow
    assert "APEX_PRIVATE_MANAGER_ENABLED" in workflow
    assert "apex-v2 acquire" in workflow


def test_archived_airsenal_preserves_historical_horizon_wrapper_for_forensics():
    workflow = (ARCHIVE / "airsenal.yml").read_text(encoding="utf-8")

    assert 'uv run python "$GITHUB_WORKSPACE/scripts/run_airsenal_worker.py"' in workflow
    assert "--horizon 8" in workflow
    assert "uv run airsenal_run_prediction" not in workflow


def test_archived_pinnacle_preserves_atomic_artifact_order_for_forensics():
    workflow = (ARCHIVE / "pinnacle.yml").read_text(encoding="utf-8")
    seal = workflow.index("Seal atomic workflow artifact before publication cleanup")
    restore = workflow.index("git restore --worktree .")
    upload = workflow.index("${{ runner.temp }}/apex-unified-packet/")
    assert seal < restore < upload
    assert "data/generated/pinnacle_latest.json" in workflow[seal:restore]
    assert "data/generated/decision_bundle" in workflow[seal:restore]


def test_archived_pinnacle_preserves_fail_closed_readiness_logic_for_forensics():
    workflow = (ARCHIVE / "pinnacle.yml").read_text(encoding="utf-8")

    assert 'payload.get("pinnacle_ready") is not False or not blockers' in workflow
    assert 'echo "ready_for_parity=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "Finalize fail-closed production status" in workflow
    assert "Publish latest canonical status and durable forecast archive" in workflow
    assert 'parity_bootstrap = [' in workflow
    assert 'if blockers == parity_bootstrap:' in workflow
