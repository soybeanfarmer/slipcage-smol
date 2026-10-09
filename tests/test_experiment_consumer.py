"""Offline producer/consumer tests; no VM, shell, network or Git writes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
from unittest.mock import patch

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
BOOT_APPROVED = {
    **APPROVED, "id": "EXP-0002", "runner": "fixed_guest_boot_v1",
}
RESOURCE_APPROVED = {
    **APPROVED, "id": "EXP-0003", "runner": "fixed_resource_observation_v1",
}


def passed_evidence(runner_name="fixed_arithmetic_sha256_v1"):
    cycle = {
        "passed": True, "supervisor_exit_code": 0, "probe_exit_code": 0,
    }
    if runner_name == "fixed_arithmetic_sha256_v1":
        mode = "fixed_arithmetic_sha256_v1"
        cycle["known_answers_verified"] = True
    elif runner_name == "fixed_guest_boot_v1":
        mode = "benign_diskless_guest_lifecycle"
    elif runner_name == "fixed_resource_observation_v1":
        mode = "fixed_resource_observation_v1"
        cycle["known_answers_verified"] = True
        cycle["resource_bounds_verified"] = True
        cycle["qemu_resources"] = {
            "wall_seconds": 2.5,
            "cpu_user_seconds": 0.7,
            "cpu_system_seconds": 0.3,
            "qemu_peak_rss_kib": 420000,
        }
    else:
        raise AssertionError("unexpected runner fixture")
    return {
        "mode": mode, "requested_cycles": 1,
        "completed_cycles": 1, "successful_cycles": 1,
        "passed": True, "network": "disabled", "persistent_guest_disk": False,
        "run_dir": "/private/guest/run-fixture",
        "cycles": [cycle],
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

    def fake_runner(self, runner_name):
        self.executions += 1
        return passed_evidence(runner_name)

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

    def test_unrelated_release_does_not_repeat_existing_experiment(self):
        self.run_once()
        self.revision.write_text(SHA2 + "\n")
        again = self.run_once()
        self.assertEqual(again["status"], "idle")
        self.assertEqual(len(self.result_files()), 1)
        self.assertEqual(self.executions, 1)

    def test_changed_approved_manifest_runs_again_with_new_provenance(self):
        first = self.run_once()
        previous = first["manifest_sha256"]
        self.revision.write_text(SHA2 + "\n")
        # Changing the approved bytes intentionally creates new work.
        self.manifest.write_text(json.dumps(APPROVED, indent=2) + "\n")
        second = self.run_once()
        self.assertEqual(second["status"], "passed")
        self.assertEqual(second["approved_release_sha"], SHA2)
        self.assertNotEqual(second["manifest_sha256"], previous)
        self.assertEqual(len(self.result_files()), 2)
        self.assertEqual(self.executions, 2)

    def test_previous_failed_or_interrupted_claim_is_never_retried_on_release(self):
        self.assertEqual(self.run_once(runner=lambda _runner: {"passed": False})["status"],
                         "failed")
        self.revision.write_text(SHA2 + "\n")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 0)

    def test_300_manifest_queue_runs_sequentially_without_duplicates(self):
        for i in range(2, 301):
            (self.queue / f"EXP-{i:04}.json").write_text(
                json.dumps({**APPROVED, "id": f"EXP-{i:04}"}))
        seen = []
        for i in range(300):
            result = self.run_once()
            self.assertEqual(result["status"], "passed")
            seen.append(result["experiment_id"])
        self.assertEqual(seen, [f"EXP-{i:04}" for i in range(1, 301)])
        self.assertEqual(self.executions, 300)
        self.assertEqual(self.run_once()["status"], "idle")
        self.revision.write_text(SHA2 + "\n")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 300)
        self.assertEqual(len(self.result_files()), 300)

    def test_bad_previous_record_fails_closed_before_running_new_work(self):
        self.run_once()
        saved = self.result_files()[0]
        record = json.loads(saved.read_text())
        record["approved_release_sha"] = SHA2
        saved.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.run_once()
        self.assertEqual(self.executions, 1)

    def test_two_approved_manifests_run_in_deterministic_queue_order(self):
        second = self.queue / "EXP-0002.json"
        second.write_text(json.dumps({**APPROVED, "id": "EXP-0002"}))
        first = self.run_once()
        later = self.run_once()
        self.assertEqual(first["experiment_id"], "EXP-0001")
        self.assertEqual(later["experiment_id"], "EXP-0002")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 2)
        self.assertEqual(len(self.result_files()), 2)

    def test_mixed_runner_queue_is_ordered_and_dispatches_exact_names(self):
        second = self.queue / "EXP-0002.json"
        third = self.queue / "EXP-0003.json"
        second.write_text(json.dumps(BOOT_APPROVED))
        third.write_text(json.dumps(RESOURCE_APPROVED))
        seen = []

        def dispatch(runner_name):
            seen.append(runner_name)
            return passed_evidence(runner_name)

        first = self.run_once(runner=dispatch)
        later = self.run_once(runner=dispatch)
        resource = self.run_once(runner=dispatch)
        self.assertEqual(first["experiment_id"], "EXP-0001")
        self.assertEqual(first["outcome"], "known_answers_verified")
        self.assertEqual(later["experiment_id"], "EXP-0002")
        self.assertEqual(later["runner"], "fixed_guest_boot_v1")
        self.assertEqual(later["outcome"], "guest_boot_verified")
        self.assertEqual(resource["experiment_id"], "EXP-0003")
        self.assertEqual(resource["runner"], "fixed_resource_observation_v1")
        self.assertEqual(resource["outcome"], "resource_bounds_verified")
        self.assertEqual(resource["resource_observation"]["qemu_peak_rss_kib"], 420000)
        self.assertEqual(seen, [
            "fixed_arithmetic_sha256_v1",
            "fixed_guest_boot_v1",
            "fixed_resource_observation_v1",
        ])
        self.assertEqual(self.run_once(runner=dispatch)["status"], "idle")

    def test_runner_names_map_only_to_hardcoded_lifecycle_profiles(self):
        driver = self.root / "driver.py"
        driver.write_text(
            "def run_lifecycle(cycles, *, profile):\n"
            "    return {'cycles': cycles, 'profile': profile}\n"
        )
        with patch.object(consumer, "DRIVER", driver):
            arithmetic = consumer.fixed_guest_runner("fixed_arithmetic_sha256_v1")
            boot = consumer.fixed_guest_runner("fixed_guest_boot_v1")
            resource = consumer.fixed_guest_runner("fixed_resource_observation_v1")
            with self.assertRaises(ValueError):
                consumer.fixed_guest_runner("arbitrary_runner")
        self.assertEqual(arithmetic, {"cycles": 1, "profile": "experiment"})
        self.assertEqual(boot, {"cycles": 1, "profile": "boot"})
        self.assertEqual(resource, {"cycles": 1, "profile": "resource"})

    def test_boot_evidence_fails_closed_on_forged_success_invariants(self):
        base = passed_evidence("fixed_guest_boot_v1")
        valid, outcome = consumer.validate_evidence("fixed_guest_boot_v1", base)
        self.assertTrue(valid)
        self.assertEqual(outcome, "guest_boot_verified")

        cases = []
        for field, value in (
            ("mode", "fixed_arithmetic_sha256_v1"),
            ("network", "enabled"),
            ("persistent_guest_disk", True),
            ("completed_cycles", 0),
            ("successful_cycles", 0),
            ("passed", False),
        ):
            evidence = json.loads(json.dumps(base))
            evidence[field] = value
            cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"] = []
        cases.append(evidence)
        for field in ("supervisor_exit_code", "probe_exit_code"):
            evidence = json.loads(json.dumps(base))
            evidence["cycles"][0][field] = 1
            cases.append(evidence)

        for evidence in cases:
            with self.subTest(evidence=evidence):
                valid, outcome = consumer.validate_evidence(
                    "fixed_guest_boot_v1", evidence
                )
                self.assertFalse(valid)
                self.assertEqual(outcome, "missing_or_failed_boot_evidence")

    def test_resource_evidence_requires_known_answers_and_fixed_ceilings(self):
        base = passed_evidence("fixed_resource_observation_v1")
        valid, outcome = consumer.validate_evidence(
            "fixed_resource_observation_v1", base
        )
        self.assertTrue(valid)
        self.assertEqual(outcome, "resource_bounds_verified")

        cases = []
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["resource_bounds_verified"] = False
        cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["known_answers_verified"] = False
        cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["qemu_resources"]["wall_seconds"] = 60.001
        cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["qemu_resources"]["cpu_user_seconds"] = 60.0
        evidence["cycles"][0]["qemu_resources"]["cpu_system_seconds"] = 0.001
        cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["qemu_resources"]["qemu_peak_rss_kib"] = 768 * 1024 + 1
        cases.append(evidence)
        evidence = json.loads(json.dumps(base))
        evidence["cycles"][0]["qemu_resources"]["wall_seconds"] = float("nan")
        cases.append(evidence)

        for evidence in cases:
            with self.subTest(evidence=evidence):
                valid, outcome = consumer.validate_evidence(
                    "fixed_resource_observation_v1", evidence
                )
                self.assertFalse(valid)
                self.assertEqual(outcome, "missing_or_failed_resource_evidence")

    def test_failed_boot_is_not_retried_after_release_change(self):
        self.manifest.write_text(json.dumps({
            **BOOT_APPROVED, "id": "EXP-0001",
        }))
        failed = self.run_once(runner=lambda _runner: {"passed": False})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["outcome"], "missing_or_failed_boot_evidence")
        self.revision.write_text(SHA2 + "\n")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 0)

    def test_failed_item_does_not_block_next_approved_item(self):
        (self.queue / "EXP-0002.json").write_text(
            json.dumps({**APPROVED, "id": "EXP-0002"}))
        failed = self.run_once(runner=lambda _runner: {"passed": False})
        self.assertEqual(failed["status"], "failed")
        subsequent = self.run_once()
        self.assertEqual(subsequent["status"], "passed")
        self.assertEqual(subsequent["experiment_id"], "EXP-0002")

    def test_recorded_failure_exits_cleanly_but_infrastructure_errors_do_not(self):
        with patch.object(consumer, "consume", return_value={"status": "failed"}):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(consumer.main(), 0)
        self.assertIn('"status": "failed"', output.getvalue())
        with patch.object(consumer, "consume", side_effect=ValueError("unsafe input")):
            with redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(consumer.main(), 2)
        self.assertIn("ValueError", errors.getvalue())

    def test_failure_not_rerun_and_provenance_preserved(self):
        failed = self.run_once(runner=lambda _runner: {"passed": True})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["outcome"], "missing_or_failed_fixed_guest_evidence")
        self.assertEqual(self.run_once()["status"], "idle")
        self.assertEqual(self.executions, 0)

    def test_fake_success_without_known_answers_is_not_accepted(self):
        evidence = passed_evidence()
        evidence["cycles"][0]["known_answers_verified"] = False
        self.assertEqual(self.run_once(runner=lambda _runner: evidence)["status"], "failed")

    def test_failed_exception_message_not_written_to_results(self):
        def fault(_runner):
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
        saved = directory / ("EXP-0001-" + key + ".json")
        saved.write_text(json.dumps({
            "schema_version": 1, "experiment_id": definition["id"],
            "approved_release_sha": SHA1, "manifest_sha256": digest,
            "runner": "fixed_arithmetic_sha256_v1",
            "status": "claimed", "claimed_utc": "2026-10-09T16:09:47+00:00",
        }))
        saved.chmod(0o600)
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
        for i in range(2, consumer.MAX_MANIFESTS + 2):
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
                      "ConditionPathExists=/usr/local/lib/slipcage/microguest.cpio.gz",
                      "ConditionPathExists=/usr/local/lib/slipcage/experiment-v1.cpio.gz",
                      "ConditionPathExists=/usr/local/lib/slipcage/resource-v1.cpio.gz",
                      "TimeoutStartSec=5min", "slipcage-guard run"):
            self.assertIn(field, service)
        self.assertNotIn("WantedBy=", service)
        self.assertIn("OnUnitInactiveSec=1min", timer)
        self.assertIn("RandomizedDelaySec=15s", timer)
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
