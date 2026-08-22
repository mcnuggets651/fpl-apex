from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PR_CERTIFICATION_WORKFLOWS = (
    ".github/workflows/projection-policy-audit.yml",
    ".github/workflows/projection-shadow-audit.yml",
    ".github/workflows/adaptive-canonical-diagnostic.yml",
    ".github/workflows/joint-path-promotion-audit.yml",
)


def _workflow(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pull_request_certification_checks_out_exact_head_sha():
    expected = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
    for path in PR_CERTIFICATION_WORKFLOWS:
        assert expected in _workflow(path), path


def test_canonical_and_adaptive_use_run_scoped_generation_and_sealed_parity():
    for path in (
        ".github/workflows/adaptive-canonical-diagnostic.yml",
        ".github/workflows/joint-path-promotion-audit.yml",
    ):
        workflow = _workflow(path)
        assert "data/generated/runs/${{ github.run_id }}" in workflow, path
        assert "build_open_solver_parity_input.py" in workflow, path
        assert "run_open_solver_parity.py" in workflow, path
        assert 'export_open_solver.py "$BUNDLE_DIR"' in workflow, path
        assert "reports/players.csv reports/projections.csv" not in workflow, path
        assert "uv run python run/solve.py" not in workflow, path


def test_adaptive_adversarial_certification_is_mandatory_not_best_effort():
    workflow = _workflow(".github/workflows/joint-path-promotion-audit.yml")
    assert "certify_adversarial_launch_ban.py" in workflow
    adversarial_section = workflow.split(
        "- name: Run mandatory adversarial selection sensitivity", 1
    )[1].split("- name: Run mandatory submitted-XI bench stress", 1)[0]
    assert "if: always()" not in adversarial_section
    assert "--canonical" in adversarial_section


def test_manual_readiness_replays_exact_production_promotion_transaction():
    workflow = _workflow(".github/workflows/production-readiness.yml")
    assert "data/generated/runs/${{ github.run_id }}" in workflow
    assert "build_open_solver_parity_input.py" in workflow
    assert "run_open_solver_parity.py" in workflow
    assert "promote_certified_generation.py" in workflow
    assert "git push" not in workflow
