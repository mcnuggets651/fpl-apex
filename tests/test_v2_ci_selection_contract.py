from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_ci_runs_all_v2_test_name_families():
    workflow = (ROOT / ".github/workflows/apex-v2-ci.yml").read_text(encoding="utf-8")
    assert "tests/test_apex_v2_*.py" in workflow
    assert "tests/test_v2_*.py" in workflow
    assert "'tests/test_apex_v2_*.py'" in workflow


def test_adversarial_audit_runs_all_v2_test_name_families():
    workflow = (
        ROOT / ".github/workflows/apex-v2-adversarial-audit.yml"
    ).read_text(encoding="utf-8")
    assert "tests/test_apex_v2_*.py" in workflow
    assert "tests/test_v2_*.py" in workflow
