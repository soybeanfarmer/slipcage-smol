# Focused QEMU/KVM advisory research (native Smol)

Slipcage Smol uses **Python, SQLite, Markdown and systemd** on one
Ubuntu development VPS. This feature brings the useful QEMU discovery
pieces from [historical PR #5](https://github.com/soybeanfarmer/slipcage-smol/pull/5)
into the native application; no GitHub Actions research runner,
additional database, web dashboard, or Dagu dependency is needed.

## Existing automated work

`slipcage-discover.timer` runs every six hours and fetches bounded
public GitHub advisory and recent-modified NVD metadata for **both**
hypervisors and container runtimes. `slipcage-review.timer` runs
every 15 minutes, producing private Markdown metadata reviews from
pending SQLite candidates. Neither job launches a VM or runs a PoC.

A focused manual `sync --focus qemu` is also available. It filters
newly ingested metadata to advisories mentioning QEMU or KVM without
discarding existing container findings. The default `sync` remains
mixed-scope. These are keyword matches, not proof an advisory affects
a version used by this host.

## Explicit NVD publication-date backfill

Ordinary scheduled NVD discovery looks at recent *modifications*. To
investigate a specific publication period, run a manual 1–30-day
NVD search over fixed QEMU and KVM terms. This changes the existing
SQLite metadata database and is safe to repeat for the same window.

On the authorized Smol VPS (from any directory), example dates:

```bash
sudo -u isolab /usr/local/bin/slipcage-guard run \
  /usr/bin/python3 /opt/isolab/app/isolab.py backfill-qemu \
  --db /srv/isolab/research.sqlite3 \
  --start-day 2026-09-01 --end-day 2026-09-14
```

This contacts only NVD's public CVE API. It allows at most **three
pages of 200 records per keyword** (QEMU, KVM). The dates must span
1–30 inclusive calendar days. It fetches all pages before writing any
candidates to the database; a timeout, inconsistent pagination, too
many results, or incomplete page aborts the batch rather than saving
a partial backfill. If the API returns an error or rate limit, wait
or choose a smaller date window; don't schedule repeated bulk searches.

Duplicate NVD CVEs are merged by stable source ID. An existing
reviewed candidate is not reset to pending by a repeat search.
QEMU/KVM focus now uses the **affected subsystem heading** for Linux
CVEs, not an incidental mention of testing inside a QEMU guest.
Previously stored context-only candidates are retained in SQLite, but
excluded from the focused leads view.
Research scores and upstream commit references are heuristic and
not confirmed patch applicability.

## Ranked lead shortlist

To view up to 15 strongest QEMU/KVM leads currently in SQLite:

```bash
sudo -u isolab /usr/bin/python3 /opt/isolab/app/isolab.py qemu-leads \
  --db /srv/isolab/research.sqlite3 --limit 15
```

The command prints JSON with source, CVE, affected subsystem, x86-64
lab-fit category, research-fit score, status, and *unverified* allowlisted
upstream commit links, where available. It sorts direct x86-relevant
subsystems first, then unspecified architecture, then other-architecture
subsystems (e.g. KVM PowerPC), and by research score within each group.
It does not enqueue reviews, download PoCs or run guests. This is an
operator-priority heuristic, **not** evidence that the VPS is affected,
severity, exploitability, or novelty.
The resulting reports under `/srv/isolab/reports` remain private.

## Verify

```bash
sudo systemctl is-active slipcage-discover.timer slipcage-review.timer
sudo systemctl --failed --no-pager
sudo -u isolab /usr/bin/python3 /opt/isolab/app/isolab.py status \
  --db /srv/isolab/research.sqlite3
```

Review source advisories and upstream patches manually before drawing
conclusions. This feature is metadata triage, not vulnerability
reproduction, guest testing, fuzzing, or host/provider scanning.
