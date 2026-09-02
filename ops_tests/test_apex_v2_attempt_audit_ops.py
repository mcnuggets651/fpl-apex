from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_attempt_audit_ops.py"
    spec = importlib.util.spec_from_file_location("apex_v2_attempt_audit_ops", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def _release(
    tag: str,
    *,
    draft: bool = False,
    immutable: bool = True,
    prerelease: bool = False,
    published_at: str | None = "2026-09-02T12:00:00Z",
):
    return {
        "tag_name": tag,
        "draft": draft,
        "immutable": immutable,
        "prerelease": prerelease,
        "published_at": published_at,
    }


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

    def test_release_integrity_accepts_only_published_immutable_attempt_records(self):
        releases = [
            _release("apex-v2/intent/2026-2027/1-1"),
            _release("apex-v2/final/2026-2027/1-1"),
            _release("apex-v2/outcome/2026-2027/1-1"),
            _release("apex-v2/evaluation/2026-2027/1-1"),
        ]
        seen = ops.validate_release_integrity(releases)
        self.assertEqual(len(seen), 4)

    def test_draft_final_cannot_hide_a_missing_immutable_final(self):
        releases = [
            _release("apex-v2/intent/2026-2027/2-1"),
            _release(
                "apex-v2/final/2026-2027/2-1",
                draft=True,
                immutable=False,
                published_at=None,
            ),
        ]
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "final/2026-2027/2-1"):
            ops.validate_release_integrity(releases)

    def test_draft_evaluation_cannot_poison_future_retry(self):
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "evaluation/2026-2027/3-1"):
            ops.validate_release_integrity(
                [
                    _release(
                        "apex-v2/evaluation/2026-2027/3-1",
                        draft=True,
                        immutable=False,
                        published_at=None,
                    )
                ]
            )

    def test_published_but_mutable_v2_record_fails_closed(self):
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "not-immutable"):
            ops.validate_release_integrity(
                [_release("apex-v2/final/2026-2027/4-1", immutable=False)]
            )

    def test_prerelease_v2_record_fails_closed(self):
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "prerelease"):
            ops.validate_release_integrity(
                [_release("apex-v2/final/2026-2027/5-1", prerelease=True)]
            )

    def test_duplicate_v2_release_tag_fails_closed(self):
        row = _release("apex-v2/final/2026-2027/6-1")
        with self.assertRaisesRegex(ops.AttemptAuditOpsError, "duplicate"):
            ops.validate_release_integrity([row, dict(row)])

    def test_unrelated_research_release_does_not_inherit_production_contract(self):
        # Tournament releases have their own contract and must not be silently
        # reclassified as production-attempt records by this controller.
        seen = ops.validate_release_integrity(
            [
                _release(
                    "apex-v2/tournament-diagnostic/2026-2027/gw2",
                    immutable=False,
                )
            ]
        )
        self.assertEqual(seen, ())


if __name__ == "__main__":
    unittest.main()
