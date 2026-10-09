"""Static architecture tests for a Dagu-free development deployment."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class NativeSystemdTests(unittest.TestCase):
    def test_no_dagu_install_or_schedule(self):
        site = (ROOT / "playbooks/site.yml").read_text()
        self.assertNotIn("get_url:", site)
        self.assertNotIn('src: "{{ playbook_dir }}/../workflows/', site)
        self.assertNotIn("dest: /var/lib/dagu/dags/", site)
        self.assertIn("Stop legacy Dagu before enabling native timers", site)
        self.assertIn("Install native discovery and review service/timer units", site)
        self.assertIn("Enable native discovery and review schedules", site)
        self.assertNotIn("name: isolab-dagu.service\n        daemon_reload: true\n        enabled: true", site)
        self.assertIn("/usr/local/bin/dagu", site)  # removal target

    def test_guarded_bounded_native_services(self):
        for name in ("slipcage-discover", "slipcage-review"):
            service = (ROOT / "systemd" / (name + ".service")).read_text()
            self.assertIn("User=isolab", service)
            self.assertIn("slipcage-guard run", service)
            self.assertIn("ProtectSystem=strict", service)
            self.assertIn("ReadWritePaths=/srv/isolab", service)
            self.assertIn("TimeoutStartSec=", service)
            self.assertIn("MemoryMax=", service)
            self.assertNotIn("/usr/local/bin/dagu", service)
            timer = (ROOT / "systemd" / (name + ".timer")).read_text()
            self.assertIn("Unit=" + name + ".service", timer)
            self.assertIn("WantedBy=timers.target", timer)
        self.assertIn("PrivateNetwork=true", (ROOT / "systemd/slipcage-review.service").read_text())

    def test_discovery_does_not_enqueue_on_dagu(self):
        source = (ROOT / "scripts/discover.sh").read_text()
        self.assertIn("isolab.py sync", source)
        self.assertIn("isolab.py analyze", source)
        self.assertNotIn("dagu", source)
        self.assertNotIn("enqueue", source)
        health = (ROOT / "scripts/slipcage-health.py").read_text()
        self.assertIn("slipcage-discover.timer", health)
        self.assertIn("slipcage-review.timer", health)
        self.assertNotIn("isolab-dagu.service", health)

if __name__ == "__main__":
    unittest.main()
