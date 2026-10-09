#!/usr/bin/env python3
"""Bounded, attempt-fenced SQLite-native review runner for systemd."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

import isolab
import recovery

MAX_REVIEWS_PER_RUN = 10


def run_reviews(db: str, reports: str, max_reviews: int = 3) -> dict:
    """Process bounded pending metadata reviews using existing SQLite fencing.

    Only one attempt may be outstanding at a time. Any previously queued or
    running attempt blocks dispatch instead of racing a Dagu worker.
    Successful reports keep the existing stable filename and attempt token.
    An exception leaves the SQLite attempt for conservative later recovery.
    """
    if not 1 <= max_reviews <= MAX_REVIEWS_PER_RUN:
        raise ValueError("max_reviews must be between 1 and 10")
    conn = isolab.connect(db)
    try:
        reconciliation = recovery.reconcile(conn)
        completed = 0
        for _ in range(max_reviews):
            claim = recovery.claim_next(conn, 1)
            if claim is None:
                break
            candidate_id, attempt = claim
            # run_review atomically validates this exact attempt and writes a
            # stable, metadata-only report before marking it reviewed.
            result = isolab.run_review(db, reports, candidate_id, attempt)
            state = conn.execute(
                "SELECT status FROM candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            if result != 0 or state is None or state["status"] != "reviewed":
                raise RuntimeError("Review attempt did not finish; operator review required")
            completed += 1
        return {"reviews_completed": completed, "reconciliation": reconciliation}
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--reports", required=True)
    p.add_argument("--max-reviews", type=int, default=3)
    args = p.parse_args(argv)
    try:
        print(json.dumps(run_reviews(args.db, args.reports, args.max_reviews),
                         sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        print(f"local review worker failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
