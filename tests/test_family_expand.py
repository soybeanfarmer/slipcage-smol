"""Offline tests for bounded experiment-family expansion."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "slipcage-family-expand.py"
spec = importlib.util.spec_from_file_location("family_expand", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)

BASE = {
    "schema_version": 1,
    "id": "FAM-0001",
    "status": "approved",
    "runner": "fixed_arithmetic_sha256_v1",
    "experiment_id_start": 1000,
    "cycles": [1, 2, 3],
    "repetitions": 2,
}


class FamilyExpandTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.families = self.root / "families"
        self.experiments = self.root / "experiments"
        self.families.mkdir()
        self.experiments.mkdir()
        self.uid = os.getuid()
        self.family = self.families / "FAM-0001.json"
        self.family.write_text(json.dumps(BASE))

    def run(self):
        return planner.expand(families=self.families, experiments=self.experiments,
                              owner=self.uid)

    def test_deterministic_bounded_expansion(self):
        result = self.run()
        self.assertEqual(result, {"status": "expanded", "families": 1, "experiments": 6})
        values = [json.loads(p.read_text()) for p in sorted(self.experiments.iterdir())]
        self.assertEqual([v["id"] for v in values],
                         [f"EXP-{i:04d}" for i in range(1000, 1006)])
        self.assertEqual([v["cycles"] for v in values], [1, 2, 3, 1, 2, 3])
        self.assertTrue(all(set(v) == {"schema_version", "id", "status", "runner", "cycles"}
                            for v in values))
        self.assertEqual(self.run()["experiments"], 6)

    def test_family_cannot_add_executable_or_network_fields(self):
        for field, value in (("command", "/bin/sh"), ("url", "https://example.invalid"),
                             ("image", "/tmp/guest.img"), ("network", True)):
            with self.subTest(field=field):
                self.family.write_text(json.dumps({**BASE, field: value}))
                with self.assertRaises(ValueError):
                    self.run()

    def test_runner_and_cycle_bounds_fail_closed(self):
        cases = [
            {**BASE, "runner": "arbitrary"},
            {**BASE, "cycles": [0]},
            {**BASE, "cycles": [4]},
            {**BASE, "cycles": [1, 1]},
            {**BASE, "cycles": [True]},
            {**BASE, "repetitions": 0},
            {**BASE, "repetitions": 101},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.family.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    self.run()

    def test_overlapping_families_and_manual_manifest_collisions_fail(self):
        other = {**BASE, "id": "FAM-0002", "experiment_id_start": 1005}
        (self.families / "FAM-0002.json").write_text(json.dumps(other))
        with self.assertRaises(ValueError):
            self.run()
        (self.families / "FAM-0002.json").unlink()
        (self.experiments / "EXP-1000.json").write_text("{}")
        with self.assertRaises(ValueError):
            self.run()

    def test_total_campaign_is_capped_at_500(self):
        # Three-cycle families of 100 repetitions each would total 600.
        second = {**BASE, "id": "FAM-0002", "experiment_id_start": 2000,
                  "repetitions": 100}
        first = {**BASE, "repetitions": 100}
        self.family.write_text(json.dumps(first))
        (self.families / "FAM-0002.json").write_text(json.dumps(second))
        with self.assertRaises(ValueError):
            self.run()


if __name__ == "__main__":
    unittest.main()
