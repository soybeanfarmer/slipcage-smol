# Smol local backups: reports and historical research archive

The ongoing backup schedule runs daily using `slipcage-backup.service`.
These backups are **local to the VPS** and do not protect against a lost
disk, lost VPS, or provider/account outage.

## One-time migration from automatic advisory research

Before the installer removes discovery/review services on an existing
Smol VPS, the deployment maintenance gate drains research work and
the **previous** backup helper snapshots the final
`/srv/isolab/research.sqlite3` and `/srv/isolab/reports` content.

That snapshot is verified before retirement proceeds. A root-private
marker records successful preservation. All prior `backup-*`
snapshots remain in `/var/backups/slipcage`, **outside the new
retention pruner**. The legacy SQLite database itself is also left
untouched and is no longer an active queue. The cleanup does not
silently erase these artifacts.

A fresh install with no legacy database skips this step.

## New daily backups (format 2)

- Root-private `/var/backups/slipcage/reports-<UTC timestamp>/`.
- A bounded `reports.tar.gz` of regular files directly inside
  `/srv/isolab/reports`, up to 128 MiB per file, 512 MiB combined.
- `manifest.json` format 2: SHA-256 + byte size of the archive,
  verified entries and report count. No SQLite dependency.
- Retain 14 verified **format 2** snapshots. Older format 1
  `backup-*` sets are retained and remain verifiable using
  `slipcage-backup verify /var/backups/slipcage/backup-...`.
- Weekly sandboxed restore assurance reconstructs the newest complete
  archive into a disposable scratch directory. The original report
  files are not overwritten or modified.
- The old format 1 archive verifier and scratch restore still
  understand historical SQLite snapshots and test their integrity.

## Operations

```bash
sudo systemctl start slipcage-backup.service
sudo journalctl -u slipcage-backup.service -n 40 --no-pager
sudo systemctl start slipcage-assurance.service
sudo cat /var/lib/slipcage-assurance/status.json
sudo ls -ld /var/backups/slipcage/reports-*
```

The latest assurance should show `"passed": true` and
`"live_data_modified": false`. There is no unattended destructive
restore of reports or historical research. Report archives do not
include private guest-run evidence or arbitrary future experiment
results unless that storage coverage is explicitly extended.

**There is no offsite backup.** Keep unpublished/valuable data outside
this VPS as well, using an independently controlled encrypted copy.
