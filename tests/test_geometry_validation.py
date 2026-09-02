import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import geometry_validation


class GeometryValidationTests(unittest.TestCase):
    def setUp(self):
        self.step_path = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-S01.step"

    def test_inspect_step_reports_required_solid_metrics(self):
        result = geometry_validation.inspect_step(self.step_path)
        self.assertEqual(result["solid_count"], 1)
        self.assertTrue(result["is_valid"])
        self.assertAlmostEqual(result["volume_mm3"], 48000.0, places=5)
        self.assertAlmostEqual(result["surface_area_mm2"], 8800.0, places=5)
        self.assertEqual(
            result["bbox_mm"],
            {"xmin": 0.0, "xmax": 60.0, "ymin": 0.0, "ymax": 40.0, "zmin": 0.0, "zmax": 20.0},
        )

    def test_face_budget_keeps_minimum_and_exact_total(self):
        counts = geometry_validation.allocate_face_samples([1.0, 3.0, 6.0], total_budget=4096, minimum_per_face=32)
        self.assertEqual(sum(counts), 4096)
        self.assertTrue(all(count >= 32 for count in counts))
        self.assertGreater(counts[2], counts[1])
        self.assertGreater(counts[1], counts[0])

    def test_sampling_is_deterministic_from_file_sha256(self):
        first = geometry_validation.sample_step_surface(self.step_path, total_budget=4096)
        second = geometry_validation.sample_step_surface(self.step_path, total_budget=4096)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["seed"], second["seed"])
        self.assertEqual(first["points"].shape, (4096, 3))
        self.assertTrue((first["points"] == second["points"]).all())
        self.assertEqual(first["face_slices"], second["face_slices"])
        self.assertAlmostEqual(sum(first["face_areas_mm2"]), 8800.0, places=5)

    def test_bidirectional_comparison_reports_required_distances(self):
        result = geometry_validation.compare_step_files(self.step_path, self.step_path, total_budget=4096)
        distance = result["surface_distance_mm"]
        self.assertEqual(result["sampling"]["global_mean_weighting"], "source_face_area")
        for key in (
            "a_to_b_mean_mm",
            "a_to_b_p95_mm",
            "b_to_a_mean_mm",
            "b_to_a_p95_mm",
            "symmetric_mean_mm",
            "symmetric_p95_mm",
            "max_face_p95_mm",
        ):
            self.assertIn(key, distance)
            self.assertAlmostEqual(distance[key], 0.0, places=12)

    def test_roundtrip_baseline_is_repeatable_without_acceptance_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "roundtrip.step"
            geometry_validation.roundtrip_step(self.step_path, output)
            first = geometry_validation.compare_step_files(self.step_path, output, total_budget=4096)
            second = geometry_validation.compare_step_files(self.step_path, output, total_budget=4096)
        self.assertEqual(first["surface_distance_mm"], second["surface_distance_mm"])
        self.assertNotIn("accepted", first)
        self.assertNotIn("threshold_mm", json.dumps(first))

    def test_calibration_report_contains_self_and_roundtrip_repeatability(self):
        with tempfile.TemporaryDirectory() as directory:
            roundtrip = Path(directory) / "roundtrip.step"
            report = geometry_validation.calibrate_baseline(
                self.step_path,
                roundtrip,
                total_budget=4096,
            )
        self.assertTrue(report["repeatability"]["same_file_exact"])
        self.assertTrue(report["repeatability"]["roundtrip_exact"])
        self.assertEqual(report["same_file"]["surface_distance_mm"]["symmetric_p95_mm"], 0.0)
        self.assertNotIn('"acceptance_threshold":', json.dumps(report))


if __name__ == "__main__":
    unittest.main()
