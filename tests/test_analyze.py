import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze import parse


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


if __name__ == "__main__":
    unittest.main()
