import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import topology_adjacency


class TopologyAdjacencyTests(unittest.TestCase):
    def step(self, case_id):
        return PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"

    def test_box_shared_edges_are_all_convex(self):
        result = topology_adjacency.inspect_adjacency(self.step("D-S01"), "D-S01")
        self.assertEqual(result["adjacency_schema"], "face-adjacency-0.1")
        self.assertEqual(len(result["relations"]), 12)
        self.assertEqual({item["classification"] for item in result["relations"]}, {"convex"})
        self.assertTrue(all(item["dihedral_angle_rad"] > 0 for item in result["relations"]))

    def test_l_shape_contains_convex_and_concave_relations(self):
        result = topology_adjacency.inspect_adjacency(self.step("D-S04"), "D-S04")
        labels = {item["classification"] for item in result["relations"]}
        self.assertIn("convex", labels)
        self.assertIn("concave", labels)

    def test_cylinder_uses_local_normals_without_self_adjacency(self):
        result = topology_adjacency.inspect_adjacency(self.step("D-S07"), "D-S07")
        self.assertEqual(len(result["relations"]), 2)
        self.assertTrue(all(item["face_1_id"] != item["face_2_id"] for item in result["relations"]))
        self.assertTrue(all(item["classification"] == "convex" for item in result["relations"]))
        self.assertTrue(all(item["normal_evaluation"] == "shared_edge_midpoint" for item in result["relations"]))

    def test_face_dictionary_is_symmetric_and_references_relations(self):
        result = topology_adjacency.inspect_adjacency(self.step("D-S01"), "D-S01")
        relation_ids = {item["relation_id"] for item in result["relations"]}
        for face_id, records in result["faces"].items():
            for record in records:
                self.assertIn(record["relation_id"], relation_ids)
                reverse = result["faces"][record["neighbor_face_id"]]
                self.assertTrue(
                    any(item["neighbor_face_id"] == face_id and item["relation_id"] == record["relation_id"] for item in reverse)
                )

    def test_unreliable_local_measurement_is_preserved_as_unknown(self):
        with patch.object(
            topology_adjacency,
            "_measure_relation",
            side_effect=topology_adjacency.AdjacencyMeasurementError(
                "synthetic kernel evaluation failure"
            ),
        ):
            result = topology_adjacency.inspect_adjacency(self.step("D-S01"), "D-S01")
        self.assertTrue(result["relations"])
        self.assertEqual({item["classification"] for item in result["relations"]}, {"unknown"})
        self.assertEqual(
            {item["measurement_error"] for item in result["relations"]},
            {"normal_or_tangent_evaluation_failed"},
        )

    def test_unexpected_measurement_error_is_not_silently_downgraded(self):
        with patch.object(
            topology_adjacency,
            "_measure_relation",
            side_effect=RuntimeError("programming error"),
        ):
            with self.assertRaisesRegex(RuntimeError, "programming error"):
                topology_adjacency.inspect_adjacency(self.step("D-S01"), "D-S01")


if __name__ == "__main__":
    unittest.main()
