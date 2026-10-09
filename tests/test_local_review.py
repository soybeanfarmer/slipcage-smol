"""Offline, no-Dagu review runner regression tests.

No systemd unit invokes this module until a separate gated migration.
"""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import isolab
import local_review
import recovery


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = str(self.root / "research.sqlite3")
        self.reports = str(self.root / "reports")
        self.conn = isolab.connect(self.db)

    def tearDown(self):
        self.conn.close()

    def add_candidate(self, index: int) -> str:
        candidate_id = f"{index:064x}"
        with self.conn:
            self.conn.execute(
                """INSERT INTO candidates
                (id, source, source_id, cve, title, summary, reference_url,
                 track, score, discovered_at, status)
                VALUES (?, 'github', ?, NULL, 'QEMU advisory', 'metadata only',
                        'https://github.com/advisories', 'hypervisor',
                        65, '2026-10-09T12:00:00+00:00', 'pending')""",
                (candidate_id, f"GHSA-fixture-{index}"),
            )
        return candidate_id

    def status(self, candidate_id: str) -> str:
        row = self.conn.execute(
            "SELECT status FROM candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        return row["status"]

    def test_one_review_succeeds_and_does_not_repeat(self):
        candidate = self.add_candidate(1)
        first = local_review.run_reviews(self.db, self.reports)
        self.assertEqual(first["reviews_completed"], 1)
        self.assertEqual(self.status(candidate), "reviewed")
        self.assertEqual(len(list(Path(self.reports).glob("candidate-*.md"))), 1)
        second = local_review.run_reviews(self.db, self.reports)
        self.assertEqual(second["reviews_completed"], 0)
        self.assertEqual(len(list(Path(self.reports).glob("candidate-*.md"))), 1)

    def test_per_run_budget_is_bounded(self):
        candidates = [self.add_candidate(i) for i in range(1, 5)]
        self.assertEqual(local_review.run_reviews(
            self.db, self.reports, 2)["reviews_completed"], 2)
        self.assertEqual(sum(self.status(x) == "reviewed" for x in candidates), 2)
        self.assertEqual(local_review.run_reviews(
            self.db, self.reports, 2)["reviews_completed"], 2)
        self.assertTrue(all(self.status(x) == "reviewed" for x in candidates))

    def test_legacy_untracked_queue_blocks_dispatch(self):
        blocked = self.add_candidate(1)
        pending = self.add_candidate(2)
        with self.conn:
            self.conn.execute(
                "UPDATE candidates SET status='queued' WHERE id=?", (blocked,)
            )
        result = local_review.run_reviews(self.db, self.reports)
        self.assertEqual(result["reviews_completed"], 0)
        self.assertEqual(result["reconciliation"]["legacy_untracked"], 1)
        self.assertEqual(self.status(blocked), "queued")
        self.assertEqual(self.status(pending), "pending")
        self.assertFalse(Path(self.reports).exists())

    def test_live_existing_attempt_blocks_new_dispatch(self):
        blocked = self.add_candidate(1)
        pending = self.add_candidate(2)
        claimed = recovery.claim_next(self.conn, 1)
        self.assertEqual(claimed[0], blocked)
        result = local_review.run_reviews(self.db, self.reports)
        self.assertEqual(result["reviews_completed"], 0)
        self.assertEqual(self.status(pending), "pending")

    def test_report_failure_preserves_attempt_for_reconciliation(self):
        candidate = self.add_candidate(1)
        with patch.object(local_review.isolab, "report",
                          side_effect=OSError("synthetic report failure")):
            with self.assertRaises(OSError):
                local_review.run_reviews(self.db, self.reports)
        self.assertEqual(self.status(candidate), "running")
        self.assertEqual(self.conn.execute(
            "SELECT state FROM review_attempts WHERE candidate_id=?",
            (candidate,),
        ).fetchone()["state"], "running")

    def test_budget_out_of_range_rejected_before_db_changes(self):
        for budget in (0, 11, -1):
            with self.assertRaises(ValueError):
                local_review.run_reviews(self.db, self.reports, budget)
        self.assertFalse(Path(self.db + ".missing").exists())


if __name__ == "__main__":
    unittest.main()
