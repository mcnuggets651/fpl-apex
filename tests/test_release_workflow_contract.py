from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".github/workflows/adaptive-canonical-diagnostic.yml"
ADAPTIVE = ROOT / ".github/workflows/joint-path-promotion-audit.yml"
UNIFIED = ROOT / ".github/workflows/pinnacle.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_workflow_is_reusable_and_runs_complete_release_certifier():
    workflow = _text(CANONICAL)
    assert "workflow_call:" in workflow
    assert "scripts/certify_release_generation.py" in workflow
    assert "Release certifier contract tests" in workflow
    assert "PROMOTION_DIR: ${{ runner.temp }}" not in workflow
    assert "PROMOTION_DIR: /tmp/canonical-certified-generation" in workflow


def test_adaptive_workflow_reuses_the_canonical_release_transaction():
    workflow = _text(ADAPTIVE)
    assert "name: Apex Adaptive Strategy Audit" in workflow
    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in workflow
    assert "secrets: inherit" in workflow
    assert "runner.temp" not in workflow


def test_unified_requires_release_certificate_before_ready_finalization():
    workflow = _text(UNIFIED)
    assert "scripts/certify_release_generation.py" in workflow
    assert "id: release" in workflow
    assert 'steps.release.outputs.exit_code' in workflow
    assert (
        'if [ "${{ steps.canonical.outputs.exit_code }}" = "0" ] '
        '&& [ "${{ steps.release.outputs.exit_code }}" = "0" ]; then'
    ) in workflow
    assert "--canonical-step-succeeded" in workflow
    assert "if: steps.release.outputs.exit_code == '0'" in workflow
