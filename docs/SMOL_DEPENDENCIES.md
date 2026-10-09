# Smol dependency audit: keep benign guest execution working

This is a **static source audit**, not a package-removal or deployment
change. It documents the original v0.10 installer as retained in smol
after removing unused Restic and outbound webhook components.

## What the reviewed workloads actually invoke

| Package / executable | Evidence in tracked code | Proposed handling |
| --- | --- | --- |
| `qemu-system-x86` / `/usr/bin/qemu-system-x86_64` | `scripts/slipcage-kvm-probe.py` launches this binary for manual KVM preflight and fixed guest boot. Guest lifecycle also uses the same probe. | **Keep** for benign manual nested guests. Do not disable this package merely to shrink a source-build toolchain. |
| `busybox-static` | `scripts/build-microguest.sh` and `scripts/build-experiment-guest.sh` copy the distro BusyBox executable into inert initramfs images. | **Keep** to build both fixed guest images. |
| `cpio` and `gzip` | Both guest-build scripts package an inert `/init` into compressed `newc` archives; CI builds these images without booting them. | **Keep** the necessary tools for reproducible benign image building. |
| Running Ubuntu kernel | Ansible stages a kernel under `/usr/local/lib/slipcage`; the probe uses that staged path. | **Keep** reviewed staging; never broaden permissions on `/boot` just for QEMU. |
| `clang`, `gcc`, `g++`, `make`, `ninja-build`, `meson`, `pkg-config` | These are installed under the Ansible task `Install optional QEMU analysis and build tools`. The reviewed fixed guest-build scripts **do not call** them. | **Candidate for optional installation by default**, subject to a separate package/deployment PR and fresh-host test. |
| `libglib2.0-dev`, `libpixman-1-dev`, `gdb` | Development/debugging requirements from that same task; not used by the fixed known-answer guest shell code. | **Candidate for optional installation**, not a requirement of the manual benign guest workload identified above. |
| `qemu-utils` | Present in the analysis/build-tool task; no explicit use in the reviewed fixed guest builder or KVM probe. | Review separately; do not assume removal is harmless to every operator script or future authorized workflow. |

## Current installation switch

`group_vars/all.yml` declares `install_research_toolchain: true`.
The task controlled by that switch currently includes **both**
`qemu-system-x86` (needed for manual guests) and compiler/development
packages (not invoked by the reviewed inert guest builders).

**Do not simply set `install_research_toolchain: false`.** That would
skip QEMU itself and break manual KVM/guest tests on a fresh host
without independently installed QEMU.

## Next candidate PR, intentionally NOT included here

1. Split the package list into a required **benign guest runtime**
   containing the reviewed `qemu-system-x86` binary and guest-build
   requirements, versus an optional **source-build/debug toolchain**.
2. Default the *development* group off on a genuinely fresh smol host,
   but continue to install the benign guest runtime as a required
   package. No changes to QEMU invocation, guest inputs, network/disk
   isolation or cgroup caps.
3. Add tests verifying Ansible installs `qemu-system-x86`,
   `busybox-static` and `cpio` regardless of the development
   toolchain setting, and that the optional task excludes QEMU.
4. Validate Ubuntu 24.04 dependency resolution and an actual benign
   nested guest separately on an authorized disposable host. Existing
   host packages must not be automatically purged by Ansible.
5. Keep `/dev/kvm` access restricted to the manual unprivileged
   VM-probe account. Do not enable guest timers or general fuzzing.

**Do not carry out any deployment of smol from this audit.** The
existing original Slipcage VPS remains on its separate release
channel, and smol has no independent VPS validation.
