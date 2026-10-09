# Slipcage v0.4 — Research environment readiness

The original v0.4 release prepared **manual, benign nested-virtualization
testing** and formerly included a disabled, opt-in encrypted off-server
backup helper. **Slipcage-smol deliberately removed that unused helper.**
There is no off-server backup runner, systemd unit, or Restic dependency
in smol. This does **not** enable fuzzing, vulnerability reproduction,
scans, exploitation, or automated guest creation.

## Scope and provider authorization

The VPS provider advertises nested KVM, but /dev/kvm existing does NOT
prove nested guest execution. Confirm your plan/provider permits nested guests
and CPU-intensive testing before running more than the benign tests here.
Never attack or probe the hosting provider's hypervisor or other customers.
All new tests run only on **your rented guest VPS**.

No KVM test starts automatically during installation.

## Stage 1: Read-only capability inventory

After deployment, on the VPS run:

    /usr/bin/python3 /usr/local/lib/slipcage/kvm-probe.py

This shows /dev/kvm character device availability and whether the *calling
user* can open it. Running as slipadmin may show no access even when the
dedicated probe account has permission; that is expected. It is only an
inspection, not an actual VM test.

## Stage 2: Inert KVM initialization (manual)

    sudo systemctl start slipcage-kvm-probe.service
    sudo journalctl -u slipcage-kvm-probe.service -n 30 --no-pager

This launches QEMU as the new locked-down slipcage-vmprobe account. It
allocates 256 MiB guest RAM, one virtual CPU, no drives or network, and
starts the machine PAUSED. A QMP query must report both KVM present and
enabled. It terminates without executing a guest OS. A successful result
proves only KVM initialization, not boot/reliability.

It is isolated with PrivateNetwork=yes, device access restricted to
/dev/kvm, a strict read-only host filesystem, CPUQuota=100%, MemoryMax=768M,
TasksMax=64, and a short timeout.

## Stage 3: Disposable Linux microguest boot (manual)

Ubuntu's busybox-static package and the installed kernel are used to build
a tiny initramfs containing only a static shell and a minimal /init script.
The running kernel is staged by Ansible from the often root-restricted
/boot/vmlinuz-<kernel-version> into /usr/local/lib/slipcage/ as a root-owned,
mode 0644 copy. The unprivileged QEMU probe reads that copy, never the
original /boot file. The stage is refreshed by the next release deployment
after a host kernel upgrade; if the VPS boots a newer kernel before then,
rerun an approved deployment to populate its corresponding staged copy.
No third-party guest images are downloaded. The guest is ephemeral:
- 384 MiB RAM, one vCPU, and KVM-only (no TCG fallback)
- no virtual disks, network interface, host directory shares or host mounts
- a fixed kernel command line; emits SLIPCAGE_MICROGUEST_OK and powers off
- same unprivileged sandbox as stage 2, with 1280M host cgroup memory
  limit and a hard runtime cutoff (QEMU 75 sec / systemd oneshot start 95 sec)

Run **only after the provider's terms permit benign nested guests**:

    sudo systemctl start slipcage-kvm-boot.service
    sudo journalctl -u slipcage-kvm-boot.service -n 50 --no-pager

Success requires the marker **and** QEMU exit status zero. Kernel/guest
compatibility may prevent boot even when KVM itself works. No untrusted
code or exploit payloads are supplied by Slipcage. This is an initial
boot smoke test, not endurance/stress testing or proof of security isolation.

Both KVM units are manually started, with no timers, no DAG and no new
public service ports.

## Off-server backups — removed from smol

This historical v0.4 feature was **never enabled** for the smaller
project. Slipcage-smol no longer includes the optional encrypted
off-server backup runner, Restic package requirement, or dedicated
offsite service/timer. The commands from the old v0.4 setup guide to
start or enable an offsite service are **not applicable** to smol.

The verified daily **local** SQLite/report snapshots, the separate
non-destructive restore checker, and bounded weekly scratch restore
assurance remain installed. These same-VPS backups cannot recover from
loss of the entire server. Any future independently tested off-server
backup solution requires a new operator decision and review; no
credentials or remote storage are configured by this repo.

## Priorities before autonomous fuzzing

1. Confirm provider permission and pass manual nested guest boot checks.
2. Exercise repeated benign boot cycles and measure resource usage.
3. If ever approved separately, design off-server disaster recovery
   independently of the smol source repository; do not assume it exists.
4. Define a disposable KVM guest image policy and snapshot/revert strategy
   with no host resources mounted inside guest workloads.
5. Keep privileged host access, Docker socket access, and attack payloads
   excluded until isolation boundaries and authorization are reviewed.

A successful KVM test alone is not a license to test VM escapes against
the hosting provider.
