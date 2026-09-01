from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ops_tests"))

import apex_v2_tournament_contract as contract  # noqa: E402
from test_apex_v2_tournament_ops import base_inputs  # noqa: E402


class TournamentSealTimingTests(unittest.TestCase):
    def build_at(self, when: datetime):
        args = base_inputs()
        return contract.build_readiness(
            args[0],
            args[1],
            args[2],
            source_release=args[6],
            internal_surface_sha256=args[3],
            pitchside_capture=args[4],
            openfpl_readiness=args[5],
            private_base_release_tag="private",
            private_tournament_release_tag="supplement",
            candidate_sealed_at=when,
        )

    def test_postdeadline_candidate_cannot_be_ready(self):
        result = self.build_at(
            datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc)
        )
        self.assertFalse(result["tournament_ready"])
        self.assertFalse(
            result["common_seal"]["eligible_common_predeadline_candidate"]
        )
        self.assertIn(
            "prospective tournament candidate itself was not sealed before the Official deadline",
            result["readiness_blockers"],
        )

    def test_predeadline_candidate_records_exact_tournament_seal_time(self):
        when = datetime(2026, 9, 4, 17, 20, tzinfo=timezone.utc)
        result = self.build_at(when)
        self.assertTrue(result["tournament_ready"])
        self.assertEqual(
            result["common_seal"]["tournament_sealed_at"],
            when.isoformat(),
        )

    def test_selection_rejects_forged_postdeadline_seal(self):
        result = self.build_at(
            datetime(2026, 9, 4, 17, 20, tzinfo=timezone.utc)
        )
        result["common_seal"]["tournament_sealed_at"] = (
            "2026-09-04T17:30:00+00:00"
        )
        selected = contract.select_latest_valid_common_seal(
            [result],
            gameweek=3,
            as_of=datetime(2026, 9, 4, 18, 0, tzinfo=timezone.utc),
            require_cutoff_passed=True,
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
