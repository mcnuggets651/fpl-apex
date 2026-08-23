from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ".github/workflows/adaptive-canonical-diagnostic.yml"
ADAPTIVE = ".github/workflows/joint-path-promotion-audit.yml"
READINESS = ".github/workflows/production-readiness.yml"
DIRECT_PR_CERTIFICATION_WORKFLOWS = (
    ".github/workflows/apex.yml",
    ".github/workflows/projection-policy-audit.yml",
    ".github/workflows/projection-shadow-audit.yml",
    CANONICAL,
    ADAPTIVE,
    ".github/workflows/team-strength-validation.yml",
    ".github/workflows/understat-player-production-ab.yml",
)


def _workflow(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _jobs(path: str) -> str:
    text = _workflow(path)
    assert "\njobs:\n" in text, path
    return text.split("\njobs:\n", 1)[1]


def test_direct_pull_request_certification_checks_out_exact_head_sha():
    expected = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
    for path in DIRECT_PR_CERTIFICATION_WORKFLOWS:
        assert expected in _jobs(path), path


def test_canonical_is_the_only_live_pr_release_transaction():
    canonical = _jobs(CANONICAL)
    adaptive = _jobs(ADAPTIVE)

    assert "build_open_solver_parity_input.py" in canonical
    assert "run_open_solver_parity.py" in canonical
    assert "scripts/certify_release_generation.py" in canonical
    assert "data/generated/runs/${{ github.run_id }}" in canonical

    assert "build_open_solver_parity_input.py" not in adaptive
    assert "run_open_solver_parity.py" not in adaptive
    assert "run_airsenal_worker.py" not in adaptive
    assert "Prove lifecycle-specific release contracts" in adaptive


def test_manual_readiness_reuses_canonical_transaction_without_a_second_copy():
    jobs = _jobs(READINESS)
    assert "uses: ./.github/workflows/adaptive-canonical-diagnostic.yml" in jobs
    assert "secrets: inherit" in jobs
    assert "run_pinnacle.py" not in jobs
    assert "promote_certified_generation.py" not in jobs


def test_no_workflow_uses_runner_context_in_job_level_environment():
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (payload.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            env = job.get("env") or {}
            for key, value in env.items():
                assert "runner.temp" not in str(value), f"{path.name}:{job_name}:env.{key}"


def test_lifecycle_specific_sensitivity_is_owned_by_python_certifier():
    certifier = (ROOT / "scripts/certify_release_generation.py").read_text(encoding="utf-8")
    assert "resolve_release_profile" in certifier
    assert "scripts/run_adversarial_launch_ban.py" in certifier
    assert "scripts/audit_inseason_action_sensitivity.py" in certifier
    assert "profile == LAUNCH_PROFILE" in certifier
    assert "profile == INSEASON_PROFILE" in certifier
    assert "scripts/audit_bench_stress.py" in certifier
    assert "scripts/promote_certified_generation.py" in certifier
