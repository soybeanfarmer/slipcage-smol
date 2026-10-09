# Slipcage-smol repository audit

**Audit scope:** exact source-tree clone of the original public
`soybeanfarmer/slipcage` tag `v0.10.0`, at commit
`f356d83b8cea2500c131da78eea6325f97067065`, copied into
`soybeanfarmer/slipcage-smol` baseline
`628b7f4290ddb1af271c49a2041a040d578a1e62`.

This is a **static source/dependency audit**, not proof of every
runtime state. The smol repository has not been separately deployed.

## At-a-glance footprint

The verified v0.10.0 Git tree contains **81 tracked files**
(about **360 KB** total tracked contents, no generated guest images
checked in).

| Area | Files | Role |
| --- | ---: | --- |
| `app/` | 3 | Research CLI, advisory intelligence, queue reconciliation |
| `workflows/` | 3 | Fixed Dagu discovery, metadata review, smoke |
| `scripts/` | 19 | Deployment guard, backups, restore, health, VM checks and operators' tools |
| `systemd/` | 20 | Unit/timer definitions, including opt-in and manual-only services |
| `playbooks/`, `templates/`, `group_vars/`, `inventory/` | 5 | Ansible installation and config |
| `tests/` | 13 | Offline regressions and safety checks |
| `docs/` | 12 | Historical milestone manuals and playbooks |
| `.github/` | 2 | CI and manually approved release workflow |
| Root files | 4 | README, SECURITY, .gitignore, Ansible config |

The bloat at this baseline is mainly **documentation chronology and
installed optional tooling**, not product SaaS features.

The counts in this section describe the immutable **original v0.10.0
baseline**, not the post-PR3 smol working tree. PR3 removes three tracked
files and one unused package requirement. No product SaaS code was
present at this baseline. This snapshot
has no account/billing/tenant/marketing application code.

## What actually runs and how

| Layer | Source of truth | Activation | Keep? |
| --- | --- | --- | --- |
| Public advisory discovery | `app/isolab.py`, `app/intelligence.py`, `scripts/discover.sh`, `workflows/discover.yaml` | Dagu scheduled every six hours after installation | **Core** |
| Metadata-only review/queue | `app/recovery.py`, `workflows/review-candidate.yaml`, `systemd/slipcage-recover.*` | Dagu queues, review recovery timer every 15 minutes | **Core** |
| Research state | SQLite `/srv/isolab/research.sqlite3`; Markdown `/srv/isolab/reports/` | Updated by reviewed discovery/review commands | **Protect** |
| Deployment safety | `scripts/slipcage-guard.py`, Ansible maintenance barrier | Every guarded research step; installation requires drained jobs | **Protect** |
| Local backup | `scripts/slipcage-backup.py`, `systemd/slipcage-backup.*` | Daily root-private backup timer, keep 14 verified completed sets | **Protect** |
| Restore assurance | `scripts/slipcage-restore-check.py`, `scripts/slipcage-assurance.py`, `systemd/slipcage-assurance.*` | Weekly bounded scratch restore, source never overwritten | **Protect** |
| Host health | `scripts/slipcage-health.py`, `systemd/slipcage-health.*` | Approx. hourly; local journal status/warnings | **Keep** |
| Disposable guest execution | `scripts/slipcage-kvm-probe.py`, guest lifecycle, build scripts, `slipcage-guest-cycles@.service`, `slipcage-experiment@.service` | **Manual-only**, fixed benign work; no timer | **Keep separately bounded** |
| Evidence safety | `slipcage-experiment-audit.py`, `slipcage-limits-check.py`, `slipcage-fault-drill.py`, `slipcage-fault-retention.py` | Manual-only read-only audits and guest-free drills; deletion requires explicit reviewed flags | **Keep** |
| Optional external alerts | `slipcage-alert-dispatch.py`, alert systemd service/timer | Installed but disabled, no configured endpoint | **Deferred/optional** |
| Off-server backup | Removed from smol (historical v0.10 included a dormant Restic runner and service/timer) | **No smol offsite implementation** | **Out of scope** |
| VPS pull deployment | `bootstrap-pull.sh`, `pull-deploy.sh`, `slipcage-pull-deploy.*` | Smol origin only on a separately enrolled fresh host; original VPS stays separate | **Guarded; sandbox validation pending** |

