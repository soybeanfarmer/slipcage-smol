# v0.9 fixed resource observation — design and rollout

## Purpose

Add a third fixed experiment family that measures bounded resource behavior
without introducing manifest-controlled resource parameters or a general
payload interface.

The runner name is `fixed_resource_observation_v1`.

## Fixed workload

The guest is built locally from distro `busybox-static` into
`resource-v1.cpio.gz`. Its init process performs exactly one fixed workload:

1. write 32 MiB of zero bytes into the disposable initramfs filesystem,
2. compute SHA-256 over those bytes,
3. require the fixed known answer
   `83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`,
4. emit fixed success markers, remove the temporary file, and power off.

There is no guest network, persistent disk, host share, downloaded image,
runtime script, URL, shell input, or manifest-selected workload size.

## Fixed host-side ceilings

The QEMU process remains one vCPU with 384 MiB guest RAM. The probe records
QEMU subprocess wall time, user CPU time, system CPU time, and peak RSS.
A pass requires all existing clean-shutdown/network/disk invariants plus:

- wall time <= 60 seconds,
- user CPU + system CPU <= 60 seconds,
- QEMU peak RSS <= 768 MiB,
- the fixed guest SHA-256 markers to match.

The service-level 1280-MiB MemoryMax, 100% CPUQuota, task cap, outer timeout,
PrivateNetwork sandbox, and /dev/kvm-only device access remain unchanged.
The manifest cannot weaken or select any of these values.

## Result boundary

A private successful result may carry only four numeric observations:
`wall_seconds`, `cpu_user_seconds`, `cpu_system_seconds`, and
`qemu_peak_rss_kib`. The manual publisher independently revalidates the
fixed ceilings and publishes only those bounded numbers with the existing
sanitized provenance fields. Raw console output, host paths, exception text,
host identity, and arbitrary fields remain excluded.

## Rollout

This implementation intentionally contains no EXP-0003 manifest. After CI and
review, publish the capability in a release first. Authorize EXP-0003 in a
separate manifest PR, keep the consumer timer disabled, run it once manually,
inspect private evidence, dry-run the publisher, and only then submit a draft
sanitized result PR.

Passing this experiment demonstrates only that one fixed guest workload
completed inside the declared resource ceilings on that run. It is not a
hypervisor isolation result, capacity benchmark, vulnerability finding, or
provider-wide performance claim.
