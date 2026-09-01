from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apex_v2_tournament_source_resolver as resolver  # noqa: E402


NOW = datetime(2026, 9, 1, 22, 15, tzinfo=timezone.utc)
SEASON = "2026-2027"


def release(run_id: str, *, assets=("public_attempt.json",), immutable=True, draft=False):
    return {
        "id": int(run_id.split("-")[0]),
        "tag_name": f"apex-v2/final/{SEASON}/{run_id}",
        "immutable": immutable,
        "draft": draft,
        "assets": [{"name": name} for name in assets],
    }


def attempt(
    run_id: str,
    *,
    gameweek=3,
    frozen_at="2026-09-01T20:00:00Z",
    deadline="2026-09-04T17:30:00Z",
    actionable=True,
    personalized=True,
    serving="airsenal",
):
    return {
        "run_id": run_id,
        "season": SEASON,
        "target_gameweek": gameweek,
        "frozen_at": frozen_at,
        "certification": {"valid_until": deadline, "actionable": actionable},
        "manager_actionability": {"personalized_actionable": personalized},
        "serving_provider_by_horizon": {str(h): serving for h in range(1, 9)},
    }


class TournamentSourceResolverTests(unittest.TestCase):
    def resolve(self, releases, payloads):
        def load(row):
            return payloads[row["tag_name"]]

        return resolver.select_latest_eligible_source(
            releases,
            season=SEASON,
            now=NOW,
            load_public_attempt=load,
        )

    def test_legacy_final_without_public_attempt_is_explicitly_skipped(self):
        legacy = release("33207047220-1", assets=())
        current = release("33469824474-1")
        payloads = {current["tag_name"]: attempt("33469824474-1")}
        result = self.resolve([legacy, current], payloads)
        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["run_id"], "33469824474-1")
        self.assertEqual(result["rejection_counts"][resolver.MISSING_PUBLIC_ATTEMPT_ASSET], 1)
        self.assertEqual(result["examined_final_release_count"], 2)

    def test_release_list_asset_race_is_skipped_not_fatal(self):
        old = release("33241007847-1")
        current = release("33469824474-1")

        def load(row):
            if row["tag_name"] == old["tag_name"]:
                raise FileNotFoundError("legacy/race")
            return attempt("33469824474-1")

        result = resolver.select_latest_eligible_source(
            [old, current],
            season=SEASON,
            now=NOW,
            load_public_attempt=load,
        )
        self.assertEqual(result["run_id"], "33469824474-1")
        self.assertEqual(result["rejection_counts"][resolver.MISSING_PUBLIC_ATTEMPT_ASSET], 1)

    def test_earliest_future_deadline_then_latest_frozen_at(self):
        a = release("34000000001-1")
        b = release("34000000002-1")
        c = release("34000000003-1")
        payloads = {
            a["tag_name"]: attempt(
                "34000000001-1",
                frozen_at="2026-09-01T18:00:00Z",
                deadline="2026-09-04T17:30:00Z",
            ),
            b["tag_name"]: attempt(
                "34000000002-1",
                frozen_at="2026-09-01T21:00:00Z",
                deadline="2026-09-04T17:30:00Z",
            ),
            c["tag_name"]: attempt(
                "34000000003-1",
                frozen_at="2026-09-01T21:30:00Z",
                deadline="2026-09-11T17:30:00Z",
            ),
        }
        result = self.resolve([a, b, c], payloads)
        self.assertEqual(result["run_id"], "34000000002-1")
        self.assertEqual(result["selection_policy"], resolver.SELECTION_POLICY)

    def test_expired_or_nonactionable_finals_are_accounted_for(self):
        expired = release("33000000001-1")
        blocked = release("33000000002-1")
        payloads = {
            expired["tag_name"]: attempt(
                "33000000001-1", deadline="2026-09-01T20:00:00Z"
            ),
            blocked["tag_name"]: attempt("33000000002-1", actionable=False),
        }
        result = self.resolve([expired, blocked], payloads)
        self.assertEqual(result["status"], "NO_ELIGIBLE_SOURCE")
        self.assertEqual(result["rejection_counts"]["DEADLINE_PASSED"], 1)
        self.assertEqual(result["rejection_counts"]["PRODUCTION_NOT_ACTIONABLE"], 1)

    def test_modern_run_identity_mismatch_fails_closed(self):
        current = release("33469824474-1")
        with self.assertRaisesRegex(resolver.SourceResolutionError, "run identity mismatch"):
            self.resolve(
                [current],
                {current["tag_name"]: attempt("99999999999-1")},
            )

    def test_modern_serving_authority_drift_fails_closed(self):
        current = release("33469824474-1")
        with self.assertRaisesRegex(resolver.SourceResolutionError, "serving authority drift"):
            self.resolve(
                [current],
                {current["tag_name"]: attempt("33469824474-1", serving="dastan")},
            )

    def test_personalized_actionability_is_required(self):
        current = release("33469824474-1")
        result = self.resolve(
            [current],
            {current["tag_name"]: attempt("33469824474-1", personalized=False)},
        )
        self.assertEqual(result["status"], "NO_ELIGIBLE_SOURCE")
        self.assertEqual(result["rejection_counts"]["MANAGER_NOT_ACTIONABLE"], 1)


if __name__ == "__main__":
    unittest.main()
