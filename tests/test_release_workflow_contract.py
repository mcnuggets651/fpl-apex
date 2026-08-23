from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".github/workflows/adaptive-canonical-diagnostic.yml"
ADAPTIVE = ROOT / ".github/workflows/joint-path-promotion-audit.yml"
READINESS = ROOT / ".github/workflows/production-readiness.yml"
UNIFIED = ROOT / ".github/workflows/pinnacle.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_workflow_is_reusable_and_runs_lifecycle_release_certifier():
    workflow = _text(CANONICAL)
    assert "workflow_call:" in workflow
    assert "scripts/certify_release_generation.py" in workflow
    assert "Release-profile contract tests" in workflow
    assert "Certify lifecycle-specific sensitivity, mechanics and promotion" in workflow
    assert "PROMOTION_DIR: ${{ runner.temp }}" not in workflow
    assert "PROMOTION_DIR: /tmp/canonical-certified-generation" in workflow


def test_adaptive_workflow_is_focused_not_a_second_live_release_transaction():
    workflow = _text(ADAPTIVE)
    jobs = workflow.split("\njobs:\n", 1)[1]
    assert "name: Apex Adaptive Strategy Audit" in workflow
    assert "Prove lifecycle-specific release contracts" in jobs
    assert "run_airsenal_worker.py" not in jobs
    assert "run_pinnacle.py" not in jobs
    assert "run_apex.py" not in jobs
    assert "runner.temp" not in jobs


def test_manual_readiness_reuses_exact_canonical_release_transaction():
    workflow = _text(READINESS)
    jobs = workflow.split("\njobs:\n", 1)[1]
    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in jobs
    assert "secrets: inherit" in jobs
    assert "runner.temp" not in jobs


def test_unified_requires_release_certificate_before_ready_finalization():
    workflow = _text(UNIFIED)
    assert "scripts/certify_release_generation.py" in workflow
    assert "id: release" in workflow
    assert "steps.release.outputs.exit_code" in workflow
    assert (
        'if [ "${{ steps.canonical.outputs.exit_code }}" = "0" ] '
        '&& [ "${{ steps.release.outputs.exit_code }}" = "0" ]; then'
    ) in workflow
    assert "--canonical-step-succeeded" in workflow
    assert "if: steps.release.outputs.exit_code == '0'" in workflow
