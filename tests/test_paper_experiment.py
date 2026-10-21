import unittest
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from paper_experiment import allocate_profile_counts, coverage_summary, expected_task_count, initial_matrix, target_allowed_types, target_architecture


class PaperExperimentTests(unittest.TestCase):
    def test_largest_remainder_profile_allocation_hits_requested_device_count(self):
        expected = {
            10: [2, 1, 1, 3, 3],
            20: [4, 2, 2, 6, 6],
            30: [6, 3, 3, 8, 10],
        }
        for requested, counts in expected.items():
            with self.subTest(requested=requested):
                actual = allocate_profile_counts(requested, [18, 11, 11, 28, 32])
                self.assertEqual(actual, counts)
                self.assertEqual(sum(actual), requested)

    def test_initial_matrix_is_36_unique_combinations(self):
        matrix = initial_matrix()
        self.assertEqual(len(matrix), 36)
        self.assertEqual(len({(x["method"], x["devices"], x["destination_config"]) for x in matrix}), 36)

    def test_quadrant_coverage_covers_full_200_by_200_area_with_radius_71(self):
        points = [(0, 0), (100, 0), (0, 100), (200, 200)]
        centers = [(50, 50), (150, 50), (50, 150), (150, 150)]
        summary = coverage_summary(points, centers, 71, 200, 200)
        self.assertEqual(summary["coverage_violation_count"], 0)
        self.assertEqual(summary["area_violation_count"], 0)
        self.assertAlmostEqual(summary["max_nearest_distance"], 5000 ** 0.5)

    def test_task_rates_are_applied_per_second_to_each_assigned_user(self):
        expected = {10: 29000, 20: 58000, 30: 87000}
        for users, count in expected.items():
            with self.subTest(users=users):
                self.assertEqual(expected_task_count(users, [20, 30, 50], [20, 30, 3], 200), count)

    def test_paper_parameters_use_cloud_orchestrator_200s_and_wifi_spec(self):
        props = {}
        for line in (ROOT / "configs/paper-aligned/simulation_parameters.properties").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                props[key.strip()] = value.strip()
        self.assertEqual(float(props["simulation_time"]) * 60, 200)
        self.assertEqual(props["enable_orchestrators"], "true")
        self.assertEqual(props["deploy_orchestrator"], "CLOUD")
        self.assertEqual(props["wait_for_all_tasks"], "false")
        self.assertEqual(props["length"], "200")
        self.assertEqual(props["width"], "200")
        self.assertEqual(props["edge_datacenters_coverage"], "71")
        self.assertEqual(props["wifi_bandwidth"], "1300")
        self.assertEqual(props["wifi_latency"], "0.005")

    def test_paper_configuration_contains_five_profiles_three_apps_and_four_edcs(self):
        config = ROOT / "configs" / "paper-aligned"
        devices = ET.parse(config / "edge_devices.xml").getroot().findall("device")
        apps = ET.parse(config / "applications.xml").getroot().findall("application")
        edcs = ET.parse(config / "edge_datacenters.xml").getroot().findall("datacenter")
        self.assertEqual(len(devices), 5)
        self.assertEqual([int(d.findtext("percentage")) for d in devices], [18, 11, 11, 28, 32])
        self.assertEqual([d.findtext("generateTasks") for d in devices], ["true"] * 5)
        self.assertEqual(len(apps), 3)
        self.assertEqual([int(a.findtext("rate")) for a in apps], [20, 30, 3])
        self.assertEqual([int(a.findtext("usage_percentage")) for a in apps], [20, 30, 50])
        self.assertEqual(len(edcs), 4)
        self.assertEqual([(int(d.findtext("location/x_pos")), int(d.findtext("location/y_pos"))) for d in edcs],
                         [(50, 50), (150, 50), (50, 150), (150, 150)])

    def test_all_six_paper_targets_map_to_distinct_supported_layer_sets(self):
        expected = {
            "ALL_DEVICES": "ALL",
            "EDGE_AND_EDGE_DC": "MIST_AND_EDGE",
            "EDGE_AND_CLOUD": "MIST_AND_CLOUD",
            "EDGE_DC_AND_CLOUD": "EDGE_AND_CLOUD",
            "EDGE_ONLY": "MIST_ONLY",
            "EDGE_DC_ONLY": "EDGE_ONLY",
        }
        self.assertEqual({k: target_architecture(k) for k in expected}, expected)
        self.assertEqual(len(set(expected.values())), 6)
        allowed = {
            "ALL_DEVICES": {"CLOUD", "EDGE_DATACENTER", "EDGE_DEVICE"},
            "EDGE_AND_EDGE_DC": {"EDGE_DATACENTER", "EDGE_DEVICE"},
            "EDGE_AND_CLOUD": {"CLOUD", "EDGE_DEVICE"},
            "EDGE_DC_AND_CLOUD": {"CLOUD", "EDGE_DATACENTER"},
            "EDGE_ONLY": {"EDGE_DEVICE"},
            "EDGE_DC_ONLY": {"EDGE_DATACENTER"},
        }
        self.assertEqual({k: target_allowed_types(k) for k in allowed}, allowed)


if __name__ == "__main__":
    unittest.main()
