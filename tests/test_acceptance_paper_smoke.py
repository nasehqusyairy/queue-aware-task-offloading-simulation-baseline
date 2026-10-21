import csv
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("RUN_PAPER_SMOKE") == "1", "set RUN_PAPER_SMOKE=1 for the 200-second simulator acceptance test")
class PaperSmokeAcceptanceTests(unittest.TestCase):
    def test_200_second_edge_dc_only_smoke_records_real_configuration_and_metrics(self):
        command = [
            str(ROOT / "run.sh"), "--profile", "paper-aligned-baseline",
            "--method", "trade-off", "--devices", "10", "--duration-seconds", "200",
            "--destination-config", "EDGE_DC_ONLY",
        ]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stdout[-5000:] + result.stderr[-5000:])
        match = re.search(r"RUN_DIR=(.+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        run = Path(match.group(1).strip())
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["devices"], 10)
        self.assertEqual(manifest["duration_seconds"], 200)
        self.assertEqual(manifest["destination_config"], "EDGE_DC_ONLY")
        self.assertEqual(manifest["actual_edge_device_count"], 10)
        self.assertEqual(manifest["edge_datacenter_count"], 4)
        self.assertEqual(manifest["orchestrator_types_observed"], ["CLOUD"])
        self.assertEqual(manifest["coverage_violation_count"], 0)
        self.assertEqual(manifest["ue_decision_source_count"], 10)
        self.assertEqual(manifest["destination_counts"].get("NONE", 0), 0)
        self.assertEqual(manifest["nearest_edc_mismatch_count"], 0)
        self.assertTrue((run / "metrics.json").exists())
        self.assertTrue(list((run / "raw").rglob("*.csv")))
        self.assertTrue((run / "raw/destinations.csv").exists())
        self.assertAlmostEqual(manifest["simulated_end_seconds"], 200.0)

        with (run / "raw/destinations.csv").open(newline="") as stream:
            decisions = [row for row in csv.DictReader(stream) if row["record_type"] == "DECISION"]
        self.assertGreater(len(decisions), 0)
        for row in decisions:
            self.assertIn(row["destination_type"], {"EDGE_DATACENTER", "NONE"})
            if row["destination_type"] != "NONE":
                self.assertEqual(row["orchestrator_type"], "CLOUD")


if __name__ == "__main__":
    unittest.main()
