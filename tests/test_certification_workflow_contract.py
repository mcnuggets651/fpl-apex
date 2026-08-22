from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DIRECT_PR_CERTIFICATION_WORKFLOWS = (
    ".github/workflows/apex.yml",
    ".github/workflows/projection-policy-audit.yml",
    ".github/workflows/projection-shadow-audit.yml",
    ".github/workflows/adaptive-canonical-diagnostic.yml",
    ".github/workflows/team-strength-validation.yml",
    ".github/workflows/understat-player-production-ab.yml",
)
CANONICAL = ".github/workflows/adaptive-canonical-diagnostic.yml"
ADAPTIVE = ".github/workflows/joint-path-promotion-audit.yml"


def _workflow(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_direct_pull_request_certification_checks_out_exact_head_sha():
    expected = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
    for path in DIRECT_PR_CERTIFICATION_WORKFLOWS:
        assert expected in _workflow(path), path


def test_adaptive_certification_reuses_exact_canonical_release_transaction():
    adaptive = _workflow(ADAPTIVE)
    canonical = _workflow(CANONICAL)

    assert "workflow_call:" in canonical
    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in adaptive
    assert "secrets: inherit" in adaptive
    # The caller intentionally owns no second checkout/solver implementation: exact
    # head checkout and the whole release transaction live in the called workflow.
    assert "actions/checkout@v4" not in adaptive
    assert "build_open_solver_parity_input.py" not in adaptive


def test_canonical_release_transaction_uses_run_scoped_generation_and_sealed_parity():
    workflow = _workflow(CANONICAL)
    assert "data/generated/runs/${{ github.run_id }}" in workflow
    assert "build_open_solver_parity_input.py" in workflow
    assert "run_open_solver_parity.py" in workflow
    assert 'export_open_solver.py "$BUNDLE_DIR"' in workflow
    assert "reports/players.csv reports/projections.csv" not in workflow
    assert "uv run python run/solve.py" not in workflow


def test_adaptive_adversarial_certification_is_mandatory_via_shared_certifier():
    adaptive = _workflow(ADAPTIVE)
    canonical = _workflow(CANONICAL)
    certifier = (ROOT / "scripts/certify_release_generation.py").read_text(encoding="utf-8")

    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in adaptive
    assert "Certify adversarial, bench-stress, mechanics and promotion gates" in canonical
    assert "scripts/certify_release_generation.py" in canonical
    assert "scripts/run_adversarial_launch_ban.py" in certifier
    assert "scripts/certify_adversarial_launch_ban.py" in certifier
    assert "scripts/audit_bench_stress.py" in certifier
    assert "scripts/promote_certified_generation.py" in certifier
    # The certification step itself is conditional only on successful canonical
    # assembly; there is no always()/best-effort escape hatch around the certifier.
    section = canonical.split(
        "- name: Certify adversarial, bench-stress, mechanics and promotion gates", 1
    )[1].split("- name: Summarize canonical diagnostics", 1)[0]
    assert "if: always()" not in section
    assert "if: steps.canonical.outputs.exit_code == '0'" in section


def test_manual_readiness_replays_exact_production_promotion_transaction():
    workflow = _workflow(".github/workflows/production-readiness.yml")
    assert "data/generated/runs/${{ github.run_id }}" in workflow
    assert "build_open_solver_parity_input.py" in workflow
    assert "run_open_solver_parity.py" in workflow
    assert "promote_certified_generation.py" in workflow
    assert "git push" not in workflow
