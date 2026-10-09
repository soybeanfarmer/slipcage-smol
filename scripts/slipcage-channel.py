#!/usr/bin/env python3
"""Fail-closed ownership gate for a FRESH, independently bootstrapped smol VPS.

No path overrides on the command line: tests inject paths directly into
the pure inspection functions. This does not migrate an existing host.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys

CHANNEL = "soybeanfarmer/slipcage-smol"
MARKER = Path("/etc/slipcage/release-channel")
BLOCKERS = (
    Path("/etc/slipcage"),
    Path("/var/lib/slipcage"),
    Path("/var/lib/dagu"),
    Path("/srv/isolab"),
    Path("/opt/isolab"),
    Path("/var/backups/slipcage"),
    Path("/usr/local/sbin/slipcage-pull-deploy"),
    Path("/usr/local/bin/slipcage-guard"),
    Path("/etc/systemd/system/isolab-dagu.service"),
    Path("/etc/systemd/system/slipcage-pull-deploy.service"),
    Path("/etc/systemd/system/slipcage-pull-deploy.timer"),
)


def occupied(path: Path) -> bool:
    """Detect both actual entries and dangling symlinks without following them."""
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def require_pristine(blockers=BLOCKERS) -> None:
    found = [str(path) for path in blockers if occupied(path)]
    if found:
        raise ValueError(
            "Refusing fresh smol bootstrap: existing service/data/state paths: "
            + ", ".join(found)
        )


def require_enrolled(marker: Path = MARKER, *, expected_uid: int = 0) -> None:
    """Root-owned, regular, private and exact-channel identity only."""
    parent_info = marker.parent.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode) or
            parent_info.st_uid != expected_uid or
            stat.S_IMODE(parent_info.st_mode) != 0o700):
        raise ValueError("Unsafe smol channel configuration directory")
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or
                info.st_size > 128):
            raise ValueError("Invalid smol channel marker metadata")
        content = stream.read(129)
    if content != (CHANNEL + "\n").encode("ascii"):
        raise ValueError("This host is not enrolled for the smol release channel")


def enroll(*, marker: Path = MARKER, blockers=BLOCKERS, expected_uid: int = 0) -> None:
    """Enroll only an unoccupied host, and never overwrite existing state."""
    require_pristine(blockers)
    marker.parent.mkdir(mode=0o700)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write((CHANNEL + "\n").encode("ascii"))
        out.flush()
        os.fsync(out.fileno())
    require_enrolled(marker, expected_uid=expected_uid)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pristine", "enroll", "enrolled"))
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("slipcage-smol-channel: root required", file=sys.stderr)
        return 2
    try:
        if args.command == "pristine":
            require_pristine()
        elif args.command == "enroll":
            enroll()
        else:
            require_enrolled()
    except (OSError, ValueError) as exc:
        # Refusal is explicit; never mutate or delete the detected old state.
        print(f"slipcage-smol-channel: {exc}", file=sys.stderr)
        return 1
    print(f"slipcage-smol-channel: {args.command} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
