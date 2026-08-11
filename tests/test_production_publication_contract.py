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


def test_final_deadline_run_uses_stricter_core_age_limit():
    _, text = _workflow("gw1-final-2026.yml")
    assert 'APEX_MAX_CORE_AGE_HOURS: "12"' in text
