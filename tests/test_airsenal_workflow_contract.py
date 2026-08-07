from pathlib import Path


WORKFLOWS = (
    "apex.yml",
    "bootstrap-publish.yml",
    "gw1-final-2026.yml",
    "pinnacle.yml",
    "production-readiness.yml",
    "publish-apex.yml",
)


def test_production_workflows_do_not_require_a_manager_team_to_refresh_airsenal():
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in WORKFLOWS:
        workflow = (root / name).read_text(encoding="utf-8")
        assert "airsenal_setup_initial_db --fpl_team_id 1" in workflow, name
        assert "python scripts/update_airsenal_worker.py" in workflow, name
        assert "airsenal_update_db" not in workflow, name
