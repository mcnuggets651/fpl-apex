from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_DOCS = (
    ROOT / "README.md",
    ROOT / "PROJECT_STATUS.md",
    ROOT / "docs/CURRENT_STATE.md",
    ROOT / "docs/APEX_MASTER_CONTEXT.md",
    ROOT / "docs/APEX_OPERATING_MANUAL.md",
    ROOT / "docs/APEX_V2_DAILY_OPERATIONS.md",
    ROOT / "docs/KNOWN_ISSUES.md",
    ROOT / "docs/CHATGPT_USAGE.md",
    ROOT / "docs/CHATGPT_APEX_QUERY_POLICY.md",
    ROOT / "docs/APEX_ROADMAP.md",
)


class V2PostPromotionAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = json.loads(
            (ROOT / "docs/APEX_V2_AUTHORITY.json").read_text(encoding="utf-8")
        )
        cls.frozen = cls.authority["frozen_engine_sha"]
        cls.production = cls.authority["production_core_sha"]

    def test_every_canonical_doc_names_both_authorities_exactly(self):
        frozen_marker = (
            f"Immutable forensic base (`frozen_engine_sha`): `{self.frozen}`"
        )
        production_marker = (
            f"Current serving core (`production_core_sha`): `{self.production}`"
        )
        for path in AUTHORITY_DOCS:
            body = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn(frozen_marker, body)
                self.assertIn(production_marker, body)
                self.assertIn("APEX_V2_AUTHORITY.json", body)
                self.assertIn("AIrsenal", body)

    def test_canonical_docs_do_not_conflate_frozen_base_with_serving_core(self):
        stale_patterns = (
            r"Apex V2 is frozen at engine SHA",
            r"Frozen certified engine",
            r"Certified engine SHA",
            r"Apex V2 frozen engine SHA",
            r"frozen Apex V2 optimiser/mechanics at",
            r"checks out(?:/proves)? the frozen engine SHA",
            r"serving recommendation .* produced by the frozen engine",
            r"serving result .* created by the frozen engine",
            r"under the frozen engine",
            r"During the authority-split migration[^\n]*remain[s]? `?99cc",
            r"during the authority-split migration[^\n]*remain `?99cc",
        )
        for path in AUTHORITY_DOCS:
            body = path.read_text(encoding="utf-8")
            for pattern in stale_patterns:
                with self.subTest(path=path, pattern=pattern):
                    self.assertIsNone(re.search(pattern, body, flags=re.IGNORECASE))

    def test_production_workflow_binds_intent_snapshot_and_publish_to_serving_core(self):
        workflow = (
            ROOT / ".github/workflows/apex-v2-daily-production.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('echo "APEX_CODE_SHA=$PRODUCTION_CORE_SHA"', workflow)
        self.assertGreaterEqual(workflow.count('--code-sha "$APEX_CODE_SHA"'), 3)
        self.assertIn(
            'test "$(git -C "$APEX_CORE_PATH" rev-parse HEAD)" = "$APEX_CODE_SHA"',
            workflow,
        )
        self.assertIn(
            'git merge-base --is-ancestor "$FROZEN_ENGINE_SHA" "$PRODUCTION_CORE_SHA"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
