import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import brep_inspection
import candidate_validation
import profile_reconstruction
import through_hole_inference
import topology_adjacency


DEVELOPMENT_INPUTS = PROJECT_ROOT / "benchmarks" / "inputs" / "development"


def load_validator():
    path = PROJECT_ROOT / "shared" / "sequence_validator.py"
    spec = importlib.util.spec_from_file_location("sequence_validator_checkpoint3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_evidence(case_id):
    summary, context = brep_inspection.inspect_step_with_context(
        DEVELOPMENT_INPUTS / f"{case_id}.step", case_id
    )
    adjacency = topology_adjacency.build_adjacency(summary, context)
    hole_facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
    candidates = through_hole_inference.generate_coupled_candidates(
        summary, adjacency, hole_facts
    )["candidates"]
    accepted = [candidate for candidate in candidates if candidate["status"] == "accepted"]
    if len(accepted) != 1:
        raise AssertionError(f"expected one accepted candidate for {case_id}")
    return summary, accepted[0]


class ThroughHoleReconstructionArtifactTests(unittest.TestCase):
    def test_checkpoint3_module_and_public_apis_exist(self):
        spec = importlib.util.find_spec("through_hole_reconstruction")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in (
            "ThroughHoleReconstructionError",
            "sequence_from_summary",
            "recover_development_sequence",
            "rebuild_sequence_step",
            "validate_reconstruction",
            "write_sequence",
            "checkpoint3_validation_protocol",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(module, name))


class ThroughHoleSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import through_hole_reconstruction

        cls.reconstruction = through_hole_reconstruction
        cls.validator = load_validator()
        cls.cases = {
            f"D-H{index:02d}": case_evidence(f"D-H{index:02d}")
            for index in range(1, 6)
        }

    def test_all_five_emit_one_valid_automatic_four_operation_sequence(self):
        inferred_root_cases = []
        for case_id, (summary, candidate) in self.cases.items():
            with self.subTest(case_id=case_id):
                sequence = self.reconstruction.sequence_from_summary(summary, candidate)
                self.assertEqual(sequence["schema_version"], "cadseq-0.2")
                self.assertEqual(sequence["model_id"], case_id)
                self.assertEqual(sequence["replay_mode"], "automatic")
                self.assertEqual(sequence["corrections"], [])
                self.assertEqual(len(sequence["operations"]), 4)
                self.assertEqual(
                    [operation["operation_type"] for operation in sequence["operations"]],
                    ["sketch", "extrude", "sketch", "extrude"],
                )
                self.assertEqual(
                    self.validator.validate_sequence(sequence),
                    {"valid": True, "errors": []},
                )
                if (
                    sequence["operations"][0]["sketch_plane"].get("frame_source")
                    == "inferred_brep"
                ):
                    inferred_root_cases.append(case_id)
        self.assertIn("D-H04", inferred_root_cases)

    def test_base_sketch_selects_only_candidate_outer_wire(self):
        for case_id, (summary, candidate) in self.cases.items():
            with self.subTest(case_id=case_id):
                base_face_id = candidate["base"]["base_face_id"]
                base_face = next(
                    face
                    for face in summary["solids"][0]["faces"]
                    if face["face_id"] == base_face_id
                )
                incident_ids = {use["wire_id"] for use in base_face["wire_uses"]}
                expected_outer = next(
                    wire_id
                    for wire_id in candidate["base"]["outer_wire_ids"]
                    if wire_id in incident_ids
                )
                reconstructed = profile_reconstruction.reconstruct_profile(
                    summary,
                    {
                        "status": "accepted",
                        "base_face_id": base_face_id,
                        "extrusion_direction": candidate["base"]["extrusion_direction"],
                        "source_face_outward_normal": candidate["base"][
                            "source_face_outward_normal"
                        ],
                    },
                    outer_wire_id=expected_outer,
                )
                sequence = self.reconstruction.sequence_from_summary(summary, candidate)
                primitives = sequence["operations"][0]["loops"][0]["primitives"]
                self.assertEqual(primitives, reconstructed["loop"]["primitives"])
                self.assertTrue(3 <= len(primitives) <= 8)
                self.assertEqual({primitive["type"] for primitive in primitives}, {"line"})

    def test_hole_circle_is_resolved_by_support_face_incidence(self):
        for case_id, (summary, candidate) in self.cases.items():
            with self.subTest(case_id=case_id):
                shuffled = copy.deepcopy(candidate)
                shuffled["hole"]["circle_edge_ids"].reverse()
                shuffled["hole"]["inner_wire_ids"].reverse()
                sequence = self.reconstruction.sequence_from_summary(summary, shuffled)
                hole_sketch = sequence["operations"][2]
                plane = hole_sketch["sketch_plane"]
                self.assertEqual(
                    plane["semantic_reference"], candidate["semantic_replay"]["operation_cap"]
                )
                self.assertNotIn("frame_source", plane)
                self.assertEqual(plane["frame"]["normal"], candidate["base"]["extrusion_direction"])

                support_face_id = candidate["semantic_replay"]["support_face_id"]
                support_face = next(
                    face
                    for face in summary["solids"][0]["faces"]
                    if face["face_id"] == support_face_id
                )
                incident_wire_ids = {use["wire_id"] for use in support_face["wire_uses"]}
                support_wire_id = next(
                    wire_id
                    for wire_id in candidate["hole"]["inner_wire_ids"]
                    if wire_id in incident_wire_ids
                )
                support_wire = next(
                    wire
                    for wire in summary["solids"][0]["wires"]
                    if wire["wire_id"] == support_wire_id
                )
                support_edge_id = next(
                    use["edge_id"]
                    for use in support_wire["edge_uses"]
                    if use["edge_id"] in candidate["hole"]["circle_edge_ids"]
                )
                support_edge = next(
                    edge
                    for edge in summary["solids"][0]["edges"]
                    if edge["edge_id"] == support_edge_id
                )
                circle = hole_sketch["loops"][0]["primitives"][0]
                frame = plane["frame"]
                normal = frame["normal"]
                x_axis = frame["x_axis"]
                y_axis = [
                    normal[1] * x_axis[2] - normal[2] * x_axis[1],
                    normal[2] * x_axis[0] - normal[0] * x_axis[2],
                    normal[0] * x_axis[1] - normal[1] * x_axis[0],
                ]
                unprojected = [
                    frame["origin"][axis]
                    + circle["center"][0] * x_axis[axis]
                    + circle["center"][1] * y_axis[axis]
                    for axis in range(3)
                ]
                for actual, expected in zip(
                    unprojected, support_edge["curve_parameters"]["center_mm"]
                ):
                    self.assertAlmostEqual(actual, expected, places=7)
                self.assertEqual(circle["radius_mm"], candidate["hole"]["radius_mm"])

    def test_cut_is_through_all_and_points_into_material(self):
        for case_id, (summary, candidate) in self.cases.items():
            with self.subTest(case_id=case_id):
                cut = self.reconstruction.sequence_from_summary(summary, candidate)["operations"][3]
                self.assertEqual(cut["boolean_type"], "cut")
                self.assertEqual(cut["extent"], {"type": "through_all"})
                self.assertEqual(cut["direction"], candidate["semantic_replay"]["cut_direction"])

    def test_sequence_generation_rejects_unaccepted_and_malformed_candidates(self):
        summary, candidate = self.cases["D-H01"]
        rejected = copy.deepcopy(candidate)
        rejected["status"] = "rejected"
        with self.assertRaisesRegex(
            self.reconstruction.ThroughHoleReconstructionError, "candidate_not_accepted"
        ):
            self.reconstruction.sequence_from_summary(summary, rejected)
        malformed = copy.deepcopy(candidate)
        malformed["semantic_replay"]["support_face_id"] = "face-missing"
        with self.assertRaisesRegex(
            self.reconstruction.ThroughHoleReconstructionError, "malformed_candidate"
        ):
            self.reconstruction.sequence_from_summary(summary, malformed)

    def test_sequence_generation_rejects_incomplete_paired_incidence_evidence(self):
        summary, candidate = self.cases["D-H04"]
        for field_path in (
            ("base", "outer_wire_ids"),
            ("hole", "inner_wire_ids"),
            ("hole", "circle_edge_ids"),
        ):
            with self.subTest(field_path=field_path):
                malformed = copy.deepcopy(candidate)
                malformed[field_path[0]][field_path[1]] = malformed[field_path[0]][
                    field_path[1]
                ][:1]
                with self.assertRaisesRegex(
                    self.reconstruction.ThroughHoleReconstructionError,
                    "malformed_candidate",
                ):
                    self.reconstruction.sequence_from_summary(summary, malformed)

        missing_provenance = copy.deepcopy(candidate)
        del missing_provenance["base"]["source_face_outward_normal"]
        with self.assertRaisesRegex(
            self.reconstruction.ThroughHoleReconstructionError, "malformed_candidate"
        ):
            self.reconstruction.sequence_from_summary(summary, missing_provenance)

    def test_sequence_bytes_are_deterministic_and_writer_refuses_overwrite(self):
        summary, candidate = self.cases["D-H05"]
        first = self.reconstruction.sequence_from_summary(summary, candidate)
        second = self.reconstruction.sequence_from_summary(summary, copy.deepcopy(candidate))
        self.assertEqual(
            brep_inspection.canonical_json_bytes(first),
            brep_inspection.canonical_json_bytes(second),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sequence.json"
            self.reconstruction.write_sequence(first, output)
            self.assertEqual(output.read_bytes(), brep_inspection.canonical_json_bytes(first))
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                self.reconstruction.write_sequence(first, output)


class ThroughHoleDevelopmentEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import through_hole_reconstruction

        cls.reconstruction = through_hole_reconstruction

    def test_entry_guards_then_imports_once_and_returns_evidence_plus_sequence(self):
        input_path = DEVELOPMENT_INPUTS / "D-H02.step"
        original = brep_inspection.inspect_step_with_context
        with mock.patch.object(
            self.reconstruction.brep_inspection,
            "inspect_step_with_context",
            wraps=original,
        ) as inspected:
            result = self.reconstruction.recover_development_sequence(
                PROJECT_ROOT, "D-H02", input_path
            )
        inspected.assert_called_once_with(input_path.resolve(), "D-H02")
        self.assertEqual(set(result), {"evidence", "sequence"})
        self.assertEqual(
            set(result["evidence"]),
            {
                "brep_summary",
                "adjacency",
                "hole_facts",
                "coupled_candidates",
                "selected_candidate",
            },
        )
        self.assertEqual(result["sequence"]["model_id"], "D-H02")
        self.assertFalse(
            {"expected_scope", "expected_behavior", "geometry"}
            & _all_keys(result)
        )

    def test_entry_rejects_path_before_import_and_wraps_gate3_error(self):
        outside = PROJECT_ROOT / "models" / "manual_box_hole.step"
        with mock.patch.object(
            self.reconstruction.brep_inspection,
            "inspect_step_with_context",
        ) as inspected:
            with self.assertRaisesRegex(
                self.reconstruction.ThroughHoleReconstructionError,
                "input_not_frozen_development",
            ):
                self.reconstruction.recover_development_sequence(
                    PROJECT_ROOT, "D-H01", outside
                )
        inspected.assert_not_called()

    def test_entry_rejects_ambiguous_accepted_candidates(self):
        input_path = DEVELOPMENT_INPUTS / "D-H01.step"
        summary, candidate = case_evidence("D-H01")
        ambiguous = {
            "coupled_candidates_schema": "coupled-through-hole-candidates-0.1",
            "model_id": "D-H01",
            "source_step_sha256": summary["source_step_sha256"],
            "ordering": "candidate_id",
            "candidates": [candidate, copy.deepcopy(candidate)],
            "rejection_reasons": [],
        }
        ambiguous["candidates"][1]["candidate_id"] += "-duplicate"
        with mock.patch.object(
            self.reconstruction.through_hole_inference,
            "generate_coupled_candidates",
            return_value=ambiguous,
        ):
            with self.assertRaisesRegex(
                self.reconstruction.ThroughHoleReconstructionError,
                "accepted_candidate_count_mismatch",
            ):
                self.reconstruction.recover_development_sequence(
                    PROJECT_ROOT, "D-H01", input_path
                )


class ThroughHoleCadQueryRebuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import through_hole_reconstruction

        cls.reconstruction = through_hole_reconstruction
        cls.validator = load_validator()
        cls.cases = {
            f"D-H{index:02d}": case_evidence(f"D-H{index:02d}")
            for index in range(1, 6)
        }

    def test_checkpoint_protocol_keeps_surface_diagnostic_only(self):
        protocol = self.reconstruction.checkpoint3_validation_protocol()
        self.assertEqual(protocol["protocol_schema"], "gate3-checkpoint3-validation-0.1")
        self.assertEqual(protocol["surface"]["mode"], "diagnostic_only")
        self.assertNotIn("symmetric_p95_ratio_threshold", protocol["surface"])
        self.assertNotIn("max_face_p95_ratio_threshold", protocol["surface"])
        self.assertEqual(
            set(protocol["hard_conditions"]),
            {
                "single_valid_solid",
                "volume_absolute_tolerance_mm3",
                "volume_relative_tolerance",
                "bbox_coordinate_tolerance_mm",
            },
        )

    def test_complete_external_reconstruction_passes_hard_checks_for_all_five(self):
        protocol = self.reconstruction.checkpoint3_validation_protocol()
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            for case_id, (summary, candidate) in self.cases.items():
                with self.subTest(case_id=case_id):
                    sequence = self.reconstruction.sequence_from_summary(summary, candidate)
                    with mock.patch.object(
                        self.reconstruction.through_hole_inference,
                        "generate_coupled_candidates",
                    ) as candidate_generator:
                        metrics = self.reconstruction.validate_reconstruction(
                            DEVELOPMENT_INPUTS / f"{case_id}.step",
                            sequence,
                            output_dir / f"{case_id}.step",
                            protocol,
                        )
                    candidate_generator.assert_not_called()
                    self.assertTrue(metrics["valid_single_solid"])
                    self.assertTrue(metrics["volume_pass"])
                    self.assertTrue(metrics["bbox_pass"])
                    self.assertTrue(metrics["geometry_pass"])
                    self.assertEqual(metrics["surface_mode"], "diagnostic_only")
                    self.assertIsNone(metrics["surface_pass"])

    def test_rebuilder_validates_sequence_and_refuses_overwrite(self):
        summary, candidate = self.cases["D-H01"]
        sequence = self.reconstruction.sequence_from_summary(summary, candidate)
        malformed = copy.deepcopy(sequence)
        malformed["operations"][3]["extent"] = {"type": "distance", "distance_mm": 20.0}
        with tempfile.TemporaryDirectory() as directory:
            invalid_output = Path(directory) / "invalid.step"
            with self.assertRaisesRegex(
                self.reconstruction.ThroughHoleReconstructionError,
                "sequence_validation_failed:invalid_boolean_extent",
            ):
                self.reconstruction.rebuild_sequence_step(malformed, invalid_output)
            self.assertFalse(invalid_output.exists())

            output = Path(directory) / "valid.step"
            self.reconstruction.rebuild_sequence_step(sequence, output)
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                self.reconstruction.rebuild_sequence_step(sequence, output)

    def test_base_only_reconstruction_is_not_final_success(self):
        summary, candidate = self.cases["D-H01"]
        sequence = self.reconstruction.sequence_from_summary(summary, candidate)
        base_only = copy.deepcopy(sequence)
        base_only["operations"] = base_only["operations"][:2]
        protocol = self.reconstruction.checkpoint3_validation_protocol()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "base-only.step"
            candidate_validation.rebuild_sequence_step(base_only, output)
            metrics = candidate_validation.validate_replay_step(
                DEVELOPMENT_INPUTS / "D-H01.step", output, protocol
            )
        self.assertFalse(metrics["volume_pass"])
        self.assertFalse(metrics["geometry_pass"])

    def test_cut_direction_away_from_positive_cap_has_no_boolean_intersection(self):
        summary, candidate = self.cases["D-H01"]
        sequence = self.reconstruction.sequence_from_summary(summary, candidate)
        sequence["operations"][3]["direction"] = [0.0, 0.0, 1.0]
        self.assertEqual(
            self.validator.validate_sequence(sequence), {"valid": True, "errors": []}
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "wrong-direction.step"
            with self.assertRaisesRegex(
                self.reconstruction.ThroughHoleReconstructionError,
                "boolean_no_intersection",
            ):
                self.reconstruction.rebuild_sequence_step(sequence, output)
            self.assertFalse(output.exists())

    def test_negative_cap_equivalent_geometry_is_outside_checkpoint_scope(self):
        summary, candidate = self.cases["D-H01"]
        sequence = self.reconstruction.sequence_from_summary(summary, candidate)
        base_frame = sequence["operations"][0]["sketch_plane"]["frame"]
        hole_plane = sequence["operations"][2]["sketch_plane"]
        hole_plane["semantic_reference"]["role"] = "negative_end_cap"
        hole_plane["frame"]["origin"] = list(base_frame["origin"])
        sequence["operations"][3]["direction"] = [0.0, 0.0, 1.0]
        self.assertEqual(
            self.validator.validate_sequence(sequence), {"valid": True, "errors": []}
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "negative-cap.step"
            with self.assertRaisesRegex(
                self.reconstruction.ThroughHoleReconstructionError,
                "unsupported_operation_cap_role",
            ):
                self.reconstruction.rebuild_sequence_step(sequence, output)
            self.assertFalse(output.exists())


def _all_keys(value):
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(_all_keys(child))
        return keys
    if isinstance(value, list):
        keys = set()
        for child in value:
            keys.update(_all_keys(child))
        return keys
    return set()


if __name__ == "__main__":
    unittest.main()
