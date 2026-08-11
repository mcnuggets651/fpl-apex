from pathlib import Path
import subprocess
import sys


def test_governance_contract_is_machine_enforced():
    result = subprocess.run(
        [sys.executable, "scripts/check_governance_consistency.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path("src/apex_fpl/services/answer_context.py").exists()
