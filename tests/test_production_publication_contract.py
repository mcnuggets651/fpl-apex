from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WRITERS = ["pinnacle.yml", "airsenal.yml", "refresh-core-pin.yml"]


def _workflow(name: str) -> tuple[dict, str]:
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def test_all_main_writers_share_one_non_cancelling_concurrency_group():
    for name in WRITERS:
        workflow, _ = _workflow(name)
        assert workflow["concurrency"] == {
            "group": "apex-production-write",
            "cancel-in-progress": False,
        }


def test_no_production_writer_rebases_a_result_onto_changed_inputs():
    for name in WRITERS:
        _, text = _workflow(name)
        assert "git rebase" not in text
        assert "git pull --rebase" not in text
        assert "git rev-parse origin/main" in text
        assert "github.sha" in text


def test_unified_publishes_latest_status_even_when_decision_is_withheld():
    _, text = _workflow("pinnacle.yml")
    marker = "- name: Publish latest canonical status and durable forecast archive"
    publish = text[text.index(marker) :]
    assert "if: steps.canonical.outputs.ready == 'true'" not in publish.split(
        "- name:", 1
    )[0]
    assert "data/history/deadlines" in publish


def test_unified_finalizes_and_publishes_after_early_failure():
    _, text = _workflow("pinnacle.yml")
    finalize = text.index("- name: Finalize fail-closed production status")
    publish = text.index("- name: Publish latest canonical status and durable forecast archive")
    assert finalize < publish
    assert "if: always()" in text[finalize:publish]
    assert "scripts/finalize_production_status.py" in text[finalize:publish]
    assert "if: always()" in text[publish : publish + 180]
    assert "data/history/production_runs" in text[publish:]


def test_explicit_readiness_block_skips_parity_without_failing_workflow():
    _, text = _workflow("pinnacle.yml")
    assert 'echo "ready_for_parity=false" >> "$GITHUB_OUTPUT"' in text
    assert "Pinnacle exited non-zero without an explicit readiness block" in text
    assert text.count("if: steps.pinnacle.outputs.ready_for_parity == 'true'") == 4


def test_missing_parity_alone_bootstraps_independent_solver_stage():
    _, text = _workflow("pinnacle.yml")
    assert 'if blockers == parity_bootstrap:' in text
    assert 'echo "ready_for_parity=true" >> "$GITHUB_OUTPUT"' in text
    assert "scripts/export_open_solver.py" in text


def test_final_deadline_run_uses_stricter_core_age_limit():
    _, text = _workflow("gw1-final-2026.yml")
    assert 'APEX_MAX_CORE_AGE_HOURS: "12"' in text
