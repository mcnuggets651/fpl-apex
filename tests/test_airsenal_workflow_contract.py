from pathlib import Path


# Only workflows that actively run the canonical Apex production/readiness path
# should be required to refresh genuine AIrsenal forecasts. CI-only and archived
# legacy publishers are intentionally excluded.
WORKFLOWS = (
    "gw1-final-2026.yml",
    "pinnacle.yml",
    "production-readiness.yml",
)


def test_production_workflows_do_not_require_a_manager_team_to_refresh_airsenal():
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in WORKFLOWS:
        workflow = (root / name).read_text(encoding="utf-8")
        assert "airsenal_setup_initial_db --fpl_team_id 1" in workflow, name
        assert "python scripts/update_airsenal_worker.py" in workflow, name
        assert "airsenal_update_db" not in workflow, name
        assert "scripts/run_apex.py" in workflow, name


def test_scheduled_airsenal_workflow_uses_canonical_horizon_wrapper():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "airsenal.yml"
    workflow = path.read_text(encoding="utf-8")

    assert 'uv run python "$GITHUB_WORKSPACE/scripts/run_airsenal_worker.py"' in workflow
    assert "--horizon 8" in workflow
    assert "uv run airsenal_run_prediction" not in workflow
    assert "Resolve live eight-Gameweek horizon" not in workflow
    assert "Export genuine AIrsenal forecast by official FPL ID" not in workflow


def test_unified_artifact_is_copied_before_runtime_diagnostics_are_restored():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")
    seal = workflow.index("Seal atomic workflow artifact before publication cleanup")
    restore = workflow.index("git restore --worktree .")
    upload = workflow.index("${{ runner.temp }}/apex-unified-packet/")
    assert seal < restore < upload
    assert "data/generated/pinnacle_latest.json" in workflow[seal:restore]
    assert "data/generated/decision_bundle" in workflow[seal:restore]


def test_explicit_readiness_blocks_reach_fail_closed_publication_path():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")

    assert 'payload.get("pinnacle_ready") is not False or not blockers' in workflow
    assert 'echo "ready_for_parity=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "Finalize fail-closed production status" in workflow
    assert "Publish latest canonical status and durable forecast archive" in workflow


def test_parity_bootstrap_block_advances_only_to_parity_stage():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")

    assert 'parity_bootstrap = [' in workflow
    assert 'if blockers == parity_bootstrap:' in workflow
    assert 'classification=$?' in workflow
