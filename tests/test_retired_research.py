"""Retiring discovery must preserve data and require no research runtime."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RetiredResearchTests(unittest.TestCase):
    def test_old_advisory_code_and_units_deleted(self):
        for name in ("app/isolab.py", "app/intelligence.py",
                     "app/recovery.py", "app/local_review.py",
                     "scripts/discover.sh",
                     "systemd/slipcage-discover.timer",
                     "systemd/slipcage-review.timer",
                     "systemd/slipcage-discover.service",
                     "systemd/slipcage-review.service"):
            with self.subTest(path=name):
                self.assertFalse((ROOT / name).exists())
        self.assertTrue((ROOT / "systemd/slipcage-experiment@.service").exists())

    def test_retirement_order_and_old_data_retained(self):
        site = (ROOT / "playbooks/site.yml").read_text()
        self.assertLess(site.index("Enter maintenance and drain guarded research jobs"),
                        site.index("Preserve final legacy research SQLite"))
        self.assertLess(site.index("Preserve final legacy research SQLite"),
                        site.index("Disable legacy discovery and review timers"))
        self.assertLess(site.index("Disable legacy discovery and review timers"),
                        site.index("Remove obsolete discovery and review unit"))
        self.assertIn("research-retired.snapshot-complete", site)
        self.assertIn("legacy_research_db.stat.isreg", site)
        self.assertNotIn("path: /srv/isolab/research.sqlite3\n        state: absent", site)
        self.assertNotIn("path: /srv/isolab/reports\n        state: absent", site)
        self.assertIn("Create first reports-only snapshot", site)
        self.assertNotIn("Enable native discovery and review schedules", site)

    def test_backup_and_health_are_independent_of_candidate_queue(self):
        unit = (ROOT / "systemd/slipcage-backup.service").read_text()
        self.assertIn("create-reports", unit)
        self.assertNotIn("--db", unit)
        health = (ROOT / "scripts/slipcage-health.py").read_text()
        self.assertNotIn("slipcage-discover.", health)
        self.assertNotIn("slipcage-review.", health)
        self.assertIn("slipcage-assurance.timer", health)
        self.assertIn("slipcage-backup.timer", health)
        self.assertIn("slipcage-pull-deploy.timer", health)

if __name__ == "__main__":
    unittest.main()
