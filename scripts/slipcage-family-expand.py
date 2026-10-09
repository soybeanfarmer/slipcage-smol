#!/usr/bin/env python3
"""Expand reviewed bounded experiment families into fixed-runner queue manifests.

This planner cannot introduce commands, images, networking, URLs, or runner code.
It only materializes deterministic EXP manifests for the already-allowlisted
fixed arithmetic/SHA-256 guest runner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile

RUNNER = "fixed_arithmetic_sha256_v1"
FAMILY_ID = re.compile(r"FAM-[0-9]{4}\\Z")
FIELDS = {"schema_version", "id", "status", "runner", "experiment_id_start",
          "cycles", "repetitions"}
MAX_FAMILIES = 100
MAX_FAMILY_BYTES = 4096
MAX_EXPERIMENTS = 500
MAX_CYCLES = 3
MAX_REPETITIONS = 100


def trusted_json(path: Path, *, owner: int) -> dict:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o022 or not 0 < info.st_size <= MAX_FAMILY_BYTES):
        raise ValueError("Untrusted or oversized family file")
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_FAMILY_BYTES:
        raise ValueError("Invalid family size")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Family must be a JSON object")
    return value


def read_family(path: Path, *, owner: int) -> dict:
    if not path.name.endswith(".json"):
        raise ValueError("Family must be JSON")
    item = trusted_json(path, owner=owner)
    cycles = item.get("cycles")
    if (set(item) != FIELDS
            or type(item.get("schema_version")) is not int
            or item["schema_version"] != 1
            or not isinstance(item.get("id"), str)
            or not FAMILY_ID.fullmatch(item["id"])
            or path.name != item["id"] + ".json"
            or item.get("status") != "approved"
            or item.get("runner") != RUNNER
            or type(item.get("experiment_id_start")) is not int
            or not 1 <= item["experiment_id_start"] <= 9999
            or not isinstance(cycles, list) or not cycles
            or len(cycles) > MAX_CYCLES
            or any(type(v) is not int or not 1 <= v <= MAX_CYCLES for v in cycles)
            or len(set(cycles)) != len(cycles)
            or type(item.get("repetitions")) is not int
            or not 1 <= item["repetitions"] <= MAX_REPETITIONS):
        raise ValueError("Unsupported approved experiment family")
    count = len(cycles) * item["repetitions"]
    if count > MAX_EXPERIMENTS:
        raise ValueError("Family expands beyond queue limit")
    if item["experiment_id_start"] + count - 1 > 9999:
        raise ValueError("Family experiment IDs exceed supported range")
    return item


def expand_family(item: dict) -> list[dict]:
    result = []
    ident = item["experiment_id_start"]
    for _ in range(item["repetitions"]):
        for cycles in item["cycles"]:
            result.append({
                "schema_version": 1,
                "id": f"EXP-{ident:04d}",
                "status": "approved",
                "runner": RUNNER,
                "cycles": cycles,
            })
            ident += 1
    return result


def atomic_write(path: Path, value: dict) -> None:
    payload = json.dumps(value, sort_keys=True, indent=2) + "\\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".family-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def expand(*, families: Path, experiments: Path, owner: int = 0) -> dict:
    family_info = families.lstat()
    experiment_info = experiments.lstat()
    for info in (family_info, experiment_info):
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
            raise ValueError("Planner directory is untrusted")
    files = sorted(families.iterdir())
    if len(files) > MAX_FAMILIES:
        raise ValueError("Too many approved families")
    planned = []
    for path in files:
        if path.name.startswith("."):
            raise ValueError("Unexpected family directory entry")
        planned.extend(expand_family(read_family(path, owner=owner)))
    if len(planned) > MAX_EXPERIMENTS:
        raise ValueError("Families expand beyond queue limit")
    ids = [item["id"] for item in planned]
    if len(ids) != len(set(ids)):
        raise ValueError("Experiment ID collision between families")
    for item in planned:
        destination = experiments / (item["id"] + ".json")
        payload = json.dumps(item, sort_keys=True, indent=2) + "\\n"
        if destination.exists():
            if destination.is_symlink() or destination.read_text(encoding="utf-8") != payload:
                raise ValueError("Experiment ID collides with existing manifest")
            continue
        atomic_write(destination, item)
    return {"status": "expanded", "families": len(files), "experiments": len(planned)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", type=Path, required=True)
    parser.add_argument("--experiments", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = expand(families=args.families, experiments=args.experiments)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print("slipcage-family-expand: " + type(exc).__name__, file=os.sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
