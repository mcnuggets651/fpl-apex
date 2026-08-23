from pathlib import Path


# Workflows that actively run the canonical Apex production/readiness path must
# refresh AIrsenal through the isolated worker contract rather than importing the
# worker into the Apex core interpreter.
WORKFLOWS = (
    "gw1-final-2026.yml",
    "pinnacle.yml",
    "production-readiness.yml",
)


def test_production_workflows_do_not_require_manager_transaction_state():
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in WORKFLOWS:
        workflow = (root / name).read_text(encoding="utf-8")
        assert "--fpl_team_id 1" in workflow, name
        assert "scripts/update_airsenal_worker.py" in workflow, name
        assert "airsenal_update_db" not in workflow, name
        assert "scripts/run_apex.py" in workflow, name


def test_scheduled_airsenal_workflow_uses_isolated_canonical_horizon_wrapper():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "airsenal.yml"
    workflow = path.read_text(encoding="utf-8")

    assert '"$AIRSENAL_WORKER_PYTHON" "$GITHUB_WORKSPACE/scripts/run_airsenal_worker.py"' in workflow
    assert "--horizon 8" in workflow
    assert "uv run airsenal_run_prediction" not in workflow
    assert "Resolve live eight-Gameweek horizon" not in workflow
    assert "Export genuine AIrsenal forecast by official FPL ID" not in workflow
    assert "contents: read" in workflow
    assert "git push origin HEAD:main" not in workflow
    assert "uv sync --frozen" in (path.parents[2] / "scripts/install_pinned_airsenal.sh").read_text(
        encoding="utf-8"
    )


def test_unified_artifact_is_sealed_before_runtime_release_is_staged():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")
    seal = workflow.index("Seal atomic workflow packet")
    stage = workflow.index("Stage immutable runtime release outside source control")
    upload = workflow.index("${{ runner.temp }}/apex-unified-packet/")
    assert seal < stage < upload
    assert "data/generated/pinnacle_latest.json" in workflow[seal:stage]
    assert "data/generated/decision_bundle" in workflow[seal:stage]
    assert "git restore --worktree ." not in workflow


def test_explicit_readiness_blocks_reach_fail_closed_runtime_release_path():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")

    assert 'payload.get("pinnacle_ready") is not False or not blockers' in workflow
    assert 'echo "ready_for_parity=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "Finalize fail-closed production status" in workflow
    assert "Stage immutable runtime release outside source control" in workflow
    assert "git push origin HEAD:main" not in workflow


def test_parity_bootstrap_block_advances_only_to_parity_stage():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")

    assert "parity_bootstrap = [" in workflow
    assert "if blockers == parity_bootstrap:" in workflow
    assert "classification=$?" in workflow
