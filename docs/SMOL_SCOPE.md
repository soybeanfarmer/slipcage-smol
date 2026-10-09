# Slipcage Smol — active development scope

One operator-led, Git-reviewed experiment lab on a single Ubuntu
development VPS. Humans select research questions and prepare concrete
experiments; only approved, bounded test workloads should execute
on the host. The repository is intended to become the authoritative
experiment queue and curated results record. The consumer and GitHub
result PR mechanism are **future work**, not current capabilities.

We are not building an automatic advisory crawler, CVE scoring system,
remote scanner, exploit reproduction service, product, or dashboard.

## What remains now

- Explicitly launched fixed benign nested-KVM boot and arithmetic/hash
  checks; manual only, no guest network or persistent disks.
- Systemd sandbox/resource limits and the deployment maintenance guard.
- Private reports and existing legacy SQLite research evidence
  **preserved but not automatically queried or updated**.
- Reports-only daily verified local backups and weekly scratch restore;
  historical SQLite-plus-reports backups are retained without automatic
  deletion. No off-server disaster recovery is provided.
- Hourly local-only health status and journal warnings.
- GitHub CI and manually approved Smol release deployment on the existing
  enrolled development VPS.

No untrusted PR content, advisory metadata, or arbitrary YAML `command`
field is automatically executed. A future consumer must accept only
explicitly reviewed, allowlisted runners/parameters and bind execution
to an approved commit SHA. Results destined for the public GitHub
repository must be sanitized; raw logs and unpublished findings stay
in private storage.

The original Slipcage v0.10.0 baseline and earlier Smol milestones are
historical references, not instructions for the current dev VPS.
