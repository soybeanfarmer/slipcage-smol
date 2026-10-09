"""Smol release-channel isolation: fixtures only, no VPS commands or deploy."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "slipcage-channel.py"
spec = importlib.util.spec_from_file_location("smol_channel", SOURCE)
channel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(channel)


class SmolChannelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.blockers = [
            self.root / "etc" / "slipcage",
            self.root / "var" / "lib" / "slipcage",
            self.root / "var" / "lib" / "dagu",
            self.root / "srv" / "isolab",
            self.root / "var" / "backups" / "slipcage",
            self.root / "units" / "isolab-dagu.service",
        ]
        self.marker = self.blockers[0] / "release-channel"
        # Production already has /etc; provide its equivalent in the test fixture.
        self.marker.parent.parent.mkdir(parents=True, exist_ok=True)

    def test_pristine_host_passes_without_mutation(self):
        channel.require_pristine(self.blockers)
        self.assertFalse(self.marker.parent.exists())
        self.assertFalse(any(path.exists() for path in self.blockers))

    def test_existing_research_or_release_state_refused(self):
        for path in self.blockers:
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch() if path.suffix else path.mkdir(exist_ok=True)
                with self.assertRaises(ValueError):
                    channel.require_pristine(self.blockers)
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()

    def test_dangling_symlink_blocks_bootstrap(self):
        sentinel = self.blockers[1]
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            channel.require_pristine(self.blockers)
        self.assertTrue(channel.occupied(sentinel))

    def test_enroll_is_one_time_and_root_private_in_production(self):
        uid = os.geteuid()  # Normal CI fixture owned by the test account.
        channel.enroll(marker=self.marker, blockers=self.blockers,
                       expected_uid=uid)
        channel.require_enrolled(self.marker, expected_uid=uid)
        self.assertEqual(self.marker.read_text(), "soybeanfarmer/slipcage-smol\n")
        self.assertEqual(stat.S_IMODE(self.marker.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.marker.parent.stat().st_mode), 0o700)
        with self.assertRaises(ValueError):
            channel.enroll(marker=self.marker, blockers=self.blockers,
                           expected_uid=uid)

    def test_wrong_repo_marker_and_world_readable_marker_rejected(self):
        uid = os.geteuid()
        channel.enroll(marker=self.marker, blockers=self.blockers,
                       expected_uid=uid)
        self.marker.write_text("soybeanfarmer/slipcage\n")
        with self.assertRaises(ValueError):
            channel.require_enrolled(self.marker, expected_uid=uid)
        self.marker.write_text(channel.CHANNEL + "\n")
        self.marker.chmod(0o644)
        with self.assertRaises(ValueError):
            channel.require_enrolled(self.marker, expected_uid=uid)
        self.marker.chmod(0o600)
        self.marker.parent.chmod(0o755)
        with self.assertRaises(ValueError):
            channel.require_enrolled(self.marker, expected_uid=uid)

    def test_symlink_marker_rejected(self):
        self.marker.parent.mkdir(mode=0o700, parents=True)
        original = self.root / "value"
        original.write_text("soybeanfarmer/slipcage-smol\n")
        self.marker.symlink_to(original)
        with self.assertRaises(OSError):
            channel.require_enrolled(self.marker, expected_uid=os.geteuid())

    def test_host_bootstrap_refuses_before_any_side_effects(self):
        source = (ROOT / "scripts" / "bootstrap-pull.sh").read_text()
        self.assertIn('slipcage-channel.py" pristine', source)
        self.assertIn('slipcage-channel.py" enroll', source)
        self.assertLess(source.index('slipcage-channel.py" pristine'),
                        source.index("apt-get update"))
        self.assertLess(source.index('slipcage-channel.py" enroll'),
                        source.index('install -d -m 0755'))
        self.assertIn("/usr/local/sbin/slipcage-smol-channel", source)
        self.assertNotIn("systemctl disable", source)

    def test_pull_deployer_only_pulls_smol_and_checks_host_first(self):
        deploy = (ROOT / "scripts" / "pull-deploy.sh").read_text()
        self.assertIn('REPO="soybeanfarmer/slipcage-smol"', deploy)
        self.assertIn("slipcage-smol-channel enrolled", deploy)
        self.assertLess(deploy.index("slipcage-smol-channel enrolled"),
                        deploy.index("curl --fail"))
        self.assertIn("merge-base --is-ancestor", deploy)
        self.assertIn('c.get("name")=="validate"', deploy)
        self.assertIn('c.get("conclusion")=="success"', deploy)
        self.assertIn("No successful GitHub Actions validation", deploy)
        self.assertIn("Unexpected Git remote", deploy)
        self.assertNotIn('REPO="soybeanfarmer/slipcage"', deploy)

    def test_ansible_refuses_unenrolled_or_wrong_channel_before_maintenance(self):
        site = (ROOT / "playbooks" / "site.yml").read_text()
        self.assertIn("follow: false", site)
        self.assertIn("smol_channel_marker.stat.isreg", site)
        self.assertIn("smol_channel_marker.stat.mode", site)
        self.assertIn("soybeanfarmer/slipcage-smol", site)
        self.assertLess(site.index("Require explicit Slipcage-smol bootstrap"),
                        site.index("Enter maintenance and drain guarded research jobs"))
        self.assertIn("Refuse unsafe unattended migration from unguarded Dagu", site)

    def test_release_stays_manual_and_repo_specific(self):
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
        self.assertIn("name: Approve Slipcage-smol Release", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("environment: production", workflow)
        self.assertIn("group: slipcage-smol-release", workflow)
        self.assertIn("RELEASE_SHA: ", workflow)
        self.assertNotIn("on:\n  push:", workflow)

    def test_no_root_or_host_path_override_via_cli(self):
        source = SOURCE.read_text()
        self.assertIn('choices=("pristine", "enroll", "enrolled")', source)
        self.assertNotIn('add_argument("--root"', source)
        self.assertNotIn('add_argument("--marker"', source)
        self.assertNotIn("getenv(", source)
        self.assertNotIn("os.environ", source)


if __name__ == "__main__":
    unittest.main()
