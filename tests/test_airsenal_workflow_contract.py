from pathlib import Path


# Only workflows that actively run the canonical Apex production/readiness path
# should be required to refresh genuine AIrsenal forecasts. CI-only and archived
# legacy publishers are intentionally excluded.
WORKFLOWS = (
    "gw1-final-2026.yml",
    "pinnacle.yml",
    "production-readiness.yml",
)


def _unified() -> str:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pinnacle.yml"
    return path.read_text(encoding="utf-8")


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


def test_unified_artifact_is_sealed_from_the_current_run_generation_before_publication_mutates_git():
    workflow = _unified()
    seal = workflow.index("Seal current-generation workflow artifact")
    publish = workflow.index("Publish current canonical status with compare-and-swap")
    upload = workflow.index("apex-unified-${{ github.run_id }}")
    assert seal < publish < upload
    sealed = workflow[seal:publish]
    assert 'cp -a "$RUN_DIR" "$packet/data/generated/run"' in sealed
    assert "certified_generation.json" in sealed
    assert "data/generated/decision_bundle" not in sealed
    assert "git restore --worktree ." not in sealed


def test_explicit_pinnacle_blocks_are_classified_without_masquerading_as_parity_bootstrap():
    workflow = _unified()
    classification = workflow[
        workflow.index("Generate current-generation Pinnacle surface") :
        workflow.index("Read pinned independent solver revision")
    ]
    assert 'blockers == ["required independent solver parity snapshot is not embedded"]' in classification
    assert 'echo "ready_for_parity=$([ "$classification" -eq 0 ] && echo true || echo false)"' in classification
    assert 'if [ "$classification" -eq 0 ]; then' in classification
    assert "scripts/export_open_solver.py" in classification


def test_parity_stage_consumes_only_the_sealed_bundle_and_content_addressed_input():
    workflow = _unified()
    assert 'RUN_DIR: data/generated/runs/${{ github.run_id }}' in workflow
    assert 'BUNDLE_DIR: data/generated/runs/${{ github.run_id }}/decision_bundle' in workflow
    assert 'PARITY_DIR: data/generated/runs/${{ github.run_id }}/open_solver_parity_input' in workflow
    assert 'python scripts/export_open_solver.py "$BUNDLE_DIR" /tmp/apex.csv --projection-col xp' in workflow
    assert "scripts/build_open_solver_parity_input.py" in workflow
    assert "scripts/run_open_solver_parity.py" in workflow
    assert "scripts/compare_solver_parity.py" in workflow
    assert "scripts/embed_solver_parity.py" in workflow


def test_generation_is_finalized_then_promoted_before_cas_publication():
    workflow = _unified()
    finalize = workflow.index("Finalize current-generation fail-closed status")
    promote = workflow.index("Promote exactly one coherent generation to latest aliases")
    publish = workflow.index("Publish current canonical status with compare-and-swap")
    assert finalize < promote < publish
    assert "scripts/finalize_production_status.py" in workflow[finalize:promote]
    assert "scripts/promote_certified_generation.py" in workflow[promote:publish]
    assert 'if [ "$(git rev-parse origin/main)" != "${{ github.sha }}" ]; then' in workflow[publish:]
