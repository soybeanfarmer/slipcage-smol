"""Offline producer/consumer tests; no VM, shell, network or Git writes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "slipcage-experiment-consumer.py"
spec = importlib.util.spec_from_file_location("experiment_consumer", SCRIPT)
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)

SHA1 = "a" * 40
SHA2 = "b" * 40
APPROVED = {
    "schema_version": 1, "id": "EXP-0001", "status": "approved",
    "runner": "fixed_arithmetic_sha256_v1", "cycles": 1,
}


def passed_evidence():
    return {
        "mode": "fixed_arithmetic_sha256_v1", "requested_cycles": 1,
        "completed_cycles": 1, "successful_cycles": 1,
        "passed": True, "network": "disabled", "persistent_guest_disk": False,
        "run_dir": "/private/guest/run-fixture",
        "cycles": [{"passed": True, "known_answers_verified": True}],
    }


class ExperimentConsumerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.queue = self.root / "approved"
        self.queue.mkdir()
        self.revision = self.root / "deployed-sha"
        self.revision.write_text(SHA1 + "\n")
        self.state = self.root / "state"
        self.uid = os.getuid()
        self.manifest = self.queue / "EXP-0001.json"
        self.manifest.write_text(json.dumps(APPROVED))
        self.executions = 0

    def run_once(self, runner=None):
        return consumer.consume(
            queue=self.queue, revision_file=self.revision,
            state=self.state, owner=self.uid,
            runner=runner if runner is not None else self.fake_runner)

    def fake_runner(self):
        self.executions += 1
        return passed_evidence()

    def result_files(self):
        return list((self.state / "experiment-results").glob("EXP-*.json"))

    def test_first_run_is_private_and_repeat_is_idle(self):
        first = self.run_once()
        self.assertEqual(first["status"], "passed")
        self.assertEqual(first["approved_release_sha"], SHA1)
        self.assertEqual(first["runner"], "fixed_arithmetic_sha256_v1")
        self.assertEqual(self.executions, 1)
        self.assertEqual(len(self.result_files()), 1)
        saved = json.loads(self.result_files()[0].read_text())
        self.assertEqual(saved["outcome"], "known_answers_verified")
        self.assertEqual(stat.S_IMODE(self.result_files()[0].stat().st_mode), 0o600)
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 1)

    def test_new_release_revision_is_new_work_and_preserves_old_result(self):
        self.run_once()
        self.revision.write_text(SHA2 + "\n")
        again = self.run_once()
        self.assertEqual(again["status"], "passed")
        self.assertEqual(again["approved_release_sha"], SHA2)
        self.assertEqual(len(self.result_files()), 2)
        self.assertEqual(self.executions, 2)

    def test_failure_not_rerun_and_provenance_preserved(self):
        failed = self.run_once(runner=lambda: {"passed": True})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["outcome"], "missing_or_failed_fixed_guest_evidence")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 0)

    def test_fake_success_without_known_answers_is_not_accepted(self):
        evidence = passed_evidence()
        evidence["cycles"][0]["known_answers_verified"] = False
        self.assertEqual(self.run_once(runner=lambda: evidence)["status"], "failed")

    def test_failed_exception_message_not_written_to_results(self):
        def fault():
            raise RuntimeError("do not leak secrets to repo or journal")
        saved = self.run_once(runner=fault)
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["failure_type"], "RuntimeError")
        self.assertNotIn("do not leak secrets", self.result_files()[0].read_text())

    def test_interrupted_claim_stops_automatic_retry(self):
        definition, digest = consumer.read_manifest(self.manifest, owner=self.uid)
        import hashlib
        key = hashlib.sha256(
            (definition["id"] + ":" + SHA1 + ":" + digest).encode("ascii")
        ).hexdigest()
        directory = self.state / "experiment-results"
        directory.mkdir(parents=True)
        (directory / ("EXP-0001-" + key + ".json")).write_text(
            '{"status": "claimed"}')
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 0)

    def test_rejects_arbitrary_commands_and_other_runners(self):
        for change in (
            {"command": "echo arbitrary payload"},
            {"runner": "shell_script"},
            {"cycles": 2},
            {"status": "draft"},
        ):
            with self.subTest(change=change):
                obj = {**APPROVED, **change}
                self.manifest.write_text(json.dumps(obj))
                with self.assertRaises(ValueError):
                    self.run_once()
                self.assertEqual(self.executions, 0)
        self.assertFalse(self.state.exists())

    def test_rejects_bad_release_and_symlink_or_writable_manifest(self):
        self.revision.write_text("not-a-github-commit\n")
        with self.assertRaises(ValueError):
            self.run_once()
        self.revision.write_text(SHA1 + "\n")
        self.manifest.chmod(0o666)
        with self.assertRaises(ValueError):
            self.run_once()
        self.manifest.chmod(0o644)
        self.manifest.unlink()
        self.manifest.symlink_to(self.revision)
        with self.assertRaises(ValueError):
            self.run_once()
        self.assertEqual(self.executions, 0)

    def test_limit_on_approved_manifest_count(self):
        for i in range(2, 28):
            (self.queue / f"EXP-{i:04}.json").write_text(
                json.dumps({**APPROVED, "id": f"EXP-{i:04}"}))
        with self.assertRaises(ValueError):
            self.run_once()

    def test_approved_manifest_and_sandbox_are_release_bundled_and_opt_in(self):
        manifest = json.loads((ROOT / "experiments/EXP-0001.json").read_text())
        self.assertEqual(manifest, APPROVED)
        service = (ROOT / "systemd/slipcage-experiment-consumer.service").read_text()
        timer = (ROOT / "systemd/slipcage-experiment-consumer.timer").read_text()
        playbook = (ROOT / "playbooks/site.yml").read_text()
        deploy = (ROOT / "scripts/pull-deploy.sh").read_text()
        for field in ("User=slipcage-vmprobe", "SupplementaryGroups=kvm",
                      "PrivateNetwork=yes", "ProtectSystem=strict",
                      "StateDirectory=slipcage-guest",
                      "MemoryMax=1280M", "CPUQuota=100%", "TasksMax=64",
                      "DevicePolicy=closed", "DeviceAllow=/dev/kvm rw",
                      "TimeoutStartSec=5min", "slipcage-guard run"):
            self.assertIn(field, service)
        self.assertNotIn("WantedBy=", service)
        self.assertIn("OnUnitInactiveSec=20min", timer)
        self.assertIn("Install sandboxed experiment consumer and optional timer", playbook)
        self.assertIn("experiments/EXP-*.json", playbook)
        self.assertNotIn("name: slipcage-experiment-consumer.timer\n        daemon_reload", playbook)
        self.assertIn('chmod 0644 "' + chr(36) + '{LAST}.tmp"', deploy)
        self.assertIn("merge-base --is-ancestor", deploy)
        self.assertIn("No successful GitHub Actions validation", deploy)
        self.assertNotIn("shell=True", SCRIPT.read_text())
        self.assertNotIn("github.com", SCRIPT.read_text())

if __name__ == "__main__":
    unittest.main()
