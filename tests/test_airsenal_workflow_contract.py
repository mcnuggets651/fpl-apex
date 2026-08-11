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


def test_unified_artifact_is_copied_before_runtime_diagnostics_are_restored():
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    workflow = path.read_text(encoding="utf-8")
    seal = workflow.index("Seal atomic workflow artifact before publication cleanup")
    restore = workflow.index("git restore --worktree .")
    upload = workflow.index("${{ runner.temp }}/apex-unified-packet/")
    assert seal < restore < upload
    assert "data/generated/pinnacle_latest.json" in workflow[seal:restore]
    assert "data/generated/decision_bundle" in workflow[seal:restore]
