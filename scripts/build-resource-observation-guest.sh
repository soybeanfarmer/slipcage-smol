#!/usr/bin/env bash
# Construct a fixed, bounded resource-observation guest using distro busybox-static.
# No downloaded guest images, guest disk, networking, or arbitrary guest payloads.
set -Eeuo pipefail
umask 022
[[ "$EUID" == 0 ]] || { echo "Root needed to create the console device node" >&2; exit 1; }
busybox="$(command -v busybox)"
[[ -x "$busybox" ]] || { echo "busybox-static is required" >&2; exit 1; }
command -v cpio >/dev/null || { echo "cpio is required" >&2; exit 1; }

destination="/usr/local/lib/slipcage/resource-v1.cpio.gz"
work="$(mktemp -d)"
temporary=""
cleanup() {
  rm -rf -- "$work"
  if [[ -n "$temporary" ]]; then rm -f -- "$temporary"; fi
}
trap cleanup EXIT

mkdir -p "$work/root/bin" "$work/root/dev" "$work/root/tmp"
cp -- "$busybox" "$work/root/bin/busybox"
chmod 0755 "$work/root/bin/busybox"
ln -s busybox "$work/root/bin/sh"
mknod -m 0600 "$work/root/dev/console" c 5 1
cat > "$work/root/init" <<'GUEST_INIT'
#!/bin/sh
# Fixed 32-MiB zero-buffer touch + SHA-256 verification. No outside inputs.
set -eu
path=/tmp/slipcage-resource.bin
bytes=33554432
expected="83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302  $path"
/bin/busybox dd if=/dev/zero of="$path" bs=1048576 count=32 2>/dev/null
actual="$(/bin/busybox sha256sum "$path")"
if [ "$actual" != "$expected" ]; then
    echo SLIPCAGE_RESOURCE_V1_SHA256_FAIL > /dev/console
    exec /bin/busybox poweroff -f
fi
/bin/busybox rm -f "$path"
echo SLIPCAGE_RESOURCE_V1_BYTES=$bytes > /dev/console
echo SLIPCAGE_RESOURCE_V1_SHA256=83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302 > /dev/console
echo SLIPCAGE_RESOURCE_V1_OK > /dev/console
exec /bin/busybox poweroff -f
GUEST_INIT
chmod 0755 "$work/root/init"
temporary="$(mktemp /usr/local/lib/slipcage/.resource-v1.XXXXXXXX)"
(
  cd "$work/root"
  find . -print0 | LC_ALL=C sort -z | cpio --null -o --format=newc --quiet | gzip -n > "$temporary"
)
chmod 0644 "$temporary"
mv -f -- "$temporary" "$destination"
temporary=""
echo "Built fixed 32-MiB resource-observation guest (no network or disks)"
