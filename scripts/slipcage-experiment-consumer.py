#!/usr/bin/env python3
"""Consume one approved release-bundled experiment via the fixed benign guest runner.

No network, Git credentials, shell, dynamic commands, or arbitrary guest images.
A durable claim precedes guest execution; interrupted/failed jobs require human
review and will not be automatically retried.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from importlib.machinery import SourceFileLoader

QUEUE = Path("/usr/local/lib/slipcage/experiments")
REVISION = Path("/var/lib/slipcage/deployed-sha")
STATE = Path("/var/lib/slipcage-guest")
DRIVER = Path("/usr/local/lib/slipcage/guest-lifecycle.py")
EXPERIMENT_ID = re.compile(r"EXP-[0-9]{4}\Z")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_RUNNER = "fixed_arithmetic_sha256_v1"
FIELDS = {"schema_version", "id", "status", "runner", "cycles"}
MAX_MANIFESTS = 500
MAX_MANIFEST_BYTES = 4096
MAX_RESULT_FILES = 2000
MAX_RESULT_BYTES = 8192
MAX_CYCLES = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def trusted_file(path: Path, *, owner: int = 0, max_bytes: int) -> bytes:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o022 or not 0 < info.st_size <= max_bytes):
        raise ValueError("Untrusted or oversized approved file: " + path.name)
    # Fixed root-owned directories; no caller-supplied path or URL is accepted.
    with path.open("rb") as stream:
        content = stream.read(max_bytes + 1)
    if not 0 < len(content) <= max_bytes:
        raise ValueError("Approved file changed size during read")
    return content


def read_revision(path: Path = REVISION, *, owner: int = 0) -> str:
    value = trusted_file(path, owner=owner, max_bytes=64).decode("ascii").strip()
    if not COMMIT_SHA.fullmatch(value):
        raise ValueError("Invalid approved release SHA")
    return value


def read_manifest(path: Path, *, owner: int = 0) -> tuple[dict, str]:
    if not path.name.endswith(".json"):
        raise ValueError("Experiment must be a JSON manifest")
    raw = trusted_file(path, owner=owner, max_bytes=MAX_MANIFEST_BYTES)
    item = json.loads(raw)
    if not isinstance(item, dict) or set(item) != FIELDS:
        raise ValueError("Unknown experiment manifest fields")
    if (type(item["schema_version"]) is not int or item["schema_version"] != 1
            or not isinstance(item["id"], str)
            or not EXPERIMENT_ID.fullmatch(item["id"])
            or path.name != item["id"] + ".json"
            or item["status"] != "approved"
            or item["runner"] != ALLOWED_RUNNER
            or type(item["cycles"]) is not int
            or not 1 <= item["cycles"] <= MAX_CYCLES):
        raise ValueError("Experiment is not a supported, approved fixed workload")
    return item, hashlib.sha256(raw).hexdigest()


def manifests(queue: Path = QUEUE, *, owner: int = 0) -> list[tuple[dict, str]]:
    info = queue.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o022):
        raise ValueError("Approved experiment queue directory is untrusted")
    files = sorted(queue.iterdir())
    if len(files) > MAX_MANIFESTS:
        raise ValueError("Too many approved experiment definitions")
    return [read_manifest(path, owner=owner) for path in files]



def prior_claims(directory: Path, *, owner: int) -> set[tuple[str, str]]:
    """Index durable private claims across approved releases.

    A new release may add unrelated experiments or change publisher code.
    Neither event should rerun an unchanged, already claimed experiment.
    Keep the historic release-specific result filename for provenance and
    compatibility with the sanitized results publisher.
    """
    entries = sorted(directory.iterdir())
    if len(entries) > MAX_RESULT_FILES:
        raise ValueError("Too many retained private experiment result records")
    seen: set[tuple[str, str]] = set()
    for path in entries:
        if path.name.startswith(".result-"):
            # A failed atomic replacement may leave a private temp file.
            # A durable claim or completed JSON is still the source of truth.
            continue
        matched = re.fullmatch(r"(EXP-[0-9]{4})-([a-f0-9]{64})[.]json", path.name)
        if not matched:
            raise ValueError("Unexpected item in experiment result directory")
        raw = trusted_file(path, owner=owner, max_bytes=MAX_RESULT_BYTES)
        item = json.loads(raw)
        if not isinstance(item, dict):
            raise ValueError("Invalid previous result")
        ident = item.get("experiment_id")
        revision = item.get("approved_release_sha")
        digest = item.get("manifest_sha256")
        if (ident != matched.group(1)
                or not isinstance(revision, str) or not COMMIT_SHA.fullmatch(revision)
                or not isinstance(digest, str)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or item.get("status") not in ("claimed", "passed", "failed")):
            raise ValueError("Invalid previous result provenance")
        expected = hashlib.sha256(
            (ident + ":" + revision + ":" + digest).encode("ascii")
        ).hexdigest()
        if expected != matched.group(2):
            raise ValueError("Previous result filename disagrees with contents")
        seen.add((ident, digest))
    return seen


def fixed_guest_runner(cycles: int = 1) -> dict:
    """Invoke only the installed fixed controller with a bounded cycle count."""
    loader = SourceFileLoader("slipcage_fixed_guest", str(DRIVER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_lifecycle(cycles, profile="experiment")


def publish_json(destination: Path, value: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                         prefix=".result-", delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
        parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def claim(destination: Path, value: dict) -> bool:
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return True


def consume(*, queue: Path = QUEUE, revision_file: Path = REVISION,
            state: Path = STATE, owner: int = 0, runner=None) -> dict:
    os.umask(0o077)
    revision = read_revision(revision_file, owner=owner)
    definitions = manifests(queue, owner=owner)
    if state.is_symlink():
        raise ValueError("Consumer state directory must not be a symlink")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    result_dir = state / "experiment-results"
    if result_dir.is_symlink():
        raise ValueError("Consumer results directory must not be a symlink")
    result_dir.mkdir(mode=0o700, exist_ok=True)
    lock_fd = os.open(state / ".consumer.lock",
                      os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        seen = prior_claims(result_dir, owner=os.geteuid())
        for definition, digest in definitions:
            # Release changes alone do NOT re-run unchanged experiments.
            # A changed reviewed manifest digest or a new ID is new work.
            if (definition["id"], digest) in seen:
                continue
            # Retain release-specific filenames so the publisher and audit
            # evidence still record the exact approved code revision.
            key = hashlib.sha256(
                (definition["id"] + ":" + revision + ":" + digest).encode("ascii")
            ).hexdigest()
            destination = result_dir / (definition["id"] + "-" + key + ".json")
            start = utc_now()
            base = {
                "schema_version": 1,
                "experiment_id": definition["id"],
                "approved_release_sha": revision,
                "manifest_sha256": digest,
                "runner": ALLOWED_RUNNER,
                "cycles": definition["cycles"],
                "claimed_utc": start,
            }
            if not claim(destination, {**base, "status": "claimed"}):
                # Preserve incomplete claims for review; never automatically retry.
                continue
            try:
                evidence = (runner if runner is not None else fixed_guest_runner)(definition["cycles"])
                valid = (isinstance(evidence, dict)
                         and evidence.get("mode") == ALLOWED_RUNNER
                         and evidence.get("requested_cycles") == definition["cycles"]
                         and evidence.get("completed_cycles") == definition["cycles"]
                         and evidence.get("successful_cycles") == definition["cycles"]
                         and evidence.get("passed") is True
                         and evidence.get("network") == "disabled"
                         and evidence.get("persistent_guest_disk") is False
                         and isinstance(evidence.get("cycles"), list)
                         and len(evidence["cycles"]) == definition["cycles"]
                         and all(isinstance(cycle, dict)
                                 and cycle.get("passed") is True
                                 and cycle.get("known_answers_verified") is True
                                 for cycle in evidence["cycles"]))
                result = {**base, "status": "passed" if valid else "failed",
                          "finished_utc": utc_now(),
                          "outcome": "known_answers_verified" if valid
                          else "missing_or_failed_fixed_guest_evidence",
                          "run_dir": (str(evidence.get("run_dir", ""))[:500]
                                      if isinstance(evidence, dict) else None)}
            except Exception as exc:
                # Never include arbitrary exception messages or console logs.
                result = {**base, "status": "failed", "finished_utc": utc_now(),
                          "outcome": "runner_exception",
                          "failure_type": type(exc).__name__}
            publish_json(destination, result)
            return {**result, "result_path": str(destination)}
        return {"status": "idle", "reason": "no_new_approved_experiments"}
    finally:
        os.close(lock_fd)


def main() -> int:
    try:
        outcome = consume()
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print("slipcage-experiment-consumer: " + type(exc).__name__, file=sys.stderr)
        return 2
    # Only a bounded summary goes to journal; raw evidence stays private.
    print(json.dumps(outcome, sort_keys=True))
    return 1 if outcome["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
