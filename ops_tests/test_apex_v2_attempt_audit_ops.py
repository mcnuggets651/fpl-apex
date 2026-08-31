from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_attempt_audit_ops.py"
    spec = importlib.util.spec_from_file_location("apex_v2_attempt_audit_ops", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = _load_module()


def _result(returncode: int, missing: list[str] | None = None, *, stdout: str | None = None):
    payload = {
        "intents": [],
        "finals": [],
        "missing_finals": missing or [],
        "in_progress": [],
    }
    return subprocess.CompletedProcess(
        args=["apex-v2", "audit-attempts"],
        returncode=returncode,
        stdout=json.dumps(payload) if stdout is None else stdout,
        stderr="",
    )


class AttemptAuditOperationsTests(unittest.TestCase):
    def test_clean_audit_passes(self):
        classified = ops.evaluate_result(_result(0, []))
        self.assertEqual(classified.acknowledged_missing_finals, ())
        self.assertEqual(classified.unacknowledged_missing_finals, ())

    def test_exact_acknowledged_historical_failures_pass(self):
        known = sorted(ops.ACKNOWLEDGED_FAILED_INTENTS)
        classified = ops.evaluate_result(_result(2, known))
        self.assertEqual(classified.acknowledged_missing_finals, tuple(known))
        self.assertEqual(classified.unacknowledged_missing_finals, ())

    def test_subset_of_acknowledged_historical_failures_passes(self):
        known = sorted(ops.ACKNOWLEDGED_FAILED_INTENTS)[:2]
        classified = ops.evaluate_result(_result(2, known))
        self.assertEqual(classified.acknowledged_missing_finals, tuple(known))
        self.assertEqual(classified.unacknowledged_missing_finals, ())

    def test_new_orphan_remains_hard_failure_classification(self):
        new_orphan = "apex-v2/intent/2026-2027/99999999999-1"
        known = sorted(ops.ACKNOWLEDGED_FAILED_INTENTS)[:1]
        classified = ops.evaluate_result(_result(2, known + [new_orphan]))
        self.assertEqual(classified.acknowledged_missing_finals, tuple(known))
        self.assertEqual(classified.unacknowledged_missing_finals, (new_orphan,))

    def test_malformed_json_fails_closed(self):
        with self.assertRaises(ops.AttemptAuditOpsError):
            ops.evaluate_result(_result(2, stdout="not-json"))

    def test_invalid_missing_finals_shape_fails_closed(self):
        malformed = json.dumps({"missing_finals": "not-a-list"})
        with self.assertRaises(ops.AttemptAuditOpsError):
            ops.evaluate_result(_result(2, stdout=malformed))

    def test_unexpected_frozen_cli_exit_fails_closed(self):
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "unexpectedly"):
            ops.evaluate_result(_result(1, []))

    def test_success_exit_with_missing_finals_is_rejected(self):
        known = sorted(ops.ACKNOWLEDGED_FAILED_INTENTS)[:1]
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "success"):
            ops.evaluate_result(_result(0, known))

    def test_orphan_exit_without_missing_finals_is_rejected(self):
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "without missing finals"):
            ops.evaluate_result(_result(2, []))

    def test_render_makes_acknowledgement_explicit_without_mutating_history(self):
        known = sorted(ops.ACKNOWLEDGED_FAILED_INTENTS)[:1]
        classified = ops.evaluate_result(_result(2, known))
        rendered = json.loads(ops._render(classified))
        self.assertEqual(rendered["missing_finals"], known)
        self.assertEqual(rendered["acknowledged_historical_failures"], known)
        self.assertEqual(rendered["unacknowledged_missing_finals"], [])
        self.assertTrue(rendered["operationally_clear"])


if __name__ == "__main__":
    unittest.main()
