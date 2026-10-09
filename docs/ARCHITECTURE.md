# Slipcage Smol — current architecture

The development VPS is an execution environment for **human-selected
and Git-reviewed experiments**. It is not a vulnerability discovery or
advisory-triage agent.

```text
Human research and code review
              |
      GitHub Smol repository
              |
Manually approved release + CI
              |
       VPS pull deployer
              |
  Restricted manual benign guest probes
              |
   Local logs, evidence and reports
```

## Active services

- `slipcage-pull-deploy.timer`: checks approved Smol releases.
  Runs Ansible only for GitHub commits validated by CI.
- `slipcage-backup.timer`: creates verified daily reports-only
  snapshots, preserving old format-1 SQLite/reports backups.
- `slipcage-assurance.timer`: restores a recent backup in
  disposable scratch and verifies consistency.
- `slipcage-health.timer`: emits local journal alerts and records
  backup/assurance, free-space, failed-unit and guest-artifact status.
- Benign KVM microguest/systemd templates: manual only, unprivileged,
  diskless, networkless and bounded by systemd resource limits.

`slipcage-discover.*`, `slipcage-review.*`, Dagu and the automatic
SQLite candidate queue are **not active or installed** after the
advisory retirement release. The previous `research.sqlite3` stays
dormant as historical data and is preserved in a final verified
format-1 backup; no scheduled service requires it.

## Future experiment producer/consumer (not yet implemented)

A GitHub-reviewed experiment specification should bind a fixed,
allowlisted runner to a content-addressed commit and explicit
resource/time limits. A restricted consumer could record attempts
in a lightweight ledger and produce reproducible local result JSON.
Only reviewed, sanitized results should be proposed back to GitHub
via a narrowly scoped bot/PR. This architecture **does not** imply
arbitrary shell execution from Git, a public GitHub writer credential
or automatic guest attacks.

See [README](../README.md), [backup operations](BACKUPS.md) and
[scope](SMOL_SCOPE.md). The original v0.10 architecture is historical.
