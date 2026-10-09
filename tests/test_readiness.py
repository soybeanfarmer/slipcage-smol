"""Offline tests: KVM capability checks and disposable benign boot design."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "slipcage-kvm-probe.py"
spec = importlib.util.spec_from_file_location("slipcage_kvm_probe", MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def available():
    return {"process_can_open_kvm": True, "qemu_binary_available": True}


class ReadinessTests(unittest.TestCase):
    def test_qmp_requires_explicit_true_status_not_merely_greeting(self):
        ok = '{"QMP":{"version":{}}}\n' + (
            '{"return":{},"id":"enable"}\n'
            '{"return":{"enabled":true,"present":true},"id":"inspect-kvm"}\n'
            '{"return":{},"id":"exit"}\n'
        )
        self.assertTrue(probe.parse_kvm_status(ok))
        for text in [
            '{"QMP":{"version":{}}}', "",
            '{"return":{"present":true,"enabled":false},"id":"inspect-kvm"}',
            '{"return":{"present":true,"enabled":"true"},"id":"inspect-kvm"}',
            '{"error":{"class":"GenericError"},"id":"inspect-kvm"}',
        ]:
            self.assertFalse(probe.parse_kvm_status(text))

    def test_qmp_probe_has_no_disk_network_or_guest_execution(self):
        with patch.object(probe, "inspect", return_value=available()):
            def runner(cmd, **kwargs):
                self.assertIn("q35,accel=kvm", cmd)
                self.assertIn("-nic", cmd)
                self.assertEqual(cmd[cmd.index("-nic") + 1], "none")
                self.assertIn("-S", cmd)
                self.assertNotIn("-drive", cmd)
                self.assertNotIn("-kernel", cmd)
                self.assertEqual(kwargs["timeout"], 15)
                self.assertIn('"execute":"query-kvm"', kwargs["input"])
                return Mock(returncode=0, stdout=(
                    '{"return":{},"id":"enable"}\n'
                    '{"return":{"present":true,"enabled":true},"id":"inspect-kvm"}\n'
                    '{"return":{},"id":"exit"}\n'), stderr="")
            self.assertTrue(probe.smoke(runner=runner)["kvm_initialized"])

    def test_qmp_fails_closed_without_open_kvm(self):
        with patch.object(probe, "inspect", return_value={
            "process_can_open_kvm": False, "qemu_binary_available": True
        }):
            self.assertFalse(probe.smoke(runner=lambda *_a, **_k: self.fail())["kvm_initialized"])

    def test_guest_boot_is_diskless_networkless_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            kernel = Path(d) / "vmlinuz"
            initrd = Path(d) / "microguest.cpio.gz"
            kernel.write_bytes(b"dummy test kernel")
            initrd.write_bytes(b"dummy test initramfs")
            def runner(cmd, **kwargs):
                self.assertIn("q35,accel=kvm", cmd)
                self.assertIn("-nic", cmd)
                self.assertEqual(cmd[cmd.index("-nic") + 1], "none")
                for forbidden in ["-drive", "-hda", "-hdb", "-cdrom", "-virtfs", "-netdev"]:
                    self.assertNotIn(forbidden, cmd)
                self.assertIn("-kernel", cmd)
                self.assertIn("-initrd", cmd)
                self.assertEqual(kwargs["timeout"], 75)
                return Mock(returncode=0,
                            stdout="boot\nSLIPCAGE_MICROGUEST_OK\npoweroff\n", stderr="")
            with patch.object(probe, "inspect", return_value=available()):
                result = probe.boot_guest(runner=runner, kernel_path=kernel,
                                          initrd_path=initrd)
            self.assertTrue(result["guest_booted"])
            self.assertFalse(result["persistent_guest_disk"])
            self.assertEqual(result["network"], "disabled")

    def test_guest_requires_marker_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as d:
            kernel, initrd = Path(d) / "kernel", Path(d) / "initramfs"
            kernel.touch()
            initrd.touch()
            with patch.object(probe, "inspect", return_value=available()):
                for code, output in [(0, "ordinary boot"), (1, probe.BOOT_MARKER)]:
                    result = probe.boot_guest(runner=lambda *_args, **_kwargs:
                        Mock(returncode=code, stdout=output, stderr=""),
                        kernel_path=kernel, initrd_path=initrd)
                    self.assertFalse(result["guest_booted"])

    def test_kernel_is_staged_readable_without_chmodding_boot(self):
        playbook = (ROOT / "playbooks" / "site.yml").read_text()
        probe_script = (ROOT / "scripts" / "slipcage-kvm-probe.py").read_text()
        self.assertIn('src: "/boot/vmlinuz-{{ ansible_facts[\'kernel\'] }}"', playbook)
        self.assertIn('dest: "/usr/local/lib/slipcage/vmlinuz-{{ ansible_facts[\'kernel\'] }}"', playbook)
        kernel_task = playbook.split(
            "- name: Stage running Ubuntu kernel for unprivileged microguest boot")[1].split(
            "- name: Install KVM readiness probe")[0]
        self.assertIn("remote_src: true", kernel_task)
        self.assertIn("owner: root", kernel_task)
        self.assertIn("mode: '0644'", kernel_task)
        self.assertIn('Path("/usr/local/lib/slipcage") / f"vmlinuz-{os.uname().release}"',
                      probe_script)
        self.assertNotIn('kernel = Path("/boot")', probe_script)
        for name in ("slipcage-kvm-probe.service", "slipcage-kvm-boot.service"):
            unit = (ROOT / "systemd" / name).read_text()
            self.assertNotIn("RuntimeMaxSec=", unit)
            self.assertIn("TimeoutStartSec=", unit)
            self.assertIn("User=slipcage-vmprobe", unit)

    def test_systemd_probe_units_are_manual_and_resource_bounded(self):
        for name in ("slipcage-kvm-probe.service", "slipcage-kvm-boot.service"):
            text = (ROOT / "systemd" / name).read_text()
            self.assertIn("User=slipcage-vmprobe", text)
            self.assertIn("SupplementaryGroups=kvm", text)
            self.assertIn("PrivateNetwork=yes", text)
            self.assertIn("DeviceAllow=/dev/kvm rw", text)
            self.assertIn("MemoryMax=", text)
            self.assertIn("CPUQuota=100%", text)
            self.assertIn("TimeoutStartSec=", text)
            self.assertNotIn("WantedBy=", text)
        self.assertEqual(
            (ROOT / "systemd" / "slipcage-kvm-boot.service").read_text().count(
                "ExecStart="), 1)

    def test_removed_offsite_integration_is_not_installed(self):
        """Restic must not be installed by fresh-smol Ansible deployments."""
        playbook = (ROOT / "playbooks" / "site.yml").read_text()
        self.assertNotIn("slipcage-offsite-backup", playbook)
        self.assertNotIn("          - restic", playbook)
        self.assertFalse((ROOT / "scripts" / "slipcage-offsite-backup.sh").exists())
        for name in ("slipcage-offsite-backup.service",
                     "slipcage-offsite-backup.timer"):
            self.assertFalse((ROOT / "systemd" / name).exists())

        # The private config directory MUST stay: the fresh-host smol
        # release-channel marker lives inside /etc/slipcage.
        self.assertIn("path: /etc/slipcage", playbook)
        self.assertIn("Protect private smol release-channel", playbook)

    def test_local_backup_and_weekly_restore_assurance_stay_enabled(self):
        playbook = (ROOT / "playbooks" / "site.yml").read_text()
        for name in ("slipcage-backup.py", "slipcage-restore-check.py",
                     "slipcage-assurance.py", "slipcage-assurance.timer",
                     "slipcage-backup.timer"):
            self.assertIn(name, playbook)
        self.assertIn("Enable scheduled Slipcage backups", playbook)
        self.assertIn("Enable bounded weekly local backup assurance", playbook)

    def test_microguest_init_has_no_external_payload(self):
        source = (ROOT / "scripts" / "build-microguest.sh").read_text()
        self.assertIn("SLIPCAGE_MICROGUEST_OK", source)
        self.assertIn("poweroff -f", source)
        self.assertNotIn("curl ", source)
        self.assertNotIn("wget ", source)


if __name__ == "__main__":
    unittest.main()
