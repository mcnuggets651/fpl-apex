from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-daily-production.yml"


class ApexProprietaryProductionWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_apex_proprietary_shadow_is_generated_before_freeze(self) -> None:
        step = "Generate Apex Proprietary H1-H8 shadow"
        runner = "scripts/acquire_apex_proprietary_shadow.py"
        output = "acquisition/providers/apex_proprietary.csv"
        freeze = "Re-anchor Official truth and freeze all inputs once"
        for needle in (step, runner, output, "--expected-official-hash", "--horizon 8"):
            self.assertIn(needle, self.text)
        self.assertLess(self.text.index(step), self.text.index(freeze))

    def test_shadow_failure_cannot_replace_serving_airsenal(self) -> None:
        start = self.text.index("- name: Generate Apex Proprietary H1-H8 shadow")
        end = self.text.index("- name: Acquire Dastan H1 shadow", start)
        block = self.text[start:end]
        self.assertIn("continue-on-error: true", block)
        self.assertNotIn("serving_provider", block)
        self.assertNotIn("apex-v2 solve", block)
        self.assertNotIn("apex-v2 publish", block)

    def test_export_is_bound_to_authority_selected_core(self) -> None:
        start = self.text.index("- name: Generate Apex Proprietary H1-H8 shadow")
        end = self.text.index("- name: Acquire Dastan H1 shadow", start)
        block = self.text[start:end]
        self.assertIn('test "$(git -C "$APEX_CORE_PATH" rev-parse HEAD)" = "$APEX_CODE_SHA"', block)
        self.assertIn('python "$APEX_CORE_PATH/scripts/acquire_apex_proprietary_shadow.py"', block)
        self.assertIn('--code-sha "$APEX_CODE_SHA"', block)


if __name__ == "__main__":
    unittest.main()
