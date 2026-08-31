from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts.apex_v2_deadline_ops import (
    decide_deadline_window,
    has_existing_deadline_run,
    next_official_deadline,
    run_watch,
)


def event(gw: int, deadline: str) -> dict:
    return {"id": gw, "deadline_time": deadline}


class DeadlineLogicTests(unittest.TestCase):
    NOW = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)

    def test_selects_earliest_future_deadline_not_list_order(self):
        payload = {"events": [event(4, "2026-09-12T10:00:00Z"), event(3, "2026-09-04T17:30:00Z")]}
        gw, deadline = next_official_deadline(payload, self.NOW)
        self.assertEqual(gw, 3)
        self.assertEqual(deadline.isoformat(), "2026-09-04T17:30:00+00:00")

    def test_in_window_is_eligible_at_both_boundaries(self):
        payload = {"events": [event(3, "2026-09-04T17:30:00Z")]}
        for minutes in (90, 150):
            now = datetime.fromtimestamp(
                datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc).timestamp() - minutes * 60,
                tz=timezone.utc,
            )
            decision = decide_deadline_window(payload, now=now)
            self.assertTrue(decision.eligible)
            self.assertEqual(decision.reason, "IN_WINDOW")

    def test_too_early_and_too_close_do_not_dispatch(self):
        payload = {"events": [event(3, "2026-09-04T17:30:00Z")]}
        early = decide_deadline_window(payload, now=datetime(2026, 9, 4, 14, 59, tzinfo=timezone.utc))
        close = decide_deadline_window(payload, now=datetime(2026, 9, 4, 16, 1, tzinfo=timezone.utc))
        self.assertEqual((early.eligible, early.reason), (False, "TOO_EARLY"))
        self.assertEqual((close.eligible, close.reason), (False, "TOO_CLOSE"))

    def test_deadline_change_is_taken_from_current_official_payload(self):
        a = {"events": [event(3, "2026-09-04T17:30:00Z")]}
        b = {"events": [event(3, "2026-09-04T18:30:00Z")]}
        self.assertTrue(decide_deadline_window(a, now=self.NOW).eligible)
        self.assertFalse(decide_deadline_window(b, now=self.NOW).eligible)

    def test_malformed_or_missing_future_deadline_fails_closed(self):
        with self.assertRaises(RuntimeError):
            next_official_deadline({}, self.NOW)
        with self.assertRaises(RuntimeError):
            next_official_deadline({"events": [{"id": 3}]}, self.NOW)
        with self.assertRaises(RuntimeError):
            next_official_deadline({"events": [event(2, "2026-08-30T10:00:00Z")]}, self.NOW)

    def test_malformed_unfinished_event_fails_closed_even_if_later_deadline_is_valid(self):
        payload = {
            "events": [
                {"id": 3, "deadline_time": None, "finished": False},
                event(4, "2026-09-12T10:00:00Z"),
            ]
        }
        with self.assertRaises(RuntimeError):
            next_official_deadline(payload, self.NOW)

    def test_any_manual_dispatch_inside_current_deadline_window_counts_regardless_of_conclusion(self):
        deadline = datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc)
        for conclusion in ("success", "failure", None):
            runs = {"workflow_runs": [{"event": "workflow_dispatch", "created_at": "2026-09-04T15:30:00Z", "conclusion": conclusion}]}
            self.assertTrue(has_existing_deadline_run(runs, deadline=deadline, min_minutes=90, max_minutes=150))

    def test_scheduled_or_outside_window_run_does_not_count(self):
        deadline = datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc)
        scheduled = {"workflow_runs": [{"event": "schedule", "created_at": "2026-09-04T15:30:00Z"}]}
        old_manual = {"workflow_runs": [{"event": "workflow_dispatch", "created_at": "2026-09-04T13:00:00Z"}]}
        self.assertFalse(has_existing_deadline_run(scheduled, deadline=deadline, min_minutes=90, max_minutes=150))
        self.assertFalse(has_existing_deadline_run(old_manual, deadline=deadline, min_minutes=90, max_minutes=150))

    @patch("scripts.apex_v2_deadline_ops._json_request")
    def test_far_from_deadline_never_touches_github_runs_or_dispatch(self, request):
        request.return_value = (200, {"events": [event(3, "2026-09-04T20:30:00Z")]})
        result = run_watch(repository="o/r", token="x", ref="main", now=self.NOW, min_minutes=90, max_minutes=150)
        self.assertEqual(result["dispatch"], "NOT_ATTEMPTED")
        self.assertEqual(request.call_count, 1)

    @patch("scripts.apex_v2_deadline_ops._json_request")
    def test_eligible_dispatches_exactly_once_with_metadata(self, request):
        request.side_effect = [
            (200, {"events": [event(3, "2026-09-04T17:30:00Z")]}),
            (200, {"workflow_runs": []}),
            (204, None),
        ]
        result = run_watch(repository="o/r", token="x", ref="main", now=self.NOW, min_minutes=90, max_minutes=150)
        self.assertEqual(result["dispatch"], "DISPATCHED")
        payload = request.call_args_list[2].kwargs["payload"]
        self.assertEqual(payload, {"ref": "main"})

    @patch("scripts.apex_v2_deadline_ops._json_request")
    def test_existing_failed_run_prevents_automatic_retry(self, request):
        request.side_effect = [
            (200, {"events": [event(3, "2026-09-04T17:30:00Z")]}),
            (200, {"workflow_runs": [{"event": "workflow_dispatch", "created_at": "2026-09-04T15:30:00Z", "conclusion": "failure"}]}),
        ]
        result = run_watch(repository="o/r", token="x", ref="main", now=self.NOW, min_minutes=90, max_minutes=150)
        self.assertEqual(result["dispatch"], "SKIPPED_ALREADY_RECORDED")
        self.assertEqual(request.call_count, 2)

    def test_non_main_ref_is_rejected(self):
        with self.assertRaises(RuntimeError):
            run_watch(repository="o/r", token="x", ref="feature", now=self.NOW, min_minutes=90, max_minutes=150)


if __name__ == "__main__":
    unittest.main()
