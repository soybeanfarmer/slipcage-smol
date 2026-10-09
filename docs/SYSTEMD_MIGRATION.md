# Smol: replace Dagu with systemd (development server)

This branch **implements the cutover**, rather than preserving two
schedulers. Smol v0.1.0 ran Dagu on the same development VPS. We
accept breaking removal of the dashboard and Dagu workflow interface.

## After approving a new release

The pull deployer still checks a manually published Smol release on main,
an approved commit and CI. Ansible then:
1. Enters the existing deployment guard and waits for guarded jobs.
2. Stops/disables the Dagu service and its legacy recovery timer.
3. Removes the obsolete Dagu systemd units and binary.
4. Installs the local bounded review worker and two native systemd
   oneshot/timer pairs, then enables the two timers.
5. Retains the SQLite database, reports, root-private local backups,
   weekly scratch restore, hourly health service and manual-only benign
   VM probes; it does not delete prior Dagu history under /var/lib/dagu.

The first scheduled review will conservatively reconcile stale legacy
queued/running attempts. Queued attempts may delay new reviews by
30 minutes; abandoned running attempts are reclaimed only when the
recorded worker can be proven dead. Ambiguous work remains blocked
and requires inspection. We intentionally do not add a data wipe.

## Native jobs

- `slipcage-discover.timer`: UTC 00:17/06:17/12:17/18:17 with up to
  2 minutes jitter. Calls `scripts/discover.sh` to fetch bounded public
  advisory metadata and run deterministic scoring. No Dagu dispatch.
- `slipcage-review.timer`: start 10 min after boot; runs every
  15 min after the previous run. Processes up to three candidates
  sequentially using SQLite attempt tokens and stable Markdown reports.
- Both use `slipcage-guard run`, run as unprivileged `isolab`,
  enforce systemd time/resource limits and write logs to journald.
- The old `smoke` command is still available directly using
  `sudo -u isolab python3 /opt/isolab/app/isolab.py smoke --output /srv/isolab/reports`.

## Basic verification

```bash
sudo systemctl list-timers --all 'slipcage-*' --no-pager
sudo systemctl is-active slipcage-discover.timer slipcage-review.timer
sudo systemctl is-active isolab-dagu.service  # should be inactive/unknown
sudo systemctl start slipcage-review.service
sudo journalctl -u slipcage-review.service -n 60 --no-pager
sudo systemctl start slipcage-discover.service
sudo journalctl -u slipcage-discover.service -n 60 --no-pager
sudo systemctl start slipcage-health.service
sudo cat /var/lib/slipcage-health/status.json
```

No web dashboard remains. Use SQLite read-only diagnostics, status JSON
and systemd journals. Existing `/var/lib/dagu` directory is intentionally
not deleted automatically.

## Old PR

[PR #5](https://github.com/soybeanfarmer/slipcage-smol/pull/5)
predates deployment and proposed an on-demand GitHub Actions QEMU
metadata workflow based on the old second-VPS assumption. Reassess it
separately from this scheduler replacement.