**Important:** "Installed" or "defined" does not mean enabled.
The Ansible playbook also installs development/QEMU packages because
`group_vars/all.yml` currently sets
`install_research_toolchain: true`. It never launches guest tests
during deployment; guest service templates remain manual-only.

## Main dependency / data flow

`Dagu discover (six-hour schedule)` →
`slipcage-guard` →
`scripts/discover.sh` →
`isolab.py sync + intelligence analyze + enqueue` →
`SQLite` → `Dagu metadata review` → `Markdown report`.

Independent local protection:

- Daily `slipcage-backup.service` makes a consistent SQLite
  snapshot and bounded report archive with manifest/verification.
- Weekly `slipcage-assurance.service` verifies latest backup
  by restoring into private disposable scratch space, records pass/fail.
- Hourly `slipcage-health.service` checks timers, backups,
  assurance freshness, disk capacity and stale incomplete artifacts.
- Human review/promotion controls pull deployment. The deployment
  maintenance lock prevents reviewed research jobs from overlapping
  an installation upgrade, with documented limits.

Manual-only path:
`systemctl start slipcage-experiment@1.service` invokes a fixed
microguest profile with network, disk, time and resource restrictions.
It is **not part** of advisory discovery or normal scheduled operations.

## Risks identified

1. **Independent release origin, but no same-host migration.**
   The follow-up smol deployment-isolation PR points
   `scripts/pull-deploy.sh` at the smol repository and requires
   a private smol bootstrap marker before polling or Ansible writes.
   Original and smol hosts still use historical service/data paths;
   the original production VPS must **never** be directly
   bootstrapped from smol. A migration is not included. See
   [SMOL_DEPLOYMENT.md](SMOL_DEPLOYMENT.md).
2. **Misleading landing page.** The historical README starts
   at "starter v0.1" and calls released capabilities "proposals".
   It also promotes optional future security/fuzzing work that is
   outside the refined objective. Replacing it with a current-state
   operator overview is a safe first cleanup.
3. **Optional surface even when disabled.** The dormant
   Restic/off-server backup script, service, timer, and package
   requirement are removed in smol PR 3. The separately opt-in HTTPS
   notifier and optional development toolchain are still present.
   Review any further removal separately: deleting a source file does
   not erase pre-existing installed units or configuration.
4. **Monolithic installation manifest.**
   `playbooks/site.yml` wires research, backups, health, guest
   tooling and optional modules in one play. Splitting deployment
   into roles may improve comprehension but would introduce a
   migration/integration risk if done before tests for an
   existing installation.
5. **Historical documentation drift.**
   Individual milestone docs accurately preserve design history,
   but some future-tense claims are stale relative to v0.10.
   Keep them as historical manuals; use the new README and
   `SMOL_SCOPE.md` for the current state.
6. **No independent smol production validation yet.**
   Smol CI passed on the exact cloned baseline, but the running VPS
   follows releases from the original repository. Do not equate
   a passing CI run with a tested smol production migration.

## Small-PR simplification record and next steps

**PR 1 (merged):** Audit and simplify navigation only.
Replace the historical README with a current-state summary;
record the component map and permanent project scope.
No code, tests, schemas, units, flags, or deploy targets change.

**PR 2 (merged):** Configure a distinct smol
release origin and fail-closed **fresh-host-only** bootstrap gate.
The existing server stays unchanged. Validate actual installation
only later on a separate operator-approved disposable sandbox
before calling independent production readiness proven.

**PR 3 (this PR):** Remove only the dormant off-server backup runner,
its two systemd units, Ansible install tasks and unused Restic package.
Do **not** touch local daily backups, weekly scratch restores, research
DBs or manual guest experiments. Smol has never published a release;
this PR does not delete any file/unit from a running host.

**Future separate review:** Decide whether the disabled HTTPS notifier
should remain as optional reliability tooling, and whether compiler/
QEMU build dependencies should be installed only when needed. Do not
remove existing packages/services from any host without a separate
migration plan and live-use inventory.

**PR 4:** Refactor the monolithic Ansible playbook only if it
reduces operator burden; require syntax tests, a fresh sandbox
installation, an idempotent repeat run, and an existing-installation
upgrade test before making it a deploy path.

We should favor fewer moving parts, not fewer safety checks.
