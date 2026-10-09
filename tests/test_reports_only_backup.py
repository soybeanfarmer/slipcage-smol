"""Reports-only snapshots must preserve legacy SQLite archives and scratch-restore."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(filename):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"),
        ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

backup = load("slipcage-backup.py")
restore = load("slipcage-restore-check.py")
health = load("slipcage-health.py")
NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)

class ReportsOnlyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "research.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE candidates (id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO candidates VALUES ('legacy')")
        self.reports = self.root / "reports"
        self.reports.mkdir()
        (self.reports / "first.md").write_text("Original research evidence\n")
        self.destination = self.root / "backups"

    def test_new_reports_backup_retains_legacy_db_archive(self):
        old = Path(backup.create_backup(self.db, self.reports,
                    self.destination, now=NOW)["backup"])
        for idx in range(3):
            backup.create_reports_backup(self.reports, self.destination, keep=2,
                     now=NOW + timedelta(seconds=idx + 1))
        self.assertTrue(old.exists())
        self.assertEqual(backup.verify_backup(old)["format"], 1)
        latest = max(self.destination.glob("reports-*"))
        self.assertEqual(backup.verify_backup(latest)["format"], 2)
        self.assertFalse((latest / "research.sqlite3").exists())
        self.assertEqual(len(list(self.destination.glob("reports-*"))), 2)
        self.assertEqual(health.backup_check(self.destination,
                         NOW + timedelta(minutes=5))["latest"], latest.name)
        restored = self.root / "restored"
        self.assertEqual(restore.drill(latest, restored)["format"], 2)
        self.assertEqual((restored / "reports" / "first.md").read_text(),
                         "Original research evidence\n")
        self.assertFalse((restored / "research.sqlite3").exists())
        self.assertEqual(backup.check_sqlite(self.db), 1)

    def test_missing_database_does_not_block_reports_backup(self):
        self.db.unlink()
        result = backup.create_reports_backup(self.reports, self.destination, now=NOW)
        self.assertTrue(backup.verify_backup(Path(result["backup"]))["verified"])

    def test_tamper_or_symlink_fails_closed(self):
        result = backup.create_reports_backup(self.reports, self.destination, now=NOW)
        source = Path(result["backup"])
        (source / "reports.tar.gz").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            restore.drill(source, self.root / "restored")
        (self.reports / "bad.md").symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            backup.create_reports_backup(self.reports, self.destination,
                                         now=NOW + timedelta(seconds=1))

if __name__ == "__main__":
    unittest.main()
