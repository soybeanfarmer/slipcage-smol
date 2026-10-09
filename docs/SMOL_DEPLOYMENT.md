# Independent Slipcage-smol release channel

**Scope:** prepare an independent, human-approved GitHub release channel
for a **separate, fresh Ubuntu 24.04 x86-64 host**. This is NOT a migration
or takeover procedure for the existing Slipcage VPS.

## What changed

- The smol pull deployer now checks **only**
  `soybeanfarmer/slipcage-smol` GitHub releases and verifies that
  the exact tagged commit is on **smol main** with a successful
  GitHub Actions `validate` check. It continues to honor only
  a manually published non-draft, non-prerelease release.
- A new `slipcage-channel.py` preflight refuses smol bootstrap
  if it finds an existing Slipcage app, installation state,
  research data, backups, service, or original deployment marker.
  It runs **before package installation or filesystem changes**.
- On a genuinely fresh host, successful operator-invoked bootstrap
  creates a root-private marker at
  `/etc/slipcage/release-channel`, containing exactly
  `soybeanfarmer/slipcage-smol`. This happens only after rechecking
  that the host is still pristine.
- Every smol pull check requires that marker **before network access,
  state-lock acquisition, a clone, or Ansible execution**.
- Direct execution of `playbooks/site.yml` fails during Ansible
  pre-tasks unless the private, root-owned smol marker is present
  and correct. An original Slipcage VPS does not have this marker.
- The manually approved GitHub workflow is clearly named
  `Approve Slipcage-smol Release`, with its own repository-local
  release/CI pipeline.

The existing Ansible application paths, systemd unit names, SQLite
and report formats **remain unchanged**. This PR intentionally
does not introduce a high-risk data migration or side-by-side
installation on the same VPS.

## On the existing original Slipcage VPS

**Do not run any bootstrap, playbook, setup, release or
deployment commands from smol on this VPS.** Keep the original
`soybeanfarmer/slipcage` deployment channel and its existing
`/srv/isolab`, `/var/backups/slipcage` and
`/var/lib/slipcage` state intact.

The smol bootstrap is expected to refuse that host before it changes
anything. Do not bypass the marker or remove the old state to
force smol installation.

## Separate fresh-host workflow (later, with operator approval)

1. Select a distinct authorized Ubuntu 24.04 x86-64 VPS, and decide
   whether benign nested-KVM probes are permitted. Establish SSH
   hardening and a private way to access the loopback-only Dagu UI.
2. Independently review the scripts and host isolation plan.
   Provision a *fresh* host; inspect the channel preflight result
   before installing packages. Never share SSH keys or private
   configuration in a chat.
3. When explicitly approved, clone `soybeanfarmer/slipcage-smol`
   on that fresh host and inspect `scripts/bootstrap-pull.sh`.
   Only then run the bootstrap as the administrator.
4. Review smol CI and explicitly publish a **new smol release**
   using the smol repository's manual GitHub Release workflow.
   The release in the original Slipcage repo has no standing here.
5. The separate host's poller validates smol tag ancestry and CI,
   then invokes the unchanged guarded Ansible installer. Validate
   dashboard binding, metadata ingest, local backups, scratch
   restore, health and evidence safety before considering the host
   operational. No VM workloads start on installation.
6. Keep smol releases and production promotions human-approved.
   Revisit rollback, disk space, server quotas, log hygiene and
   state/backup preservation before any upgrade from live research.

**Not performed in this PR:** new VPS provisioning; bootstrap execution;
VPS migration; original host modifications; release publication;
backups transferred between hosts; opening dashboard ports; enabling
fuzzing; external alert enrollment; off-server encrypted backups.

## Failure and recovery boundaries

- Preflight refusal means **stop and investigate**, not remove old
  files. An interrupted bootstrap may leave an explicit private
  marker or partial installation; do not delete it or rerun blindly.
- If deployment fails after the research guard enters maintenance,
  it intentionally preserves maintenance. Follow existing runbooks;
  do not force unlock or overwrite SQLite as a workaround.
- The marker is an operational safety interlock, **not a security
  sandbox** against a malicious root administrator who can change
  local programs or marker contents. Independent hosts/permissions
  and code review are still essential.
- Existing smol binaries and data paths retain the historical
  `slipcage` names **only on their separate host**; these do not
  imply co-installation compatibility.
- The repo still contains opt-in, disabled notification/offsite
  components. They do not gain permission to activate.
