"""Offline GitHub result feedback contract; no network, token or guest execution."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "slipcage-results-publisher.py"
spec = importlib.util.spec_from_file_location("slipcage_results_publisher", SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

RELEASE = "c695c6ec309eade72048840972286ab38572014f"
MANIFEST = "7df823dde988a840511b7164c2a65e871fff2bf2730e5d31d30a899802a29348"
HEAD_SHA = "a" * 40
TREE_SHA = "b" * 40
NEW_TREE_SHA = "d" * 40
COMMIT_SHA = "e" * 40


def original_result(status="passed", outcome=None, runner="fixed_arithmetic_sha256_v1"):
    if outcome is None:
        if runner == "fixed_guest_boot_v1":
            outcome = ("guest_boot_verified" if status == "passed"
                       else "missing_or_failed_boot_evidence")
        else:
            outcome = ("known_answers_verified" if status == "passed"
                       else "missing_or_failed_fixed_guest_evidence")
    return {
        "schema_version": 1,
        "experiment_id": "EXP-0001",
        "approved_release_sha": RELEASE,
        "manifest_sha256": MANIFEST,
        "runner": runner,
        "status": status,
        "outcome": outcome,
        "claimed_utc": "2026-10-09T16:09:47+00:00",
        "finished_utc": "2026-10-09T16:09:50+00:00",
        "run_dir": "/var/lib/slipcage-guest/runs/PRIVATE-HOST-PATH",
        "failure_type": "SecretFailureType",
    }


def filename(record):
    value = (record["experiment_id"] + ":" + record["approved_release_sha"]
             + ":" + record["manifest_sha256"]).encode("ascii")
    return "EXP-0001-" + hashlib.sha256(value).hexdigest() + ".json"


class FakeGitHub:
    def __init__(self, *, prior_branch=False, prior_pr=False,
                 already_merged=False, closed_pr=False):
        self.posts = []
        self.gets = []
        self.prior_branch = prior_branch
        self.prior_pr = prior_pr
        self.already_merged = already_merged
        self.closed_pr = closed_pr
        self.expected = None

    def get(self, route, optional=False):
        self.gets.append(route)
        if route == "/git/ref/heads/main":
            return {"object": {"sha": HEAD_SHA}}
        if route.startswith("/contents/") and route.endswith("?ref=main"):
            return {"type": "file"} if self.already_merged else None
        if route.startswith("/git/ref/heads/results/"):
            return {"object": {"sha": COMMIT_SHA}} if self.prior_branch else None
        if route == "/git/commits/" + HEAD_SHA:
            return {"tree": {"sha": TREE_SHA}}
        if route.startswith("/contents/") and "?ref=results/" in route:
            return {"type": "file", "sha": publisher.blob_sha(
                publisher.output_bytes(self.expected))}
        if route.startswith("/pulls?"):
            if not (self.prior_pr or self.closed_pr):
                return []
            return [{"number": 17,
                     "head": {"ref": publisher.destination(self.expected)[0]},
                     "state": "closed" if self.closed_pr else "open",
                     "merged_at": None}]
        raise AssertionError("Unexpected GitHub GET route: " + route)

    def post(self, route, value):
        self.posts.append((route, value))
        if route == "/git/trees":
            assert value["tree"][0]["path"].startswith("results/EXP-0001/")
            assert value["tree"][0]["content"] == publisher.output_bytes(
                self.expected).decode("ascii")
            return {"sha": NEW_TREE_SHA}
        if route == "/git/commits":
            assert value["parents"] == [HEAD_SHA]
            return {"sha": COMMIT_SHA}
        if route == "/git/refs":
            assert value["ref"].startswith("refs/heads/results/")
            return {"ref": value["ref"]}
        if route == "/pulls":
            assert value["draft"] is True
            assert value["base"] == "main"
            assert value["head"].startswith("results/")
            assert "PRIVATE-HOST-PATH" not in value["body"]
            return {"number": 17, "state": "open"}
        raise AssertionError("Unexpected GitHub POST route: " + route)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "private-results"
        self.source.mkdir(mode=0o700)
        self.state = self.root / "publisher-state"
        self.owner = os.getuid()
        self.record = original_result()
        self.result_file = self.source / filename(self.record)
        self.save_source()

    def save_source(self):
        self.result_file.write_text(json.dumps(self.record), encoding="utf-8")
        self.result_file.chmod(0o600)

    def invoke(self, *, submit=False, api=None):
        return publisher.run(source=self.source, state=self.state,
                             owner=self.owner, submit=submit, api=api)

    def test_sanitizer_only_allows_known_public_fields(self):
        output = publisher.sanitize(self.record, self.result_file.name)
        self.assertEqual(output["experiment_id"], "EXP-0001")
        self.assertEqual(output["approved_release_sha"], RELEASE)
        self.assertEqual(output["status"], "passed")
        self.assertEqual(output["evidence"],
                         "self-reported fixed guest result; requires human review")
        self.assertNotIn("run_dir", output)
        self.assertNotIn("failure_type", output)
        serialized = publisher.output_bytes(output).decode("ascii")
        self.assertNotIn("/var/lib", serialized)
        self.assertNotIn("SecretFailureType", serialized)
        self.assertLess(len(serialized), 2048)
        self.assertEqual(self.invoke()["status"], "dry_run")

    def test_boot_result_is_allowlisted_with_runner_specific_outcome(self):
        record = original_result(runner="fixed_guest_boot_v1")
        output = publisher.sanitize(record, filename(record))
        self.assertEqual(output["runner"], "fixed_guest_boot_v1")
        self.assertEqual(output["status"], "passed")
        self.assertEqual(output["outcome"], "guest_boot_verified")
        self.assertNotIn("run_dir", output)
        self.assertNotIn("failure_type", output)

        wrong = {**record, "outcome": "known_answers_verified"}
        with self.assertRaises(publisher.PublishError):
            publisher.sanitize(wrong, filename(wrong))

    def test_dry_run_never_loads_a_credential_or_contacts_api(self):
        with patch.object(publisher, "credential",
                          side_effect=AssertionError("read token")):
            result = self.invoke()
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse((self.state / self.result_file.name).exists())

    def test_strict_result_validation_blocks_payload_injection(self):
        for change in (
            {"shell": "/bin/sh"},
            {"status": "pwned"},
            {"outcome": "arbitrary console data"},
            {"claimed_utc": "not a date"},
            {"finished_utc": "2026-10-09T16:09:46+00:00"},
            {"approved_release_sha": "f" * 40},
            {"runner": "arbitrary_command"},
            {"schema_version": True},
        ):
            with self.subTest(change=change):
                changed = {**self.record, **change}
                self.result_file.write_text(json.dumps(changed))
                with self.assertRaises(publisher.PublishError):
                    self.invoke()
        self.assertFalse((self.state / self.result_file.name).exists())

    def test_unreadable_or_symlinked_source_never_sent(self):
        dest = self.root / "private.txt"
        dest.write_text("private")
        self.result_file.unlink()
        self.result_file.symlink_to(dest)
        with self.assertRaises(OSError):
            self.invoke()
        self.result_file.unlink()
        self.save_source()
        self.result_file.chmod(0o644)
        with self.assertRaises(publisher.PublishError):
            self.invoke()
        self.assertFalse((self.state / self.result_file.name).exists())

    def test_claimed_record_skipped_until_completed(self):
        self.record["status"] = "claimed"
        self.record.pop("finished_utc")
        self.record.pop("outcome")
        self.save_source()
        self.assertEqual(self.invoke()["status"], "idle")

    def test_create_draft_pr_once_and_persist_private_receipt(self):
        fake = FakeGitHub()
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        result = self.invoke(submit=True, api=fake)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["pull_request"],
                         "https://github.com/soybeanfarmer/slipcage-smol/pull/17")
        self.assertEqual([v[0] for v in fake.posts],
                         ["/git/trees", "/git/commits", "/git/refs", "/pulls"])
        receipt = self.state / self.result_file.name
        self.assertTrue(receipt.is_file())
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
        self.assertEqual(self.invoke(submit=True, api=fake)["status"], "idle")
        self.assertEqual(len(fake.posts), 4)

    def test_resume_after_branch_creation_and_avoid_duplicate_pr(self):
        fake = FakeGitHub(prior_branch=True)
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        self.assertEqual(self.invoke(submit=True, api=fake)["status"], "submitted")
        self.assertEqual([v[0] for v in fake.posts], ["/pulls"])

    def test_resume_after_pr_created_but_before_receipt(self):
        fake = FakeGitHub(prior_branch=True, prior_pr=True)
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        self.assertEqual(self.invoke(submit=True, api=fake)["status"], "submitted")
        self.assertEqual(fake.posts, [])

    def test_existing_merged_result_is_already_done(self):
        fake = FakeGitHub(already_merged=True)
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        self.assertEqual(self.invoke(submit=True, api=fake)["status"], "already_merged")
        self.assertEqual(fake.posts, [])

    def test_closed_unmerged_pr_requires_operator_intervention(self):
        fake = FakeGitHub(prior_branch=True, closed_pr=True)
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        with self.assertRaises(publisher.PublishError):
            self.invoke(submit=True, api=fake)
        self.assertFalse((self.state / self.result_file.name).exists())

    def test_no_git_write_if_upload_fails(self):
        fake = FakeGitHub()
        fake.expected = publisher.sanitize(self.record, self.result_file.name)
        def fail(*_):
            raise publisher.PublishError("HTTP 403")
        fake.post = fail
        with self.assertRaises(publisher.PublishError):
            self.invoke(submit=True, api=fake)
        self.assertFalse((self.state / self.result_file.name).exists())

    def test_git_blob_sha_stable(self):
        self.assertEqual(publisher.blob_sha(b"hello\n"),
                         hashlib.sha1(b"blob 6\x00hello\n").hexdigest())

    def test_systemd_is_dormant_and_sandboxed(self):
        unit = (ROOT / "systemd/slipcage-results-publisher.service").read_text()
        site = (ROOT / "playbooks/site.yml").read_text()
        for requirement in (
            "User=root", "PrivateDevices=yes", "ProtectSystem=strict",
            "NoNewPrivileges=yes", "LoadCredential=github_token:",
            "StateDirectory=slipcage-results-publisher",
            "InaccessiblePaths=-/var/lib/slipcage-guest/runs",
            "ReadOnlyPaths=/var/lib/slipcage-guest/experiment-results",
            "MemoryMax=192M", "CPUQuota=25%", "TimeoutStartSec=90s",
            "--submit",
        ):
            self.assertIn(requirement, unit)
        self.assertNotIn("WantedBy=", unit)
        self.assertNotIn("/dev/kvm rw", unit)
        self.assertNotIn("SupplementaryGroups=kvm", unit)
        self.assertIn("Install manual-only isolated GitHub result PR service", site)
        self.assertNotIn("slipcage-results-publisher.timer", site)
        self.assertNotIn("Environment=GITHUB_TOKEN=", unit)
        self.assertFalse((ROOT / "systemd/slipcage-results-publisher.timer").exists())


if __name__ == "__main__":
    unittest.main()
