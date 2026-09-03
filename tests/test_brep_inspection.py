import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import brep_inspection


class BRepInspectionTests(unittest.TestCase):
    def step(self, case_id):
        return PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"

    def test_box_summary_contains_only_canonical_brep_facts(self):
        summary = brep_inspection.inspect_step(self.step("D-S01"), "D-S01")
        self.assertEqual(summary["brep_summary_schema"], "brep-summary-0.1")
        self.assertEqual(summary["model_id"], "D-S01")
        self.assertNotIn("run_id", summary)
        self.assertNotIn("path", json.dumps(summary).lower())
        self.assertEqual(summary["solid_count"], 1)
        self.assertEqual(
            summary["topology_counts"],
            {"faces": 6, "wires": 6, "edges": 12, "vertices": 8},
        )
        solid = summary["solids"][0]
        self.assertAlmostEqual(solid["volume_mm3"], 48000.0, places=6)
        self.assertAlmostEqual(solid["surface_area_mm2"], 8800.0, places=6)
        self.assertTrue(all(face["surface_type"] == "plane" for face in solid["faces"]))
        self.assertTrue(all(edge["curve_type"] == "line" for edge in solid["edges"]))
        forbidden = {"adjacency", "convexity", "candidate", "score", "fusion"}
        self.assertTrue(forbidden.isdisjoint(json.dumps(summary).lower().split('"')))

    def test_all_topology_references_resolve(self):
        solid = brep_inspection.inspect_step(self.step("D-S04"), "D-S04")["solids"][0]
        face_ids = {item["face_id"] for item in solid["faces"]}
        wire_ids = {item["wire_id"] for item in solid["wires"]}
        edge_ids = {item["edge_id"] for item in solid["edges"]}
        vertex_ids = {item["vertex_id"] for item in solid["vertices"]}
        self.assertEqual(set(solid["face_ids"]), face_ids)
        for face in solid["faces"]:
            self.assertTrue({use["wire_id"] for use in face["wire_uses"]} <= wire_ids)
        for wire in solid["wires"]:
            self.assertTrue({use["edge_id"] for use in wire["edge_uses"]} <= edge_ids)
        for edge in solid["edges"]:
            self.assertTrue(set(edge["vertex_ids"]) <= vertex_ids)

    def test_cylinder_uses_type_specific_surface_and_circle_facts(self):
        solid = brep_inspection.inspect_step(self.step("D-S07"), "D-S07")["solids"][0]
        cylinder = next(face for face in solid["faces"] if face["surface_type"] == "cylinder")
        self.assertNotIn("normal", cylinder["surface_parameters"])
        self.assertAlmostEqual(cylinder["surface_parameters"]["radius_mm"], 15.0, places=8)
        circles = [edge for edge in solid["edges"] if edge["curve_type"] == "circle"]
        self.assertEqual(len(circles), 2)
        self.assertTrue(all(edge["circle_form"] == "full_circle" for edge in circles))
        self.assertTrue(all(edge["is_closed"] for edge in circles))

    def test_rotated_plane_preserves_finite_unit_direction(self):
        solid = brep_inspection.inspect_step(self.step("D-S09"), "D-S09")["solids"][0]
        for face in solid["faces"]:
            if face["surface_type"] == "plane":
                normal = face["surface_parameters"]["normal"]
                self.assertAlmostEqual(sum(value * value for value in normal), 1.0, places=10)

    def test_cli_is_byte_deterministic_across_independent_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            command = [
                sys.executable,
                str(PROJECT_ROOT / "external" / "inspect_brep.py"),
                "--input",
                str(self.step("D-S07")),
                "--model-id",
                "D-S07",
            ]
            subprocess.run(command + ["--output", str(first)], check=True)
            subprocess.run(command + ["--output", str(second)], check=True)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )

    def test_signature_collision_is_not_silently_disambiguated(self):
        with self.assertRaisesRegex(brep_inspection.BRepInspectionError, "topology_id_collision"):
            brep_inspection.assign_canonical_ids(
                "edge",
                [
                    {"_identity": "topology-a", "_signature": ["line", 1.0]},
                    {"_identity": "topology-b", "_signature": ["line", 1.0]},
                ],
            )

    def test_missing_step_has_structured_error_code(self):
        with self.assertRaisesRegex(brep_inspection.BRepInspectionError, "step_not_found"):
            brep_inspection.inspect_step(PROJECT_ROOT / "missing.step", "missing")


if __name__ == "__main__":
    unittest.main()
