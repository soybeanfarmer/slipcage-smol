"""Real local scratch-restore checks and the bounded weekly service contract."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import shutil

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


assurance = load("assurance_v10", "slipcage-assurance.py")
backup = load("backup_v10", "slipcage-backup.py")
restore = load("restore_v10", "slipcage-restore-check.py")

NOW = datetime(2026, 10, 8, 21, 0, tzinfo=timezone.utc)


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.db = self.root / "research.sqlite3"
        self.reports = self.root / "reports"
        self.reports.mkdir()
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE candidates (id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO candidates VALUES ('fixture')")
        (self.reports / "sample.md").write_text("sample harmless report", encoding="utf-8")
        self.backups = self.root / "backups"
        backup.create_backup(self.db, self.reports, self.backups, now=NOW)
        self.original_db = self.db.read_bytes()
        self.original_report = (self.reports / "sample.md").read_bytes()

    def check(self, **kwargs):
        return assurance.check(
            backups=self.backups, scratch=self.cache, state=self.state,
            drill_fn=restore.drill, **kwargs
        )

    def test_real_scratch_restore_matches_sqlite_and_reports_without_mutation(self):
        result = self.check()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["reports"], 1)
        self.assertFalse(result["live_data_modified"])
        self.assertEqual(self.db.read_bytes(), self.original_db)
        self.assertEqual((self.reports / "sample.md").read_bytes(), self.original_report)
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()), [])
        persisted = json.loads((self.state / "status.json").read_text())
        self.assertTrue(persisted["passed"])
        self.assertEqual((self.state / "status.json").stat().st_mode & 0o777, 0o600)

    def test_reports_only_scratch_restore_passes_without_sqlite_dependency(self):
        backup.create_reports_backup(
            self.reports, self.backups,
            now=NOW.replace(hour=22))
        self.db.unlink()
        result = self.check()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["reports"], 1)
        self.assertIsNone(result.get("candidates"))
        self.assertFalse(result["live_data_modified"])
        self.assertFalse((self.cache / "restored").exists())

    def test_corrupted_backup_fails_and_records_status(self):
        source = assurance.backup_latest(self.backups)
        (source / "reports.tar.gz").write_bytes(b"broken")
        result = self.check()
        self.assertFalse(result["passed"])
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()), [])
        self.assertFalse(json.loads((self.state / "status.json").read_text())["passed"])
        self.assertEqual(self.db.read_bytes(), self.original_db)

    def test_low_disk_blocks_restore_before_invoking_callback(self):
        called = []
        low = lambda _: shutil._ntuple_diskusage(1000, 999, 1)
        result = assurance.check(
            backups=self.backups, scratch=self.cache, state=self.state,
            drill_fn=lambda *a: called.append(True),
            disk_usage=low,
        )
        self.assertFalse(result["passed"])
        self.assertEqual(called, [])
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_oversized_backup_rejected_without_allocating_large_file(self):
        source = assurance.backup_latest(self.backups)
        with (source / "research.sqlite3").open("ab") as out:
            out.truncate(assurance.MAX_DB_BYTES + 1)
        result = self.check()
        self.assertFalse(result["passed"])
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_invalid_drill_output_fails_closed_and_cleanup_occurs(self):
        def fake_drill(source, target):
            target.mkdir()
            (target / "fixture").write_text("hi")
            return {"verified": False, "live_data_modified": False}
        result = assurance.check(backups=self.backups, scratch=self.cache,
                                 state=self.state, drill_fn=fake_drill)
        self.assertFalse(result["passed"])
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_unit_is_weekly_no_network_and_resource_bounded(self):
        unit = (ROOT / "systemd/slipcage-assurance.service").read_text()
        timer = (ROOT / "systemd/slipcage-assurance.timer").read_text()
        for item in ("PrivateNetwork=yes", "PrivateDevices=yes",
                     "MemoryMax=512M", "CPUQuota=35%", "TasksMax=32",
                     "TimeoutStartSec=10min", "LimitFSIZE=768M",
                     "StateDirectory=slipcage-assurance", "CacheDirectory=slipcage-assurance",
                     "ProtectSystem=strict", "ReadOnlyPaths=/var/backups/slipcage"):
            self.assertIn(item, unit)
        self.assertIn("OnCalendar=Sun", timer)
        self.assertIn("Unit=slipcage-assurance.service", timer)
        self.assertNotIn("qemu", unit.lower())


class LocalOnlyAlertBoundaryTests(unittest.TestCase):
    def test_only_local_journal_health_warnings_remain(self):
        health = (ROOT / "scripts/slipcage-health.py").read_text()
        unit = (ROOT / "systemd/slipcage-health.service").read_text()
        timer = (ROOT / "systemd/slipcage-health.timer").read_text()
        self.assertIn("SLIPCAGE_HEALTH_WARNING", health)
        self.assertIn("SLIPCAGE_HEALTH_RECOVERED", health)
        self.assertIn("StandardError=journal", unit)
        self.assertIn("PrivateNetwork=yes", unit)
        self.assertIn("Unit=slipcage-health.service", timer)

    def test_benign_manual_guest_runtime_is_still_packaged(self):
        site = (ROOT / "playbooks/site.yml").read_text()
        for pkg in ("qemu-system-x86", "busybox-static", "cpio"):
            self.assertIn("          - " + pkg, site)
        probe = (ROOT / "scripts/slipcage-kvm-probe.py").read_text()
        self.assertIn('QEMU = "/usr/bin/qemu-system-x86_64"', probe)
        for filename in ("build-microguest.sh", "build-experiment-guest.sh"):
            builder = (ROOT / "scripts" / filename).read_text()
            self.assertIn("busybox-static is required", builder)
            self.assertIn("cpio is required", builder)
        for unit in ("slipcage-experiment@.service",
                     "slipcage-guest-cycles@.service"):
            text = (ROOT / "systemd" / unit).read_text()
            self.assertIn("PrivateNetwork=yes", text)
            self.assertIn("DeviceAllow=/dev/kvm rw", text)
            self.assertNotIn("WantedBy=", text)

    def test_no_remote_notifier_is_installed_or_scheduled(self):
        playbook = (ROOT / "playbooks/site.yml").read_text()
        for path in (
            ROOT / "scripts/slipcage-alert-dispatch.py",
            ROOT / "systemd/slipcage-alert-dispatch.service",
            ROOT / "systemd/slipcage-alert-dispatch.timer",
        ):
            self.assertFalse(path.exists(), str(path))
        self.assertNotIn("alert-dispatch", playbook)
        self.assertNotIn("health-webhook.url", playbook)
        self.assertIn("Protect private smol release-channel configuration", playbook)
        self.assertIn("path: /etc/slipcage", playbook)
        self.assertIn("Enable bounded read-only operational health checks", playbook)
        self.assertIn("Enable bounded weekly local backup assurance", playbook)
        self.assertIn("Enable scheduled Slipcage backups", playbook)


if __name__ == "__main__":
    unittest.main()
