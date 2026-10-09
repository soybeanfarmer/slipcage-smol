# Simplify Slipcage Smol: Dagu to native systemd

**Status: design and inactive prototype only.** This document and
`app/local_review.py` do not change the running v0.1.0 release.
Do not manually invoke the prototype against a Dagu-managed production
database or disable Dagu before the cutover gates are implemented.

## Target

One Ubuntu 24.04 VPS, SQLite as the authoritative research queue and
attempt ledger, flat Markdown reports, and systemd as the sole scheduler.
Keep the existing human-approved release/deployment boundary, per-job
maintenance lock, daily private snapshots, bounded scratch restores,
hourly health status, and manual-only benign guest experiments.
No replacement web dashboard, remote notification or external queue.

## What currently relies on Dagu

- `workflows/discover.yaml`: six-hour discovery, analyze and enqueue.
- `workflows/review-candidate.yaml`: one attempt-fenced metadata report.
- `workflows/smoke.yaml`: manual environment smoke.
- `app/recovery.py`: calls `dagu enqueue`; SQLite remains authoritative
  for candidate state, opaque attempts, retries and crash reconciliation.
- `slipcage-recover.timer`: recovers attempts and delivers them via Dagu.
- Ansible installs Dagu v2.18.1, its private configuration and runtime.
  The hourly health checker currently expects `isolab-dagu.service`.

## Proposed staged implementation

1. **Inactive review prototype (this PR):** Add a bounded local review
   runner using existing `recovery.claim_next`, `run_review`, and
   `recovery.reconcile`. Reuse claim tokens, stable filenames and retry
   limits. Unit-test normal runs, process budgets, existing queues and
   fail-closed errors. No systemd/Ansible activation in this step.
2. **Prepare native units:** Add six-hour `slipcage-discover.timer`
   and a bounded `slipcage-review.timer` that calls the local runner,
   each through `slipcage-guard run` as the unprivileged `isolab`
   account. Preserve `discover.sh` feed/analyze stages and remove only
   its `dagu enqueue` phase. Choose an explicit UTC schedule and bounded
   service timeouts. Make smoke available as the existing CLI.
3. **Fail-closed v0.1.0 cutover:** Under deployment maintenance/drain,
   inspect the SQLite outstanding `queued`/`running` attempts and
   Dagu execution state. Refuse an ambiguous or non-empty queue; never
   drop or silently reassign an in-flight attempt. Only on a clean
   handoff stop/disable Dagu and its recovery timer and activate native
   timers. Preserve existing Dagu state/logs for forensic review and
   rollback; no recursive deletion of research data or Dagu history.
4. **Remove Dagu dependencies:** Remove binary download, config, DAG
   installation and Dagu service installation from the playbook after
   the cutover is safe. Update hourly health checks and tests to require
   the new timers rather than the Dagu daemon. Preserve the deployment
   poller, backups, restore assurance and VM manual-only restrictions.
5. **Test before an approved release:** Validate offline unit tests and
   Ansible/systemd syntax. Test a fresh install and an upgrade of the
   already deployed v0.1.0 state, including a deliberately occupied
   queue that must refuse migration. Verify recovery following a
   deliberately interrupted review, idempotent reports, journal
   diagnostics, snapshot/restore integrity and no unattended VM work.

## Acceptance criteria

- Same SQLite schema and report paths; existing reviewed leads stay put.
- Six-hour advisory discovery and bounded automatic reviews work after
  restart and reboot, with explicit run quotas and no overlapping jobs.
- Failed/ambiguous attempts are not duplicated or discarded.
- Native systemd units honor the existing deployment maintenance lock.
- Backups, scratch restore, health status and release/CI checks pass.
- Dagu service and timers are disabled; no active scheduler depends on
  Dagu. Old Dagu state stays preserved until separately reviewed.
- SSH and dashboard port exposure do not increase; no new web UI.
- Migration is a new, manually approved release; never auto-deploy
  an unreviewed branch. Keep v0.1.0 running until those gates pass.

## Separate historical PR

[PR #5](https://github.com/soybeanfarmer/slipcage-smol/pull/5)
proposes manual GitHub Actions QEMU metadata research and was written
before the fresh Smol VPS was deployed. It changes `app/isolab.py`
and `scripts/discover.sh`, and its deployment assumptions are stale.
Review and reconcile it independently; do not merge it as part of the
systemd migration or assume it is an approved release.
