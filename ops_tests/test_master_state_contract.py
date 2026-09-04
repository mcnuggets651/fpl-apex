from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_master_state_sync.py"
MASTER = "docs/FPL_APEX_MASTER_STATE.md"


class MasterStateContractTests(unittest.TestCase):
    def run_guard(self, *paths: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), "--paths", *paths],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_master_only_change_is_legal(self) -> None:
        result = self.run_guard(MASTER)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_change_with_master_update_is_legal(self) -> None:
        result = self.run_guard("src/example.py", MASTER)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_change_without_master_update_is_rejected(self) -> None:
        result = self.run_guard("src/example.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("master-state continuity violation", result.stderr)

    def test_agent_contracts_force_master_preflight(self) -> None:
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(MASTER, text)
            self.assertIn("APEX_V2_AUTHORITY.json", text)

    def test_required_ci_runs_guard(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "apex.yml").read_text(
            encoding="utf-8"
        )
        marker = "python scripts/check_master_state_sync.py"
        self.assertIn(marker, workflow)
        self.assertLess(
            workflow.index(marker),
            workflow.index("Run live V2 operations regressions"),
            "master-state guard must execute before the operations regression suite",
        )

    def test_master_records_current_machine_authority_and_run(self) -> None:
        text = (ROOT / MASTER).read_text(encoding="utf-8")
        self.assertIn("c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437", text)
        self.assertIn("99cc7b51b0cff45462b567084cb1844cfe0a456f", text)
        self.assertIn("33850307770-1", text)
        self.assertIn(
            "PRODUCTION PIPELINE PASSED; PRIVATE QUERY ACCEPTANCE BLOCKED BY GITHUB BILLING",
            text,
        )


if __name__ == "__main__":
    unittest.main()
