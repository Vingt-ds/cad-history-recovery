import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import brep_inspection
import extrusion_inference
import profile_reconstruction


def load_validator():
    path = PROJECT_ROOT / "shared" / "sequence_validator.py"
    spec = importlib.util.spec_from_file_location("sequence_validator_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()

    def step(self, case_id):
        return PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"

    def test_offset_profiles_emit_valid_automatic_inferred_sequences(self):
        expected_edges = {"D-S03": 5, "D-S05": 8, "D-S06": 8, "D-S08": 6, "D-S10": 7}
        for case_id, edge_count in expected_edges.items():
            with self.subTest(case_id=case_id):
                sequence = profile_reconstruction.recover_sequence(self.step(case_id), case_id)
                self.assertEqual(self.validator.validate_sequence(sequence), {"valid": True, "errors": []})
                self.assertEqual(sequence["schema_version"], "cadseq-0.2")
                self.assertEqual(sequence["replay_mode"], "automatic")
                self.assertEqual(sequence["corrections"], [])
                sketch = sequence["operations"][0]
                plane = sketch["sketch_plane"]
                self.assertEqual(plane["frame_source"], "inferred_brep")
                self.assertEqual(plane["semantic_reference"], {"type": "absolute_frame"})
                self.assertEqual(len(sketch["loops"][0]["primitives"]), edge_count)
                self.assertEqual({item["type"] for item in sketch["loops"][0]["primitives"]}, {"line"})
                extrude = sequence["operations"][1]
                self.assertEqual(extrude["direction"], plane["frame"]["normal"])
                self.assertGreater(extrude["extent"]["distance_mm"], 0.0)

    def test_named_xy_profile_and_full_circle_are_reconstructed_without_correction(self):
        box = profile_reconstruction.recover_sequence(
            self.step("D-S01"), "D-S01", "extrusion-face-002-face-003"
        )
        cylinder = profile_reconstruction.recover_sequence(self.step("D-S07"), "D-S07")
        for sequence in (box, cylinder):
            plane = sequence["operations"][0]["sketch_plane"]
            self.assertEqual(plane["frame_source"], "origin_named")
            self.assertEqual(plane["semantic_reference"], {"type": "origin_plane", "role": "XY"})
            self.assertEqual(sequence["corrections"], [])
            self.assertEqual(self.validator.validate_sequence(sequence), {"valid": True, "errors": []})
        primitive = cylinder["operations"][0]["loops"][0]["primitives"][0]
        self.assertEqual(primitive["type"], "circle")
        self.assertAlmostEqual(primitive["radius_mm"], 15.0, places=8)

    def test_line_profile_has_positive_winding_and_closes(self):
        sequence = profile_reconstruction.recover_sequence(self.step("D-S04"), "D-S04")
        primitives = sequence["operations"][0]["loops"][0]["primitives"]
        points = [item["start"] for item in primitives]
        area_twice = sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        self.assertGreater(area_twice, 0.0)
        for index, primitive in enumerate(primitives):
            self.assertEqual(primitive["end"], primitives[(index + 1) % len(primitives)]["start"])

    def test_multiple_profile_loops_are_rejected(self):
        summary, candidate = self.summary_and_unique_candidate("D-S03")
        face = self.face_for_candidate(summary, candidate)
        face["wire_uses"].append(copy.deepcopy(face["wire_uses"][0]))
        with self.assertRaisesRegex(profile_reconstruction.ProfileReconstructionError, "multiple_profile_loops"):
            profile_reconstruction.reconstruct_profile(summary, candidate)

    def test_mixed_and_arc_profiles_are_rejected(self):
        summary, candidate = self.summary_and_unique_candidate("D-S03")
        face = self.face_for_candidate(summary, candidate)
        wire_id = face["wire_uses"][0]["wire_id"]
        wire = next(item for item in summary["solids"][0]["wires"] if item["wire_id"] == wire_id)
        edge_id = wire["edge_uses"][0]["edge_id"]
        edge = next(item for item in summary["solids"][0]["edges"] if item["edge_id"] == edge_id)
        edge["curve_type"] = "circle"
        edge["circle_form"] = "circular_arc"
        with self.assertRaisesRegex(profile_reconstruction.ProfileReconstructionError, "mixed_profile_curves"):
            profile_reconstruction.reconstruct_profile(summary, candidate)

        circle_summary, circle_candidate = self.summary_and_unique_candidate("D-S07")
        circle_face = self.face_for_candidate(circle_summary, circle_candidate)
        circle_wire_id = circle_face["wire_uses"][0]["wire_id"]
        circle_wire = next(
            item for item in circle_summary["solids"][0]["wires"] if item["wire_id"] == circle_wire_id
        )
        circle_edge_id = circle_wire["edge_uses"][0]["edge_id"]
        circle_edge = next(
            item
            for item in circle_summary["solids"][0]["edges"]
            if item["edge_id"] == circle_edge_id
        )
        circle_edge["circle_form"] = "circular_arc"
        with self.assertRaisesRegex(profile_reconstruction.ProfileReconstructionError, "unsupported_circular_arc"):
            profile_reconstruction.reconstruct_profile(circle_summary, circle_candidate)

    def test_degenerate_and_self_intersecting_polygons_are_rejected(self):
        with self.assertRaisesRegex(profile_reconstruction.ProfileReconstructionError, "degenerate_profile_edge"):
            profile_reconstruction.validate_simple_polygon([(0, 0), (1, 0), (1, 0), (0, 1)])
        with self.assertRaisesRegex(profile_reconstruction.ProfileReconstructionError, "self_intersecting_profile"):
            profile_reconstruction.validate_simple_polygon([(0, 0), (2, 2), (0, 2), (2, 0)])

    def test_sequence_writer_uses_canonical_json_bytes(self):
        sequence = profile_reconstruction.recover_sequence(self.step("D-S03"), "D-S03")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "inferred_sequence.json"
            profile_reconstruction.write_sequence(sequence, output)
            self.assertEqual(output.read_bytes(), profile_reconstruction.canonical_json_bytes(sequence))

    def summary_and_unique_candidate(self, case_id):
        summary = brep_inspection.inspect_step(self.step(case_id), case_id)
        candidates = extrusion_inference.infer_extrusions(self.step(case_id), case_id)["candidates"]
        accepted = [item for item in candidates if item["status"] == "accepted"]
        self.assertEqual(len(accepted), 1)
        return summary, accepted[0]

    @staticmethod
    def face_for_candidate(summary, candidate):
        return next(
            item
            for item in summary["solids"][0]["faces"]
            if item["face_id"] == candidate["base_face_id"]
        )


if __name__ == "__main__":
    unittest.main()
