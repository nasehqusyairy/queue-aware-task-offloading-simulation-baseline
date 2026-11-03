import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze import parse, _row_for_run


HEADER = [
    "Number of generated tasks",
    "Tasks successfully executed",
    "Total tasks executed (Cloud)",
    "Tasks successfully executed (Cloud)",
    "Total tasks executed (Edge)",
    "Tasks successfully executed (Edge)",
    "Total tasks executed (Mist)",
    "Tasks successfully executed (Mist)",
    "Energy consumption of computing nodes (Wh)",
    "Tasks sent", "Tasks completed", "Tasks terminally failed", "Tasks pending at cutoff",
    "Cloud pending at cutoff", "Edge pending at cutoff", "Mist pending at cutoff",
    "Tasks rejected before pipeline",
]


class AnalyzeTests(unittest.TestCase):
    def write_run(self, values):
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name)
        raw = run / "raw"
        raw.mkdir()
        with (raw / "sim.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADER)
            writer.writeheader()
            writer.writerow(values)
        self.addCleanup(tmp.cleanup)
        return run

    def test_workload_uses_all_tasks_dispatched_by_layer_not_only_successes(self):
        run = self.write_run({
            "Number of generated tasks": "100",
            "Tasks successfully executed": "70",
            "Total tasks executed (Cloud)": "20",
            "Tasks successfully executed (Cloud)": "10",
            "Total tasks executed (Edge)": "50",
            "Tasks successfully executed (Edge)": "40",
            "Total tasks executed (Mist)": "30",
            "Tasks successfully executed (Mist)": "20",
            "Energy consumption of computing nodes (Wh)": "0",
        })
        metrics = parse(run)
        self.assertEqual(metrics["workload_distribution"], {"Cloud": 20, "Edge": 50, "Mist": 30})
        self.assertEqual(metrics["energy_consumption"], 0.0)

    def test_row_preserves_manifest_validation_errors_separately_from_metric_errors(self):
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name)
        (run / "raw").mkdir()
        (run / "manifest.json").write_text(json.dumps({
            "run_id": "failed-run",
            "status": "failed",
            "validation_errors": ["unexpected orchestrator types: ['EDGE_DEVICE']"],
        }))
        self.addCleanup(tmp.cleanup)

        row = _row_for_run(run)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["validation_errors"], ["unexpected orchestrator types: ['EDGE_DEVICE']"])
        self.assertIn("no simulator CSV with required task-count columns", row["metric_validation_errors"])

    def test_missing_layer_count_remains_unavailable_not_zero(self):
        run = self.write_run({
            "Number of generated tasks": "10",
            "Tasks successfully executed": "8",
            "Total tasks executed (Cloud)": "",
            "Tasks successfully executed (Cloud)": "",
            "Total tasks executed (Edge)": "8",
            "Tasks successfully executed (Edge)": "8",
            "Total tasks executed (Mist)": "",
            "Tasks successfully executed (Mist)": "",
            "Energy consumption of computing nodes (Wh)": "",
        })
        metrics = parse(run)
        self.assertEqual(metrics["workload_distribution"], {"Cloud": None, "Edge": 8, "Mist": None})
        self.assertIsNone(metrics["energy_consumption"])

    def test_pending_is_separate_and_closed_accounting_reconciles(self):
        run = self.write_run({
            "Number of generated tasks": "100", "Tasks successfully executed": "60",
            "Tasks sent": "100", "Tasks completed": "60", "Tasks terminally failed": "25",
            "Tasks pending at cutoff": "15", "Cloud pending at cutoff": "0",
            "Edge pending at cutoff": "15", "Mist pending at cutoff": "0",
            "Tasks rejected before pipeline": "0",
            "Total tasks executed (Cloud)": "0", "Tasks successfully executed (Cloud)": "0",
            "Total tasks executed (Edge)": "100", "Tasks successfully executed (Edge)": "60",
            "Total tasks executed (Mist)": "0", "Tasks successfully executed (Mist)": "0",
            "Energy consumption of computing nodes (Wh)": "",
        })
        metrics = parse(run)
        self.assertEqual((metrics["generated_tasks"], metrics["sent_tasks"], metrics["completed_tasks"],
                          metrics["terminally_failed_tasks"], metrics["pending_tasks"]), (100, 100, 60, 25, 15))
        self.assertEqual(metrics["task_success_rate"], 0.6)
        self.assertEqual(metrics["task_failure_rate"], 0.25)
        self.assertEqual(metrics["task_pending_rate"], 0.15)
        self.assertEqual(metrics["validation_errors"], [])

    def test_previous_pending_layer_discrepancy_is_rejected(self):
        run = self.write_run({
            "Number of generated tasks": "29000", "Tasks successfully executed": "2985",
            "Tasks sent": "29000", "Tasks completed": "2985", "Tasks terminally failed": "25957",
            "Tasks pending at cutoff": "58", "Cloud pending at cutoff": "0",
            "Edge pending at cutoff": "58", "Mist pending at cutoff": "0",
            "Tasks rejected before pipeline": "0",
            "Total tasks executed (Cloud)": "0", "Tasks successfully executed (Cloud)": "0",
            "Total tasks executed (Edge)": "29000", "Tasks successfully executed (Edge)": "3043",
            "Total tasks executed (Mist)": "0", "Tasks successfully executed (Mist)": "0",
            "Energy consumption of computing nodes (Wh)": "",
        })
        metrics = parse(run)
        self.assertTrue(any("do not reconcile" in error for error in metrics["validation_errors"]))
        self.assertEqual(metrics["pending_tasks"], 58)

    def test_zero_generated_tasks_has_unavailable_rates(self):
        run = self.write_run({
            "Number of generated tasks": "0", "Tasks successfully executed": "0",
            "Tasks sent": "0", "Tasks completed": "0", "Tasks terminally failed": "0",
            "Tasks pending at cutoff": "0", "Cloud pending at cutoff": "0",
            "Edge pending at cutoff": "0", "Mist pending at cutoff": "0",
            "Tasks rejected before pipeline": "0",
            "Total tasks executed (Cloud)": "0", "Tasks successfully executed (Cloud)": "0",
            "Total tasks executed (Edge)": "0", "Tasks successfully executed (Edge)": "0",
            "Total tasks executed (Mist)": "0", "Tasks successfully executed (Mist)": "0",
            "Energy consumption of computing nodes (Wh)": "",
        })
        metrics = parse(run)
        self.assertIsNone(metrics["task_success_rate"])
        self.assertIsNone(metrics["task_failure_rate"])
        self.assertIsNone(metrics["task_pending_rate"])
        self.assertEqual(metrics["validation_errors"], [])

    def test_missing_lifecycle_columns_are_reported_and_not_zero_filled(self):
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name)
        raw = run / "raw"
        raw.mkdir()
        with (raw / "sim.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["Number of generated tasks", "Tasks successfully executed"])
            writer.writeheader()
            writer.writerow({"Number of generated tasks": "12", "Tasks successfully executed": "9"})
        self.addCleanup(tmp.cleanup)
        metrics = parse(run)
        self.assertTrue(any("missing required simulator columns" in error for error in metrics["validation_errors"]))
        self.assertIsNone(metrics["pending_tasks"])
        self.assertIsNone(metrics["terminally_failed_tasks"])

    def test_invalid_numeric_values_are_reported(self):
        run = self.write_run({
            "Number of generated tasks": "not-a-number", "Tasks successfully executed": "0",
        })
        metrics = parse(run)
        self.assertTrue(any("invalid simulator CSV value" in error or "missing/empty" in error
                            for error in metrics["validation_errors"]))


if __name__ == "__main__":
    unittest.main()
