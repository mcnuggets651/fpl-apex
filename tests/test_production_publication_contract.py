from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
RUNTIME_WORKFLOWS = ["pinnacle.yml", "airsenal.yml", "refresh-core-pin.yml"]


def _workflow(name: str) -> tuple[dict, str]:
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def test_runtime_workflows_have_no_source_write_permission_or_main_push():
    for name in RUNTIME_WORKFLOWS:
        workflow, text = _workflow(name)
        assert workflow["permissions"] == {"contents": "read"}, name
        assert "contents: write" not in text, name
        assert "git push origin HEAD:main" not in text, name
        assert "git pull --rebase" not in text, name
        assert "git rebase" not in text, name


def test_unified_stages_current_status_even_when_decision_is_withheld():
    _, text = _workflow("pinnacle.yml")
    finalize = text.index("- name: Finalize fail-closed production status")
    seal = text.index("- name: Seal atomic workflow packet")
    stage = text.index("- name: Stage immutable runtime release outside source control")
    upload = text.index("- uses: actions/upload-artifact@v4")
    assert finalize < seal < stage < upload
    assert "if: always()" in text[finalize:seal]
    assert "if: always()" in text[seal:stage]
    assert "if: always()" in text[stage:upload]
    assert "scripts/stage_runtime_release.py" in text[stage:upload]
    assert "data/history/deadlines" in text[seal:stage]
    assert "data/history/production_runs" in text[seal:stage]


def test_unified_never_recreates_git_as_runtime_registry():
    _, text = _workflow("pinnacle.yml")
    forbidden = (
        "git add -f",
        "data: publish canonical Apex recommendation",
        "git config user.name",
        "git config user.email",
    )
    assert all(token not in text for token in forbidden)
    assert 'test "$(git rev-parse HEAD)" = "${{ github.sha }}"' in text


def test_airsenal_forecast_is_validation_artifact_not_tracked_runtime_state():
    _, text = _workflow("airsenal.yml")
    assert "Commit validated forecast" not in text
    assert "invalidate_published_decision.py" not in text
    assert "data/generated/airsenal.csv" in text
    assert "actions/upload-artifact@v4" in text


def test_core_pin_refresh_is_audited_proposal_not_direct_source_mutation():
    _, text = _workflow("refresh-core-pin.yml")
    assert "Materialize proposed immutable data pin" in text
    assert "Commit validated FPL Core revision" not in text
    assert "invalidate_published_decision.py" not in text
    assert "reviewed dependency source change required" in text
    assert "actions/upload-artifact@v4" in text
    assert "upstreams.lock.json" in text


def test_explicit_readiness_block_skips_parity_without_failing_workflow():
    _, text = _workflow("pinnacle.yml")
    assert 'echo "ready_for_parity=false" >> "$GITHUB_OUTPUT"' in text
    assert "Pinnacle exited non-zero without an explicit readiness block" in text
    assert text.count("if: steps.pinnacle.outputs.ready_for_parity == 'true'") == 4


def test_missing_parity_alone_bootstraps_independent_solver_stage():
    _, text = _workflow("pinnacle.yml")
    assert "if blockers == parity_bootstrap:" in text
    assert 'echo "ready_for_parity=true" >> "$GITHUB_OUTPUT"' in text
    assert "scripts/export_open_solver.py" in text


def test_final_deadline_run_uses_stricter_core_age_limit():
    _, text = _workflow("gw1-final-2026.yml")
    assert 'APEX_MAX_CORE_AGE_HOURS: "12"' in text
