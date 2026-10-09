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

**Current status:** GitHub source and CI baseline only. The original
VPS still follows `soybeanfarmer/slipcage`. Smol now has a separate
release origin and fresh-host-only enrollment guard, but **has not been
deployed to any VPS**.

## What the reviewed v0.10 baseline does

| Capability | Behavior |
| --- | --- |
| Discover and triage | Dagu polls public GitHub/NVD advisory metadata every six hours. Fixed Python code filters, scores, deduplicates, queues and produces Markdown reviews in local SQLite/report storage. |
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
| `workflows/` | Reviewed Dagu discovery, metadata-review and smoke definitions |
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

## Run QEMU advisory discovery without another VPS

Open [QEMU research snapshot](https://github.com/soybeanfarmer/slipcage-smol/actions/workflows/qemu-research.yml)
in GitHub Actions and manually run it from reviewed `main` after the
workflow PR is merged. It searches **public QEMU/KVM advisory metadata**
in a bounded 7-, 14-, or 30-day publication window and produces a
short-lived SQLite/JSON research artifact. No QEMU guest launches,
source builds, exploit execution, network scans, or original VPS
deployment are involved. Publication backfill does not guarantee
complete historical coverage or a newly discovered vulnerability.

See [QEMU/KVM research MVP](docs/QEMU_RESEARCH_MVP.md) for exact scope,
data limitations, acceptance checks and safe operator steps. This is
an **on-demand research snapshot**, not a running independent smol
server or continuous vulnerability reproduction.

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

### Independent release channel — **fresh host only**

The smol deployer now targets **`soybeanfarmer/slipcage-smol`**,
requires a root-private smol ownership marker, and accepts only
manually approved smol releases on `main` with successful CI.
The bootstrap refuses an existing Slipcage installation, and Ansible
checks the marker before changing anything.

**Do not run** the smol bootstrap, Ansible playbook, or release
promotion to migrate the original production VPS. Same-named systemd
services and data paths still exist, so a side-by-side installation
or in-place migration is not supported by this PR. No current VPS
has been changed; an independent installation requires a *separate,
fresh* Ubuntu 24.04 VPS, its own host validation, and operator approval.

See [Independent smol deployment](docs/SMOL_DEPLOYMENT.md) for the
refusal gates and future separate-host procedure.

## Design guardrails

Keep local metadata research, conservative backup/restore assurance,
deployment draining, manual-only harmless VM experiments, and human
release approval. Prefer deleting obsolete explanation and eliminating
optional dependencies **after** establishing that no active service or
stored data relies on them. Never trade away process isolation, data
preservation or provider safety merely to reduce file count.

See [SECURITY.md](SECURITY.md) for the original technical constraints.
