# Slipcage Smol

**One development VPS. We research and approve experiments; the VPS runs
bounded experiments and retains reproducible evidence.**

Slipcage Smol no longer automatically searches vulnerability advisories,
scores candidates, or generates generic CVE reviews. Those decisions are
made by the operator and collaborators. The next engineering step is a
small Git-reviewed producer/consumer experiment queue, beginning with
a fixed benign guest test. Its consumer is installed, but its polling
timer is **disabled by default**; guest execution requires operator
opt-in. No GitHub write credentials or results PR automation are installed.

## Current capabilities

- **Manual benign KVM checks:** fixed, unprivileged, diskless,
  networkless Linux microguest boot and arithmetic/SHA-256 workloads,
  deliberately launched by the operator. Limited CPU, RAM and time;
  no arbitrary downloaded guest instructions.
- **Approved experiment queue:** reviewed JSON manifests in
  `experiments/` ship only via manually approved Smol releases.
  An unprivileged consumer accepts only the fixed arithmetic/SHA-256
  guest runner, records one durable result per experiment/release,
  and never retries interrupted or failed attempts automatically.
  The optional polling timer stays disabled until explicitly enabled.
- **Approved releases:** the existing Smol GitHub manual release flow
  and root-private channel marker, checked by the VPS pull timer.
- **Evidence:** private `/srv/isolab/reports`, manual guest-run artifacts
  under `/var/lib/slipcage-guest`, local journal logs.
- **Backups and checks:** daily reports-only verified backup snapshots,
  weekly disposable scratch restores, hourly passive systemd health.
  Historical SQLite-plus-reports snapshots are preserved unpruned.
- **Host safety:** systemd resource constraints, deployment drain guard,
  SSH-first remote administration. No public dashboard or extra worker.

This is not a hosted vulnerability scanner, CVE reproduction engine, fuzzing
service, or attack automation platform. Provider permissions and isolation
must be reviewed before adding new experimental workloads.

## What changed after v0.3

The old scheduled discovery and SQLite candidate-review pipeline was
retired. On deployment to the existing Smol development server the
installer first takes a **final verified legacy SQLite + reports
snapshot**, then disables and removes `slipcage-discover.*` and
`slipcage-review.*`, their Python applications, and the obsolete
QEMU/NVD backfill and ranking commands.

**Existing research data is not deleted.** The dormant original SQLite
file stays at `/srv/isolab/research.sqlite3`. The historical
`backup-*` directories under `/var/backups/slipcage` stay intact;
ongoing `reports-*` snapshots use a new format without SQLite.
Old backup formats remain readable by the restore tool.
Neither of these archives should be committed to the public repository.

## Current operator commands

```bash
sudo cat /var/lib/slipcage/deployed-sha
sudo systemctl list-timers --all 'slipcage-*' --no-pager
sudo systemctl --failed --no-pager
sudo systemctl start slipcage-backup.service
sudo systemctl start slipcage-assurance.service
sudo cat /var/lib/slipcage-assurance/status.json
```

For the first approved experiment producer → consumer workflow,
including a one-time manual run and optional timer opt-in, see
[approved experiment queue](docs/EXPERIMENT_QUEUE.md). For legacy
fixed guest operations consult [controlled experiments](docs/CONTROLLED_EXPERIMENTS.md)
and [guest lifecycle](docs/GUEST_LIFECYCLE.md). The authorized
host's research capabilities remain restricted by provider rules.

For backup format/migration details see [backup operations](docs/BACKUPS.md),
for release safeguards see [Smol deployment](docs/SMOL_DEPLOYMENT.md),
and for operational faults see [incident runbooks](docs/INCIDENT_RUNBOOKS.md).
Older milestone documents may mention deleted discovery components;
they are retained for historical context only.

## Development and release

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
bash -n scripts/*.sh
```

The GitHub CI additionally checks Ansible/YAML and builds inert test
guest images without booting them. Changes on `main` are not deployed
until a reviewed, manually published Smol release passes CI and is
pulled by the host's existing release timer.

This release implements the **first reviewed manifest → restricted
consumer → private structured result** path. The VPS does not push
results back to GitHub yet; that requires separate permissions and
privacy review. No general remote command runner or public logs are
part of this change.

## GitHub result PRs (opt in)

A manual-only publisher can send narrowly sanitized completed experiment
summaries to GitHub as **draft pull requests**. No GitHub credential or
publishing timer is installed automatically; only the operator can
configure and start it. No guest console logs or host paths are
exported. See [reviewing and publishing results](docs/EXPERIMENT_QUEUE.md).
