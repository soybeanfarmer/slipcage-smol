#!/usr/bin/env python3
"""Opt-in sanitized result publisher: one private result -> draft GitHub PR.

Uses a systemd LoadCredential. No raw logs, host paths, error messages,
unknown JSON fields, or arbitrary repository writes are transmitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
from urllib import error, parse, request

REPO = "soybeanfarmer/slipcage-smol"
API = "https://api.github.com/repos/" + REPO
SOURCE = Path("/var/lib/slipcage-guest/experiment-results")
STATE = Path("/var/lib/slipcage-results-publisher")
RUNNER = "fixed_arithmetic_sha256_v1"
RECORD = re.compile(r"(EXP-[0-9]{4})-([a-f0-9]{64})\.json\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
ALLOWED = {"schema_version", "experiment_id", "approved_release_sha",
           "manifest_sha256", "runner", "status", "outcome",
           "claimed_utc", "finished_utc", "run_dir", "failure_type", "cycles"}
OUTCOMES = {"passed": {"known_answers_verified"},
            "failed": {"missing_or_failed_fixed_guest_evidence",
                       "runner_exception"}}
MAX_FILE = 8192
MAX_SCAN = 2000
MAX_API = 256 * 1024


class PublishError(ValueError):
    pass


def stamp(value):
    if not isinstance(value, str) or len(value) > 35:
        raise PublishError("Bad timestamp")
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise PublishError("Timestamp must be UTC")
    except ValueError as exc:
        raise PublishError("Bad timestamp") from exc
    return dt.isoformat(timespec="seconds")


def sanitize(value, filename):
    """Rebuild a small public object, never reusing the input dictionary."""
    matched = RECORD.fullmatch(filename)
    if not matched or not isinstance(value, dict) or not set(value) <= ALLOWED:
        raise PublishError("Unsupported private result")
    if value.get("status") == "claimed":
        return None  # Do not publish an interrupted or pending claim.
    ident = value.get("experiment_id")
    rev = value.get("approved_release_sha")
    digest = value.get("manifest_sha256")
    status = value.get("status")
    outcome = value.get("outcome")
    cycles = value.get("cycles", 1)
    if (type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
            or not isinstance(ident, str) or not re.fullmatch(r"EXP-[0-9]{4}", ident)
            or not isinstance(rev, str) or not SHA40.fullmatch(rev)
            or not isinstance(digest, str) or not SHA64.fullmatch(digest)
            or value.get("runner") != RUNNER
            or type(cycles) is not int or not 1 <= cycles <= 3
            or status not in OUTCOMES or outcome not in OUTCOMES[status]):
        raise PublishError("Unrecognized completed result")
    key = hashlib.sha256((ident + ":" + rev + ":" + digest).encode("ascii")).hexdigest()
    if matched.groups() != (ident, key):
        raise PublishError("Result filename does not match provenance")
    started, ended = stamp(value.get("claimed_utc")), stamp(value.get("finished_utc"))
    if datetime.fromisoformat(ended) < datetime.fromisoformat(started):
        raise PublishError("Reversed timestamps")
    return {
        "schema_version": 1, "experiment_id": ident,
        "approved_release_sha": rev, "manifest_sha256": digest,
        "runner": RUNNER, "cycles": cycles, "status": status, "outcome": outcome,
        "claimed_utc": started, "finished_utc": ended,
        "evidence": "self-reported fixed guest result; requires human review",
    }


def output_bytes(report):
    return (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")


def blob_sha(contents):
    return hashlib.sha1(b"blob " + str(len(contents)).encode()
                        + b"\0" + contents).hexdigest()


def private_file(path, owner):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                or info.st_mode & 0o077 or not 0 < info.st_size <= MAX_FILE):
            raise PublishError("Unsafe result file")
        data = os.read(fd, MAX_FILE + 1)
        if not 0 < len(data) <= MAX_FILE:
            raise PublishError("Oversized result")
    finally:
        os.close(fd)
    return json.loads(data)


def private_state(state):
    if state.is_symlink():
        raise PublishError("Publisher state is a symlink")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = state.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise PublishError("Publisher state permissions are unsafe")


def pending(source, state, owner):
    info = source.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o077):
        raise PublishError("Private result directory is unsafe")
    entries = sorted(source.iterdir())
    if len(entries) > MAX_SCAN:
        raise PublishError("Too many result files")
    for entry in entries:
        if not RECORD.fullmatch(entry.name) or (state / entry.name).exists():
            continue
        sanitized = sanitize(private_file(entry, owner), entry.name)
        if sanitized is not None:
            return sanitized, state / entry.name
    return None


def credential():
    parent = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not parent.startswith("/run/credentials/"):
        raise PublishError("Missing systemd credential directory")
    token_path = Path(parent) / "github_token"
    fd = os.open(token_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        data = os.read(fd, 1024)
    finally:
        os.close(fd)
    try:
        value = data.decode("ascii").strip()
    except UnicodeError as exc:
        raise PublishError("Invalid credential") from exc
    if not re.fullmatch(r"(?:github_pat_|ghs_)[A-Za-z0-9_]{12,500}", value):
        raise PublishError("Invalid GitHub credential format")
    return value


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = request.build_opener(NoRedirect)

    def call(self, verb, route, data=None, optional=False):
        if (verb not in ("GET", "POST") or not route.startswith("/")
                or re.search(r"[^A-Za-z0-9_./?=&:%-]", route)
                or ".." in route or "//" in route):
            raise PublishError("Unsupported GitHub URL")
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = request.Request(API + route, data=payload, method=verb,
                              headers={
                                  "Authorization": "Bearer " + self.token,
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28",
                                  "Content-Type": "application/json",
                                  "User-Agent": "slipcage-results-publisher/1",
                              })
        try:
            with self.opener.open(req, timeout=12) as response:
                if response.status not in (200, 201):
                    raise PublishError("Unexpected GitHub status")
                content = response.read(MAX_API + 1)
                if len(content) > MAX_API:
                    raise PublishError("Oversized GitHub response")
                return json.loads(content)
        except error.HTTPError as exc:
            if optional and exc.code == 404:
                return None
            raise PublishError("GitHub API status " + str(exc.code)) from None
        except (error.URLError, TimeoutError, OSError) as exc:
            raise PublishError("GitHub connection " + type(exc).__name__) from None

    def get(self, route, optional=False):
        return self.call("GET", route, optional=optional)

    def post(self, route, data):
        return self.call("POST", route, data=data)


def sha(value):
    if not isinstance(value, str) or not SHA40.fullmatch(value):
        raise PublishError("Invalid Git SHA")
    return value


def destination(report):
    ident, rev, manifest = (report["experiment_id"], report["approved_release_sha"],
                            report["manifest_sha256"])
    key = hashlib.sha256((ident + ":" + rev + ":" + manifest).encode()).hexdigest()
    branch = "results/" + ident.lower() + "-" + key[:24]
    path = "results/" + ident + "/" + rev + "-" + manifest + ".json"
    return branch, path


def find_pr(api, branch):
    head = parse.quote("soybeanfarmer:" + branch, safe="")
    prs = api.get("/pulls?state=all&head=" + head + "&per_page=25")
    if not isinstance(prs, list):
        raise PublishError("Invalid GitHub PR list")
    for pr in prs:
        if pr.get("head", {}).get("ref") == branch:
            if pr.get("state") == "open" or pr.get("merged_at") is not None:
                return pr
            raise PublishError("Result PR was closed; human review required")
    return None


def result_from_pr(pr, ident):
    number = pr.get("number")
    if type(number) is not int or not 1 <= number <= 100000000:
        raise PublishError("Bad GitHub PR number")
    return {"status": "submitted", "experiment_id": ident,
            "pull_request": "https://github.com/" + REPO + "/pull/" + str(number)}


def post_result(api, report):
    branch, path = destination(report)
    content = output_bytes(report)
    if len(content) > 2048:
        raise PublishError("Public report exceeds limit")
    base_ref = api.get("/git/ref/heads/main")
    base_sha = sha(base_ref["object"]["sha"])
    if api.get("/contents/" + path + "?ref=main", optional=True) is not None:
        return {"status": "already_merged", "experiment_id": report["experiment_id"]}
    prior_branch = api.get("/git/ref/heads/" + branch, optional=True)
    if prior_branch is None:
        root_commit = api.get("/git/commits/" + base_sha)
        base_tree = sha(root_commit["tree"]["sha"])
        new_tree = api.post("/git/trees", {
            "base_tree": base_tree,
            "tree": [{"path": path, "mode": "100644", "type": "blob",
                      "content": content.decode("ascii")}],
        })
        commit = api.post("/git/commits", {
            "message": "results: " + report["experiment_id"] + " fixed guest outcome",
            "tree": sha(new_tree["sha"]), "parents": [base_sha],
        })
        api.post("/git/refs", {"ref": "refs/heads/" + branch,
                               "sha": sha(commit["sha"])})
    else:
        # Recover safely if a previous attempt created the branch
        # but failed before opening or recording the pull request.
        file = api.get("/contents/" + path + "?ref=" + branch, optional=True)
        if (not isinstance(file, dict) or file.get("type") != "file"
                or file.get("sha") != blob_sha(content)):
            raise PublishError("Existing branch contents disagree")
    pr = find_pr(api, branch)
    if pr is None:
        pr = api.post("/pulls", {
            "title": "Result: " + report["experiment_id"] + " - " + report["status"],
            "head": branch, "base": "main", "draft": True,
            "body": ("Automated sanitized fixed-guest result. Self-reported evidence, "
                     "not a vulnerability claim or independent validation.\n\n"
                     "Experiment: " + report["experiment_id"] + "\n"
                     "Approved release: " + report["approved_release_sha"] + "\n"
                     "Outcome: " + report["status"] + "\n\n"
                     "Review this result and its approved experiment manifest before "
                     "merging. No guest logs or local paths were uploaded."),
        })
    return result_from_pr(pr, report["experiment_id"])


def save_receipt(path, value):
    temp = path.with_name("." + path.name + ".pending")
    with temp.open("x", encoding="utf-8") as out:
        os.chmod(temp, 0o600)
        json.dump(value, out, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(*, source=SOURCE, state=STATE, owner, submit=False, api=None):
    os.umask(0o077)
    private_state(state)
    lock_fd = os.open(state / ".publisher.lock",
                      os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        item = pending(source, state, owner)
        if item is None:
            return {"status": "idle", "reason": "no_completed_unpublished_results"}
        report, receipt = item
        if not submit:
            return {"status": "dry_run", "report": report}
        result = post_result(api if api is not None else GitHub(credential()), report)
        save_receipt(receipt, result)
        return result
    finally:
        os.close(lock_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)
    try:
        owner = pwd.getpwnam("slipcage-vmprobe").pw_uid
        result = run(owner=owner, submit=args.submit)
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            json.JSONDecodeError, BlockingIOError) as exc:
        print("slipcage-results-publisher: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
