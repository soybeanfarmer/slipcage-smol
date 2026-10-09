# Approved experiment queue: producer → single VPS consumer

Smol uses a **Git-reviewed queue** rather than automatic CVE discovery.
Human researchers select targets and approve executable experiments.
The first supported producer item is `experiments/EXP-0001.json`,
which names the **existing fixed arithmetic/SHA-256 microguest**
workload. There is no arbitrary command field, dynamic script loader,
fetch-from-URL hook, or VM image override.

## Approval and delivery

1. Create or edit a manifest through a reviewed GitHub pull request.
2. CI runs offline validation; the operator **manually publishes a Smol
   release**. The established release puller verifies that the tagged
   commit is on `main` with successful GitHub Actions validation.
3. Ansible installs the JSON manifests and consumer into root-owned
   paths under `/usr/local/lib/slipcage`. A new release publishes its
   commit SHA in a publicly readable, root-owned file
   `/var/lib/slipcage/deployed-sha` (the SHA is not a secret).
4. The **unprivileged** consumer checks that exact deployed SHA and
   strict JSON manifests. It runs at most **one** new approved experiment
   per invocation and uses only the fixed vetted guest lifecycle driver.
5. Before launching a guest, it atomically creates a private
   `claimed` JSON file under
   `/var/lib/slipcage-guest/experiment-results`. It later records
   `passed` or `failed` with release SHA, manifest SHA-256, fixed
   runner, timestamps and a path to local guest-run evidence.

Every new release commit is a new explicit run identity even if the
manifest is unchanged. Once claimed, the same identity will **not**
automatically retry, including after failure, interruption or reboot.
Preserve and investigate an interrupted `claimed` record. The
consumer's lock and the existing guest lifecycle flock prevent
concurrent runs; the existing deployment guard drains active work.

## First run (manual and safe)

**Do not enable unattended execution before confirming nested KVM
use is allowed by your host provider and checking the installed unit.**
After the approved release is deployed:

```bash
sudo systemctl cat slipcage-experiment-consumer.service
sudo systemctl start slipcage-experiment-consumer.service
sudo journalctl -u slipcage-experiment-consumer.service -n 40 --no-pager
sudo find /var/lib/slipcage-guest/experiment-results \
  -maxdepth 1 -type f -name 'EXP-*.json' -printf '%f\n'
```

The result directory is owned by the restricted probe account and is
private. A successful result has `"status":"passed"`; the exact
experiment commit is in `approved_release_sha`, not guessed from
advisory metadata. Underlying guest logs and manifests remain private.

After evaluating the first fixed experiment, the operator **may**
opt in to periodic queue consumption:

```bash
sudo systemctl enable --now slipcage-experiment-consumer.timer
```

The timer is installed but **disabled by default** and polls every
20 minutes after inactive, with jitter. Every new **manually approved
release** may cause one fixed guest run while the timer remains enabled.
To stop unattended experiments:

```bash
sudo systemctl disable --now slipcage-experiment-consumer.timer
```

Do not delete existing result claims merely to force re-execution.
Instead, review failures and create a new approved experiment revision.

## Security and scope

- One VPS; no message broker, dashboard, queue database or new remote
  service. Manifests are immutable for a deployed release and installed
  root-owned. Only `fixed_arithmetic_sha256_v1` with exactly one
  cycle is currently accepted. A new runner needs new reviewed code,
  tests, limits, and separate authorization.
- The consumer runs as `slipcage-vmprobe` in a systemd service with
  `PrivateNetwork=yes`, no shell command evaluation, no guest network,
  no persistent guest disks and a 1280-MiB memory quota. The existing
  lifecycle has its own timeouts and bounded run-artifact retention.
- **No GitHub write credential is installed on the VPS.** Results are
  local-only in this first version. A later PR may export carefully
  sanitized structured results through a narrowly scoped GitHub App.
  Raw guest logs, host paths, internal identifiers or unpublished
  findings should never be pushed to a public repository automatically.
- The reports-only backup service does **not** currently back up guest
  experiment results; treat those files as local, potentially ephemeral
  evidence until a separately approved retention/export plan exists.
