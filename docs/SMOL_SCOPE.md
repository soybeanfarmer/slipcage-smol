# Slipcage-smol: project scope and working rules

**Status: a source-only fork of the reviewed Slipcage v0.10.0 snapshot.**
Origin tag: [soybeanfarmer/slipcage v0.10.0](https://github.com/soybeanfarmer/slipcage/releases/tag/v0.10.0),
commit `f356d83b8cea2500c131da78eea6325f97067065`.
Smol baseline: `628b7f4290ddb1af271c49a2041a040d578a1e62`.
The two commits have the **same Git tree**, but different Git histories.

## The small vision

One operator, one isolated VPS, one local SQLite-backed workspace.
Slipcage is a **metadata-first research notebook** for selecting and
documenting public QEMU/KVM and container-runtime security advisories.
It can also run explicitly approved, fixed, benign, disposable Linux
microguest checks as *manual* experiments. Evidence must remain
reproducible and distinguish assumptions from observations.

A successful smol iteration should make it easier to understand:
1. What advisory was found, what metadata supports its priority, and
   where the associated Markdown review can be inspected.
2. Whether a fixed disposable guest check completed correctly without
   using dynamic inputs, networking, drives or fuzzing.
3. Whether the local research state is healthy and recent backup copies
   can actually be read and restored to *temporary local scratch space*.
4. How to recover conservatively when a step fails.

**We are maintaining an operator-focused research tool, not building a
hosted product.** No marketing site, billing, subscription system,
organization accounts, multi-tenant API, hosted user portal or
onboarding SaaS. No automated exploit reproduction, offensive scanning,
malicious payloads or shared-host testing.

## Safety invariants (must survive simplification)

- Public advisory metadata and URLs are **data, never executable
  instructions**. Candidate reviews generate metadata-only reports.
- The Dagu dashboard binds to loopback, is authenticated, and runs as a
  separate non-root user. Scheduled research uses the deployment
  maintenance/lock gate. A queue timeout is not evidence of an escape.
- Nested KVM experiments are **manual-only**, fixed benign
  arithmetic/hash or boot probes in unprivileged, diskless,
  networkless guests with bounded time/CPU/RAM/task quotas.
  No fuzzers, untrusted guest payloads or device attacks.
- **No autonomous writes to production research data** outside the
  reviewed metadata workflow. No automatic destructive restore,
  deleting incomplete guest evidence, or wiping local backups.
- Daily root-private local backups stay intact. Weekly scratch restore
  assurance and hourly local health checks may run automatically;
  both are bounded and do not alter research DBs or existing backups.
- HTTPS notification delivery is **disabled by default** and requires
  an operator-selected compatible endpoint. Encrypted off-server
  backup setup remains deferred: disabled units are not approval to
  enable them.
- No unapproved release or deployment. The original production VPS
  belongs to the original Slipcage deployment until the operator
  explicitly chooses and reviews an independent smol migration.
- Preserve offline Python tests, Ansible/shell/YAML syntax checks,
  pinned dependencies, and a human PR review/release gate. If a
  simplification loosens a boundary, it needs a separate security
  review rather than a silent "cleanup" commit.

## Change policy

1. Prefer a **small, testable behavior-preserving change** over broad
   rewrites, dependency swaps or new abstraction layers.
2. Each PR documents retained functionality, removed surface area,
   fallback/rollback and exact tests.
3. **Do not delete an installed service/unit, a database schema field,
   or a report/backup format solely because it looks unused.** First
   establish deployment consumers, migration impact, and preservation
   of existing state.
4. Nothing in this repository should be applied to the already-running
   VPS without a separately approved migration/release plan.

## Independent smol release channel and still-forbidden migration

The smol pull deployer now targets only
`soybeanfarmer/slipcage-smol` and verifies a private, root-owned
smol ownership marker **before GitHub polling**. Bootstrap refuses
an existing Slipcage installation, including research data and
deployment state. Ansible also requires the smol marker before
installing services. The original VPS has **not** been enrolled or
changed, and the existing application service/data paths remain
shared-name paths: no same-host co-installation or in-place
migration is supported.

See [Independent smol deployment](SMOL_DEPLOYMENT.md). Use a
**separate fresh host** only after approval. Do not run smol
bootstrap, Ansible or release promotion to take over the original VPS.

Original software source has been preserved unchanged on this first
documentation/audit PR. Existing historical guides remain under
`docs/`; they describe individual milestone implementations and
are not the canonical current-state overview.
