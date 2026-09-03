from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class V2ControlPlaneAuthorityTests(unittest.TestCase):
    def test_required_ci_has_no_legacy_runtime_authority(self):
        text = (ROOT / ".github/workflows/apex.yml").read_text(encoding="utf-8")

        forbidden_exec_patterns = (
            r"(?m)^\s*(?:python\s+)?scripts/run_apex\.py(?:\s|$)",
            r"(?m)^\s*(?:python\s+)?scripts/run_pinnacle\.py(?:\s|$)",
            r"(?m)^\s*apex-fpl(?:\s|$)",
            r"(?m)^\s*from\s+apex_fpl(?:\.|\s)",
            r"(?m)^\s*import\s+apex_fpl(?:\.|\s|$)",
        )
        for pattern in forbidden_exec_patterns:
            self.assertIsNone(re.search(pattern, text), pattern)

        for forbidden_artifact in (
            "data/generated/apex_recommendation_latest",
            "data/generated/pinnacle_latest",
            "data/generated/elite_latest",
        ):
            self.assertNotIn(forbidden_artifact, text)

        for required in (
            "docs/APEX_V2_AUTHORITY.json",
            'authority["production_core_sha"]',
            "git worktree add --detach",
            "ops_tests",
            "check_v2_architecture.py",
            "tests/test_apex_v2_*.py",
            "tests/test_v2_*.py",
        ):
            self.assertIn(required, text)

    def test_required_ci_uses_core_lock_when_available(self):
        text = (ROOT / ".github/workflows/apex.yml").read_text(encoding="utf-8")
        for required in (
            'if [ -f "$CORE/requirements-v2.lock" ]; then',
            'PIP_PIN="$(grep -E \'^pip==\' "$CORE/requirements-v2.lock")"',
            'SETUPTOOLS_PIN="$(grep -E \'^setuptools==\' "$CORE/requirements-v2.lock")"',
            'WHEEL_PIN="$(grep -E \'^wheel==\' "$CORE/requirements-v2.lock")"',
            '--no-build-isolation',
            '-c "$CORE/requirements-v2.lock" -e "$CORE[dev]"',
            'python scripts/check_v2_dependency_lock.py requirements-v2.lock',
            "python -m pip check",
        ):
            self.assertIn(required, text)
        # Both the fast operations job and the full readiness job must install the
        # exact core using the same lock-aware contract.
        self.assertGreaterEqual(text.count('if [ -f "$CORE/requirements-v2.lock" ]; then'), 2)
        self.assertGreaterEqual(text.count("--no-build-isolation"), 2)

    def test_ops_contract_never_installs_or_imports_main_legacy_runtime(self):
        text = (ROOT / ".github/workflows/apex-v2-ops-contract.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("python -m pip install -e .", text)
        self.assertNotIn("${{ github.workspace }}/src", text)
        self.assertIn('python -m pip install -e "$RUNNER_TEMP/frozen-apex[dev]"', text)
        self.assertIn(
            "PYTHONPATH: ${{ runner.temp }}/frozen-apex/src:${{ github.workspace }}/scripts",
            text,
        )
        for required in (
            "production_core_sha",
            "frozen_engine_sha",
            "git merge-base --is-ancestor",
        ):
            self.assertIn(required, text)

    def test_manual_readiness_is_read_only_reproducible_candidate_rehearsal(self):
        text = (ROOT / ".github/workflows/production-readiness.yml").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "run_apex.py",
            "run_pinnacle.py",
            "apex_recommendation_latest",
            "pinnacle_latest",
            "elite_latest",
            "ODDS_API_KEY",
            "ODDS_API_URL",
            "APEX_NEWS_FEEDS",
            "contents: write",
            "secrets.",
        ):
            self.assertNotIn(forbidden, text)
        for required in (
            "workflow_dispatch:",
            "candidate_sha:",
            "docs/APEX_V2_AUTHORITY.json",
            'authority["production_core_sha"]',
            'authority["frozen_engine_sha"]',
            "git merge-base --is-ancestor",
            "git worktree add --detach",
            'python-version: "3.12.14"',
            "requirements-v2.lock",
            "--no-build-isolation",
            "check_v2_dependency_lock.py",
            "build_v2_provenance.py",
            "check_v2_architecture.py",
            "check_v2_critical_coverage.py",
            "run_v2_mutation_sentinels.py",
            "mode=non-serving-candidate",
            "provenance.json",
            "sbom.cdx.json",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "contents: read",
        ):
            self.assertIn(required, text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("push:\n", text)

    def test_authority_separates_immutable_base_from_serving_pointer(self):
        authority = json.loads(
            (ROOT / "docs/APEX_V2_AUTHORITY.json").read_text(encoding="utf-8")
        )
        self.assertEqual(authority["frozen_engine_sha"], FROZEN_SHA)
        self.assertEqual(authority["frozen_engine_pr"], 90)
        self.assertEqual(
            authority["frozen_engine_pr_policy"],
            "NEVER_MERGE_OR_ADVANCE",
        )
        self.assertRegex(authority["production_core_sha"], SHA40)

        production = (
            ROOT / ".github/workflows/apex-v2-daily-production.yml"
        ).read_text(encoding="utf-8")
        for required in (
            'authority["production_core_sha"]',
            'authority["frozen_engine_sha"]',
            "git merge-base --is-ancestor",
            "APEX_CORE_PATH",
            'echo "APEX_CODE_SHA=$PRODUCTION_CORE_SHA"',
            '--source "$APEX_CORE_PATH/config/apex_v2.yaml"',
            '"$APEX_CORE_PATH/scripts/run_airsenal_worker.py"',
            'python "$APEX_CORE_PATH/scripts/check_v2_architecture.py"',
        ):
            self.assertIn(required, production)
        self.assertNotIn(
            f'APEX_CODE_SHA: "{FROZEN_SHA}"',
            production,
        )
        self.assertNotIn("ref: ${{ env.APEX_CODE_SHA }}", production)

    def test_production_intent_snapshot_and_final_bind_exact_serving_core(self):
        production = (
            ROOT / ".github/workflows/apex-v2-daily-production.yml"
        ).read_text(encoding="utf-8")
        for required in (
            'echo "APEX_CODE_SHA=$PRODUCTION_CORE_SHA" >> "$GITHUB_ENV"',
            '--code-sha "$APEX_CODE_SHA")',
            '--code-sha "$APEX_CODE_SHA" \\\n            --run-started-at',
            '--code-sha "$APEX_CODE_SHA"',
            'test "$(git -C "$APEX_CORE_PATH" rev-parse HEAD)" = "$APEX_CODE_SHA"',
        ):
            self.assertIn(required, production)
        self.assertGreaterEqual(production.count('--code-sha "$APEX_CODE_SHA"'), 3)

    def test_authority_keeps_legacy_nonserving_and_one_v2_publisher(self):
        authority = json.loads(
            (ROOT / "docs/APEX_V2_AUTHORITY.json").read_text(encoding="utf-8")
        )
        self.assertEqual(authority["legacy"]["status"], "HISTORICAL_NON_SERVING")
        self.assertEqual(
            authority["canonical_production_workflow"],
            ".github/workflows/apex-v2-daily-production.yml",
        )
        self.assertEqual(authority["serving_provider"], "airsenal")
        self.assertFalse(authority["research"]["automatic_promotion"])
        self.assertEqual(authority["research"]["production_influence"], "NONE")
        champion = authority["provider_constitution"][authority["serving_provider"]]
        self.assertEqual(champion["role"], "CHAMPION")
        self.assertTrue(champion["serve_authorized"])


if __name__ == "__main__":
    unittest.main()
