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


def test_unified_publishes_current_status_even_when_decision_is_withheld():
    _, text = _workflow("pinnacle.yml")
    marker = "- name: Publish current canonical status with compare-and-swap"
    publish = text[text.index(marker) :]
    assert "if: always()" in publish[:240]
    assert "data/generated/apex_recommendation_latest.json" in publish
    assert "data/history/deadlines" in publish
    assert "data/history/production_runs" in publish


def test_unified_finalizes_promotes_and_publishes_one_generation_after_early_failure():
    _, text = _workflow("pinnacle.yml")
    finalize = text.index("- name: Finalize current-generation fail-closed status")
    promote = text.index("- name: Promote exactly one coherent generation to latest aliases")
    publish = text.index("- name: Publish current canonical status with compare-and-swap")
    assert finalize < promote < publish
    assert "if: always()" in text[finalize:promote]
    assert "scripts/finalize_production_status.py" in text[finalize:promote]
    assert "if: always()" in text[promote:publish]
    assert "scripts/promote_certified_generation.py" in text[promote:publish]
    assert "if: always()" in text[publish : publish + 220]


def test_generation_namespace_is_empty_before_any_producer_runs():
    _, text = _workflow("pinnacle.yml")
    create = text.index("- name: Create empty production generation namespace")
    tests = text.index("- name: Run deterministic and adversarial stress tests")
    block = text[create:tests]
    assert 'rm -rf "$RUN_DIR"' in block
    assert 'mkdir -p "$RUN_DIR" "$APEX_REPORT_DIR"' in block
    assert 'test ! -e "$RUN_DIR/apex_recommendation_latest.json"' in block
    assert 'test ! -e "$RUN_DIR/pinnacle_latest.json"' in block
    assert 'test ! -e "$RUN_DIR/solver_parity.json"' in block


def test_explicit_readiness_block_advances_only_to_parity_bootstrap():
    _, text = _workflow("pinnacle.yml")
    step = text[text.index("- name: Generate current-generation Pinnacle surface") :]
    assert "classification=1" in step
    assert 'blockers == ["required independent solver parity snapshot is not embedded"]' in step
    assert 'echo "ready_for_parity=$([ "$classification" -eq 0 ] && echo true || echo false)"' in step
    assert text.count("if: steps.pinnacle.outputs.ready_for_parity == 'true'") == 2


def test_missing_parity_alone_builds_sealed_independent_solver_stage():
    _, text = _workflow("pinnacle.yml")
    pinnacle = text[
        text.index("- name: Generate current-generation Pinnacle surface") :
        text.index("- name: Read pinned independent solver revision")
    ]
    assert 'blockers == ["required independent solver parity snapshot is not embedded"]' in pinnacle
    assert 'if [ "$classification" -eq 0 ]; then' in pinnacle
    assert 'python scripts/export_open_solver.py "$BUNDLE_DIR" /tmp/apex.csv --projection-col xp' in pinnacle
    assert "scripts/build_open_solver_parity_input.py" in text
    assert "scripts/compare_solver_parity.py" in text
    assert "scripts/embed_solver_parity.py" in text


def test_atomic_artifact_is_sealed_from_current_run_namespace():
    _, text = _workflow("pinnacle.yml")
    seal = text.index("- name: Seal current-generation workflow artifact")
    publish = text.index("- name: Publish current canonical status with compare-and-swap")
    upload = text.index("- uses: actions/upload-artifact@v4")
    assert seal < publish < upload
    block = text[seal:publish]
    assert 'cp -a "$RUN_DIR" "$packet/data/generated/run"' in block
    assert "data/generated/certified_generation.json" in block


def test_publication_uses_compare_and_swap_against_exact_solved_main_sha():
    _, text = _workflow("pinnacle.yml")
    marker = "- name: Publish current canonical status with compare-and-swap"
    publish = text[text.index(marker) :]
    assert "git fetch origin main" in publish
    assert 'if [ "$(git rev-parse origin/main)" != "${{ github.sha }}" ]; then' in publish
    assert "refusing stale-writer publication" in publish
    assert "git push origin HEAD:main" in publish


def test_final_deadline_run_uses_stricter_core_age_limit():
    _, text = _workflow("gw1-final-2026.yml")
    assert 'APEX_MAX_CORE_AGE_HOURS: "12"' in text
