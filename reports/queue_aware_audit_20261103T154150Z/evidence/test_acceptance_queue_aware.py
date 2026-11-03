import csv
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("RUN_QUEUE_AWARE_SMOKE") == "1",
                     "set RUN_QUEUE_AWARE_SMOKE=1 for the paired Trade-Off/Round-Robin/Queue-Aware acceptance run")
class QueueAwareAcceptanceTests(unittest.TestCase):
    def test_three_methods_share_seed_and_keep_accounting_and_queue_audit(self):
        result = subprocess.run([
            str(ROOT / "run.sh"), "--profile", "paper-aligned-baseline", "--method", "all",
            "--devices", "10", "--duration-seconds", "200", "--destination-config", "EDGE_DC_ONLY",
            "--seed", "8128", "--queue-weight", "1.0",
        ], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stdout[-6000:] + result.stderr[-6000:])
        # The runner prints the same path in its status line and JSON summary.
        run_dirs = list(dict.fromkeys(re.findall(r"RUN_DIR=(.+)", result.stdout)))
        self.assertEqual(len(run_dirs), 3, result.stdout)

        manifests = {}
        source_traces = {}
        for raw_path in run_dirs:
            run = Path(raw_path.strip())
            manifest = json.loads((run / "manifest.json").read_text())
            method = manifest["method"]
            manifests[method] = manifest
            self.assertEqual(manifest["status"], "completed", manifest.get("validation_errors"))
            self.assertEqual(manifest["random_seed"], 8128)
            self.assertEqual(manifest["duration_seconds"], 200)
            self.assertEqual(manifest["destination_config"], "EDGE_DC_ONLY")
            self.assertEqual(manifest["metrics"]["validation_errors"], [])
            accounting = manifest["task_accounting"]
            self.assertEqual(accounting["generated_tasks"], accounting["completed_tasks"]
                             + accounting["terminally_failed_tasks"] + accounting["pending_tasks"])
            self.assertEqual(sum(accounting["layer_successful_completions"].values()),
                             accounting["completed_tasks"])
            with (run / "raw" / "destinations.csv").open(newline="") as stream:
                source_traces[method] = [
                    (row["task_id"], row["source_id"], row["source_x"], row["source_y"])
                    for row in csv.DictReader(stream) if row.get("record_type") == "DECISION"
                ]

        self.assertEqual(set(manifests), {"trade-off", "round-robin", "queue-aware"})
        self.assertEqual(source_traces["trade-off"], source_traces["round-robin"])
        self.assertEqual(source_traces["trade-off"], source_traces["queue-aware"])
        queue_manifest = manifests["queue-aware"]
        queue_metrics = queue_manifest["metrics"]["queue_aware_metrics"]
        self.assertTrue(queue_metrics["valid"])
        self.assertGreater(queue_metrics["candidate_observations"], 0)
        queue_run = next(Path(path.strip()) for path in run_dirs
                         if json.loads((Path(path.strip()) / "manifest.json").read_text())["method"] == "queue-aware")
        self.assertTrue((queue_run / "raw" / "queue_decisions.csv").is_file())
        self.assertTrue((queue_run / "metrics.json").is_file())


if __name__ == "__main__":
    unittest.main()
