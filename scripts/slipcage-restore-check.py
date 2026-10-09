#!/usr/bin/env python3
"""Restore a verified format-2 report archive or legacy format-1 DB/reports into scratch.

Never writes live data; refuses links and path traversal.
"""
from __future__ import annotations

import argparse
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
BACKUP_HELPER = HERE / "slipcage-backup.py"
if not BACKUP_HELPER.is_file():
    BACKUP_HELPER = HERE / "slipcage-backup"
LOADER = SourceFileLoader("slipcage_backup", str(BACKUP_HELPER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


def drill(source: Path, destination: Path) -> dict:
    """Verify, unpack into scratch, verify restored DB, and atomically publish."""
    original = backup.verify_backup(source)
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("Restore drill parent must be an existing real directory")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Refusing to overwrite an existing restore destination")
    staging = Path(tempfile.mkdtemp(dir=parent, prefix=".restore-drill-"))
    os.chmod(staging, 0o700)
    try:
        if original["format"] == 1:
            restored_db = staging / "research.sqlite3"
            # Legacy database copy is closed/verified by backup.verify_backup.
            with (source / "research.sqlite3").open("rb") as reader:
                with restored_db.open("xb") as writer:
                    shutil.copyfileobj(reader, writer)
            os.chmod(restored_db, 0o600)
        reports = staging / "reports"
        reports.mkdir(mode=0o700)
        with tarfile.open(source / "reports.tar.gz", "r:gz") as archive:
            for member in archive:
                # verify_backup already validates members, but repeat the check.
                rel = Path(member.name)
                if (not member.isfile() or len(rel.parts) != 2
                        or rel.parts[0] != "reports"
                        or rel.parts[1] in ("", ".", "..")
                        or member.size > backup.MAX_REPORT_BYTES):
                    raise ValueError("Unsafe entry in report archive")
                reader = archive.extractfile(member)
                if reader is None:
                    raise ValueError("Cannot read archived report")
                with reader:
                    with (reports / rel.parts[1]).open("xb") as out:
                        shutil.copyfileobj(reader, out)
                os.chmod(reports / rel.parts[1], 0o600)
        report_count = len(list(reports.iterdir()))
        if report_count != original["reports"]:
            raise ValueError("Restored reports do not match verified backup")
        result = {"verified": True, "restored_to": str(destination),
                  "reports": report_count, "format": original["format"],
                  "live_data_modified": False}
        if original["format"] == 1:
            count = backup.check_sqlite(restored_db)
            if count != original["candidates"]:
                raise ValueError("Restored legacy SQLite count differs")
            result["candidates"] = count
        os.replace(staging, destination)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    args = p.parse_args(argv)
    os.umask(0o077)
    try:
        result = drill(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error, tarfile.TarError,
            json.JSONDecodeError) as exc:
        print(f"slipcage-restore-check: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
