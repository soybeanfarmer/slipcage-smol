#!/usr/bin/env bash
set -euo pipefail
printf 'CPU architecture: '; uname -m
printf 'KVM device: '; if [[ -e /dev/kvm ]]; then ls -l /dev/kvm; else echo 'NOT PRESENT'; fi
printf 'Virtualization flags: '; if grep -Eq '\b(svm|vmx)\b' /proc/cpuinfo; then echo 'PRESENT'; else echo 'NOT EXPOSED'; fi
printf 'Reports backup timer: '; systemctl is-active slipcage-backup.timer || true
printf 'Health timer: '; systemctl is-active slipcage-health.timer || true
printf 'Dashboard listen: '; ss -lnt | grep ':8525' || true
printf 'Memory:'; free -h
printf 'Disk:'; df -h /srv/isolab
