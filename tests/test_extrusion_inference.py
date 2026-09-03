import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import extrusion_inference


class ExtrusionInferenceTests(unittest.TestCase):
    def step(self, case_id):
        return PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"

    def infer(self, case_id):
        return extrusion_inference.infer_extrusions(self.step(case_id), case_id)

    def test_box_retains_three_accepted_histories_without_reverse_duplicates(self):
        result = self.infer("D-S01")
        self.assertEqual(result["candidates_schema"], "extrusion-candidates-0.1")
        self.assertEqual(len(result["candidates"]), 15)
        accepted = [item for item in result["candidates"] if item["status"] == "accepted"]
        self.assertEqual(len(accepted), 3)
        pairs = [(item["base_face_id"], item["opposite_face_id"]) for item in result["candidates"]]
        self.assertEqual(len(pairs), len(set(tuple(sorted(pair)) for pair in pairs)))
        self.assertTrue(all(left < right for left, right in pairs))

    def test_each_candidate_records_hard_checks_measurements_and_rejection_reasons(self):
        result = self.infer("D-S04")
        required = {
            "opposite_normals",
            "positive_separation",
            "centroid_alignment",
            "area_match",
            "boundary_translation_match",
            "side_connection_coverage",
        }
        for candidate in result["candidates"]:
            self.assertEqual(set(candidate["checks"]), required)
            self.assertNotIn("weighted_total", candidate)
            self.assertIn("passed_hard_checks", candidate["score_components"])
            if candidate["status"] == "rejected":
                self.assertTrue(candidate["rejection_reasons"])

    def test_l_shape_has_one_fact_derived_extrusion(self):
        result = self.infer("D-S04")
        accepted = [item for item in result["candidates"] if item["status"] == "accepted"]
        self.assertEqual(len(accepted), 1)
        self.assertAlmostEqual(accepted[0]["distance_mm"], 18.0, places=8)
        self.assertEqual(accepted[0]["boundary_match_kind"], "translated_lines")

    def test_cylinder_matches_full_circle_boundaries_and_excludes_side_surface(self):
        result = self.infer("D-S07")
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["status"], "accepted")
        self.assertAlmostEqual(candidate["distance_mm"], 28.0, places=8)
        self.assertEqual(candidate["boundary_match_kind"], "translated_full_circle")

    def test_rotated_box_and_complex_polygon_keep_expected_geometric_distances(self):
        rotated = [item for item in self.infer("D-S09")["candidates"] if item["status"] == "accepted"]
        complex_polygon = [item for item in self.infer("D-S10")["candidates"] if item["status"] == "accepted"]
        self.assertEqual(len(rotated), 3)
        self.assertIn(19.0, [round(item["distance_mm"], 8) for item in rotated])
        self.assertEqual(len(complex_polygon), 1)
        self.assertAlmostEqual(complex_polygon[0]["distance_mm"], 13.0, places=8)

    def test_prevalidation_order_is_deterministic_and_uses_no_validation_metrics(self):
        first = self.infer("D-S10")
        second = self.infer("D-S10")
        self.assertEqual(first, second)
        ids = [item["candidate_id"] for item in first["candidates"]]
        expected = sorted(
            first["candidates"],
            key=lambda item: (-item["score_components"]["passed_hard_checks"], item["candidate_id"]),
        )
        self.assertEqual(ids, [item["candidate_id"] for item in expected])
        forbidden = {"volume_error", "bbox_error", "surface_p95_mm", "ambiguous"}
        self.assertTrue(all(forbidden.isdisjoint(item) for item in first["candidates"]))

    def test_candidate_evidence_writer_uses_canonical_json_bytes(self):
        result = self.infer("D-S07")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidates.json"
            extrusion_inference.write_candidates(result, output)
            self.assertEqual(output.read_bytes(), extrusion_inference.canonical_json_bytes(result))


if __name__ == "__main__":
    unittest.main()
