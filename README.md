# Slipcage-smol

**A small, single-operator security-advisory research lab.** It collects
public QEMU/KVM and container-runtime advisory **metadata**, helps
prioritize leads, and produces local Markdown notes. It also retains
carefully bounded, **manual-only** tests using a fixed, benign,
diskless and networkless Linux microguest.

This repository is a clean-source continuation of the reviewed
[Slipcage v0.10.0](https://github.com/soybeanfarmer/slipcage/releases/tag/v0.10.0)
baseline, **not** the later product expansion. The initial smol
baseline commit is [`628b7f4`](https://github.com/soybeanfarmer/slipcage-smol/commit/628b7f4290ddb1af271c49a2041a040d578a1e62);
its Git file tree exactly matches original v0.10.0 commit `f356d83`.
We are simplifying deliberately, beginning with the documentation and
component audit, before considering behavior changes.

**Current status:** Smol v0.1.0 is installed on the single development
VPS after a clean Ubuntu 24.04 reinstall. The next release replaces
the inherited Dagu scheduler with native systemd timers.

## What the reviewed v0.10 baseline does

| Capability | Behavior |
| --- | --- |
| Discover and triage | Native systemd timers run six-hour GitHub/NVD advisory ingestion and bounded local SQLite-backed review jobs that produce Markdown reports. |
| Guard operational changes | Research jobs hold a deployment guard; upgrades must drain active guarded work. |
| Protect research data | Root-private daily verified local SQLite/report backups (retain 14 successful sets) and a weekly bounded restore into disposable local scratch space. |
| Monitor reliability | Hourly read-only health checks for services, backup freshness, restore status, free disk space and incomplete artifacts; local systemd journal warnings. |
| Exercise benign VM probes | Manual-only, unprivileged, time/resource-bounded, networkless, diskless guest boots and fixed arithmetic/SHA-256 tests; records can be audited without launching a guest. |

No product accounts, billing, hosted web SaaS, multi-tenancy, automated
exploit reproduction, fuzzers, hypervisor escapes or network scans.
Advisory descriptions and URLs are treated as **untrusted data**, not
commands or proof that a vulnerability exists.

Health issues are reported **locally** in private status JSON and the
systemd journal; smol does not install an external webhook notifier or
send operational messages off the VPS. The unused Restic/off-server-backup
integration has also been **removed**. Smol does **not** provide
off-server disaster recovery. Daily local backups and weekly verified
scratch restores remain unchanged.

## Where the code lives

| Path | Why it exists |
| --- | --- |
| `app/isolab.py`, `app/intelligence.py`, `app/recovery.py` | Metadata ingestion, scoring, review reports and guarded queue recovery |
| `app/local_review.py`, `systemd/` | Local bounded review worker and native discovery/review timers |
| `scripts/` | Local backups, scratch restores, operator diagnostics, fixed guest lifecycle and deployment guard |
| `systemd/` | Explicit services, resource limits, timers and disabled/manual-only templates |
| `playbooks/site.yml` | Ubuntu 24.04 host installation and maintenance/drain boundary |
| `tests/` | Python regression and safety-boundary tests |
| `docs/` | Operations, historical milestones, incident response and current smol audit |

Read [**Smol scope and safety rules**](docs/SMOL_SCOPE.md) first,
then [**the repository audit and proposed cleanup sequence**](docs/SMOL_AUDIT.md)
and the [**benign guest dependency audit**](docs/SMOL_DEPENDENCIES.md).
For specific v0.10 operations, consult
[backup operations](docs/BACKUPS.md),
[controlled experiments](docs/CONTROLLED_EXPERIMENTS.md),
[operational assurance](docs/OPERATIONAL_ASSURANCE.md), and
[incident runbooks](docs/INCIDENT_RUNBOOKS.md).
Historical documentation is preserved for context but may contain
future-tense instructions from older versions.

## Safe local development

Work on a fresh branch and use small pull requests. Python's tests are
offline and do not launch a guest, operate on the VPS or require private
research artifacts:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app scripts tests
bash -n scripts/*.sh
```

GitHub CI also validates Ansible/YAML syntax and **builds but never boots**
the inert test initramfs. Review CI results before merging.

### Development deployment — approved releases only

The bootstrap enrolls a fresh Ubuntu 24.04 VPS into the
`soybeanfarmer/slipcage-smol` release channel. The development server
now runs Smol v0.1.0 and can be upgraded in-place with manually approved
GitHub releases once CI validates the exact tagged commit.

The next release switches from Dagu to systemd scheduling. No second
VPS is needed. Research data, local backups and old Dagu history remain
unless the operator separately chooses to delete them. The Dagu web
dashboard will no longer be served. See [systemd transition](docs/SYSTEMD_MIGRATION.md).

## Design guardrails

Keep local metadata research, conservative backup/restore assurance,
deployment draining, manual-only harmless VM experiments, and human
release approval. Prefer deleting obsolete explanation and eliminating
optional dependencies **after** establishing that no active service or
stored data relies on them. Never trade away process isolation, data
preservation or provider safety merely to reduce file count.

See [SECURITY.md](SECURITY.md) for the original technical constraints.
