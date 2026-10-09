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

Each **new experiment ID or changed manifest digest** is a new run
identity. Publishing an unrelated release does **not** rerun unchanged
manifests. Each result still records the approved release SHA of its
actual execution. Once claimed, the same experiment content will **not**
automatically retry, including after failure, interruption or reboot.
Preserve and investigate an interrupted `claimed` record. The
consumer's lock and the existing guest lifecycle flock prevent
concurrent runs; the existing deployment guard drains active work.

## One-time bootstrap puller transition

The initial bootstrap installed the Smol release puller at
`/usr/local/sbin/slipcage-pull-deploy`. Earlier Ansible releases updated
the application but did **not** refresh the puller. That meant the
v0.5.0 repository fix for the public release-SHA file's mode
(`0644`) was not yet present in the **installed** puller. The existing
`deployed-sha` therefore remained `0600`, which prevented the
unprivileged consumer from reading the release identity.

From this change onward, every approved release **atomically refreshes
the installed puller** from the same validated release snapshot. The
new puller writes a root-owned, read-only-to-others `deployed-sha`
file. The **first** deployment made with the old puller can still
finish by overwriting the SHA with mode `0600`, so on that transition
the operator must run the following once (without loosening any other
permissions):

```bash
sudo chmod 0644 /var/lib/slipcage/deployed-sha
sudo -u slipcage-vmprobe test -r /var/lib/slipcage/deployed-sha
```

This is a public Git SHA, **not** the root-private release-channel
marker, and does not contain credentials. Never change the permissions
on `/etc/slipcage/release-channel` or on guest evidence directories.

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

The timer is installed but **disabled by default**. Once enabled, it
activates approximately one minute after the preceding run finishes
(with up to 15 seconds of jitter). New **manually approved manifest
content** is processed automatically after the release is installed.
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

## Sanitized results returned to GitHub (manual opt-in)

The isolated `slipcage-results-publisher.service` submits **one completed
experiment result** as a **draft pull request** per invocation. This is
separate from the guest consumer. It never runs automatically, and it
does not start or repeat guest experiments.

The publisher reads only private completed `EXP-*.json` records, then
builds a brand-new public object with fixed fields: experiment ID,
approved release SHA, manifest hash, allowed runner, status, outcome and
UTC timestamps. It **never includes** run-directory paths, console logs,
exception messages, host identity or arbitrary input fields. Failed and
successful completed experiments are eligible; interrupted `claimed`
records are not.

Each sanitized report goes only under `results/EXP-XXXX/` on a new
`results/...` branch, then into a **draft PR** for human review.
No result is written directly to `main`. A result claims to describe
a fixed known-answer test, **not a vulnerability finding**.

### Inspect without credentials (safe dry run)

After deploying the approved release:

```bash
sudo python3 /usr/local/lib/slipcage/results-publisher.py --dry-run
```

This prints the *exact public allowlisted fields* for the first
unpublished completed record. No GitHub API requests or credentials are
used. The original guest evidence is left untouched.

### Credential setup (operator action required)

For the first integration, create a **fine-grained GitHub personal access
token** restricted to the single repository
`soybeanfarmer/slipcage-smol`, with only **Contents: read/write** and
**Pull requests: read/write** repository permissions. Prefer a dedicated
automation identity and short expiration. Do not grant administration,
Actions or access to other repositories.

A PAT cannot in general be limited to writing only `results/` branches,
so apply GitHub branch protections/rulesets to `main`: require
reviewed PRs and forbid direct pushes/bypass by the bot account. The
publisher's fixed paths are defense in depth, not a GitHub-level
permission boundary.

Store the token **only on the VPS**, root-owned and mode 0600, in
`/etc/slipcage/github-results-token`. Never paste it into chat, place
it in Git, supply it via CLI arguments, or echo it to a terminal. A
safe interactive setup that prompts without echo:

```bash
sudo bash -c 'umask 077; read -r -s -p "GitHub result token: " token; printf "\n"; printf "%s\n" "$token" > /etc/slipcage/github-results-token; unset token'
sudo chown root:root /etc/slipcage/github-results-token
sudo chmod 0600 /etc/slipcage/github-results-token
```

Systemd `LoadCredential` exposes the token only inside this manually
started oneshot. The publisher has **no KVM device access**, cannot read
the raw guest-run directory through its mount namespace, and uses
bounded CPU, RAM and time. It needs outbound HTTPS to
`api.github.com`, but no inbound network service.

### Submit a draft PR

After reviewing the dry-run output and the GitHub token permissions:

```bash
sudo systemctl start slipcage-results-publisher.service
sudo journalctl -u slipcage-results-publisher.service -n 30 --no-pager -l
```

The journal should report `submitted` and a PR URL, or
`already_merged` if the identical sanitized report is already on
`main`. Review that draft and its source manifest before merging.

The publisher writes private per-result receipts. Repeated runs are
idempotent. If a network failure happens after branch creation but
before opening the PR, retry will verify the exact blob and continue.
If a PR is closed without merging, manual review is required before
another attempt.

**Nothing in this release supplies a token, starts a publisher, or
enables a publishing timer.** Raw guest artifacts remain local and are
not covered by the current reports-only backup schedule. Rotate/revoke
the PAT if compromised.

## Sequential queue draining (opt-in)

This queue consumer is **one-at-a-time**, not concurrent: one reviewed
experiment is claimed, executed and recorded per timer activation. The
optional timer checks again approximately a minute after the previous
invocation finishes (plus up to 15 seconds of jitter). For example,
300 fixed benign experiments take at least five hours of timer
intervals, in addition to guest runtime. No second daemon or worker
is required.

- The supported manifest cap is now **500** approved JSON files per
  release, with no more than 2000 retained private result entries for
  bounded indexing. A larger campaign requires reviewing these limits,
  storage and retention first.
- Deterministic filename ordering selects the next unclaimed item.
  A durable claim **precedes** VM execution. Failed or interrupted jobs
  are not retried automatically; the queue advances to the next item.
- An unchanged experiment ID **and identical manifest bytes** do not
  rerun merely because a later release was published. A new manifest
  ID or changed manifest digest counts as new reviewed work. Each
  result still contains the exact approved release SHA for audit.
  Changes to whitespace alone change the digest; keep manifest
  formatting stable and make intentional changes reviewable.
- **Automatic queue consumption does not bypass release approval.**
  Commit and PR alone are not executable; the operator publishes an
  approved release, and the existing VPS puller installs it.
- This is queue plumbing, **not arbitrary scenario execution**.
  The only current runner remains fixed arithmetic/SHA-256 with one
  diskless, networkless guest cycle. New scenario categories require
  separate allowlisted runner implementations and review.

After publishing and deploying the release containing this change,
inspect the service and timer, then deliberately opt in once:

```bash
sudo systemctl cat slipcage-experiment-consumer.service --no-pager
sudo systemctl cat slipcage-experiment-consumer.timer --no-pager
sudo systemctl enable --now slipcage-experiment-consumer.timer
sudo systemctl list-timers 'slipcage-experiment-consumer*' --no-pager
```

The timer will then process **one** outstanding approved manifest
each activation, or report `idle` if none remain. To pause instantly
between executions, disable the timer. To stop an already running
guest, stop the service too:

```bash
sudo systemctl disable --now slipcage-experiment-consumer.timer
# Optional emergency stop of active guest work:
sudo systemctl stop slipcage-experiment-consumer.service
```

Keep publication of sanitized results into GitHub as a **separate,
manual-only** operation. Do not add a GitHub token to the guest worker.
