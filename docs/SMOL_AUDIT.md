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
installed optional tooling**, not product SaaS features. This snapshot
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
| Optional off-server backup | `slipcage-offsite-backup.sh`, offsite systemd service/timer | Installed but disabled; user explicitly deferred encryption/destination setup | **Deferred** |
| VPS pull deployment | `bootstrap-pull.sh`, `pull-deploy.sh`, `slipcage-pull-deploy.*` | Original VPS polls manually approved GitHub releases | **Migration review required** |

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

1. **Original-repo deployment coupling (highest priority).**
   `scripts/pull-deploy.sh` still declares
   `REPO="soybeanfarmer/slipcage"`, expects that repo's
   release ancestry and runs Ansible against the existing server
   layout. The smol repo must **not** simply be bootstrapped onto
   the same running production VPS; treat redirecting the deployment
   channel as a separate, reviewed migration project.
2. **Misleading landing page.** The historical README starts
   at "starter v0.1" and calls released capabilities "proposals".
   It also promotes optional future security/fuzzing work that is
   outside the refined objective. Replacing it with a current-state
   operator overview is a safe first cleanup.
3. **Optional surface even when disabled.** Installed but
   unenabled offsite-backup and webhook alert services, pinned
   restic dependency, and an optional research build toolchain
   consume attention and sometimes packages. Removal is *not
   automatically safe*: playbook upgrades may leave pre-existing
   systemd units, credentials and directories behind.
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

## Proposed small-PR sequence (not yet implemented)

**PR 1 (this PR):** Audit and simplify navigation only.
Replace the historical README with a current-state summary;
record the component map and permanent project scope.
No code, tests, schemas, units, flags, or deploy targets change.

**PR 2:** Review and design smol release/deployment isolation.
Prove a clean repository origin and release/CI verification process
on a **separate sandbox**, or explicitly decide to keep smol
source-only. Do not repoint the original VPS or silently
reuse `/var/lib/slipcage`/database paths.

**PR 3:** Reduce optional installation only after review.
Candidates: never-used offsite-backup files and the unconfigured
webhook integration, or disabling heavyweight build toolchain by
default for fresh installations. First inventory any live service,
configuration, and necessary migrations so old installations
are not left in an ambiguous state. **Do not remove local daily
backups or weekly scratch restore.**

**PR 4:** Refactor the monolithic Ansible playbook only if it
reduces operator burden; require syntax tests, a fresh sandbox
installation, an idempotent repeat run, and an existing-installation
upgrade test before making it a deploy path.

We should favor fewer moving parts, not fewer safety checks.
