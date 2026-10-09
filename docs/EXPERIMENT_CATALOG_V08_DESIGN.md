# v0.8 experiment catalog — design for review

Status: **accepted design; implementation remains review-gated**. This document does not authorize deployment or unattended execution.

## Existing trusted components (v0.7.0)

- `slipcage-experiment-consumer.py` processes one approved manifest per invocation, with a durable claim before launch and no automatic retry.
- `slipcage-guest-lifecycle.py` already supports two hardcoded profiles: `experiment` (fixed arithmetic/SHA-256) and `boot` (diskless guest boot/shutdown).
- `slipcage-kvm-probe.py` implements both fixed guest probes; neither accepts arbitrary guest commands, disk images or network configuration.
- The results publisher currently allows only the existing fixed experiment runner. Its allowlist and tests must be updated *before* any new runner is released for execution.

## First increment: fixed guest lifecycle runner

Add a second manifest runner `fixed_guest_boot_v1`, using the existing lifecycle's `boot` profile. Do not add arbitrary `profile`, `command`, `args`, `kernel`, `initrd`, `network`, `disk`, `memory`, `cpu` or `timeout` manifest fields.

Suggested schema for the first increment retains schema version 1 and the exact five existing keys:

```json
{
  "schema_version": 1,
  "id": "EXP-0002",
  "status": "approved",
  "runner": "fixed_guest_boot_v1",
  "cycles": 1
}
```

The consumer must map the **exact** runner name to a hardcoded `run_lifecycle(1, profile="boot")` invocation. The existing arithmetic runner maps to `run_lifecycle(1, profile="experiment")`. There must be no manifest-controlled function name or executable path. Keep the legacy manifest unchanged.

## Evidence and pass criteria

The arithmetic runner retains its strict known-answer verification. The boot runner must require the lifecycle summary mode `benign_diskless_guest_lifecycle`, exactly one requested/completed/successful cycle, `passed is True`, per-cycle `passed is True`, `network == "disabled"`, and `persistent_guest_disk is False`. A successful boot is **not** a vulnerability finding and does not imply arithmetic/hash verification. Distinguish runner-specific outcomes in private and sanitized results; do not pretend boot evidence has known-answer markers.

Before release, update the publisher's runner/outcome allowlists, tests, and documentation. Keep the publisher manual-only; no GitHub write credential belongs in the consumer service. Review public result fields to avoid leaking raw logs, host paths, or internal identifiers.

## Required offline tests

1. Legacy `EXP-0001` still passes and preserves its manifest digest/claim identity.
2. A mixed queue runs the two fixed runners in ID order with no duplicate or overlapping guest work.
3. An approved boot manifest invokes only the hardcoded boot profile, exactly once.
4. Wrong runner, unknown fields, extra arguments, malformed types and cycles other than 1 fail closed before guest launch.
5. Forged success summaries, wrong mode, nonzero exit, enabled networking, persistent disks, missing cycles, and incomplete claims never count as a pass.
6. Failed/interrupted boot experiments are never automatically retried, including across releases.
7. Sanitized publisher accepts the new **allowlisted** boot result but rejects arbitrary runner/outcome values; private paths and raw logs never appear in PR content.
8. Existing 300-manifest sequential test continues to pass; add mixed-runner coverage.

## Later increments, not part of the first change

Parameterized compute, memory boundaries and device enumeration need separate reviewed guest implementations, fixed allowlists, explicit resource ceilings and evidence schemas. Avoid generating hundreds of nominally distinct manifests that merely repeat the same fixed workload. Generate batches only after the new runners provide meaningfully different measurements and the approval/release workflow is exercised end-to-end.

## Rollout gate

Keep the consumer timer disabled by default for new installations. Require successful offline CI, review, a manually published approved release, deployment verification, one supervised boot experiment, and explicit operator approval before unattended queue consumption. No VPS changes are included in this design PR.
