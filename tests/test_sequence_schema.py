import copy
import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "shared" / "sequence_validator.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("sequence_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SequenceSchemaArtifactTests(unittest.TestCase):
    def test_gate1_schema_artifacts_exist(self):
        required = [
            PROJECT_ROOT / "shared" / "sequence_validator.py",
            PROJECT_ROOT / "docs" / "sequence_schema_v0.1.md",
            PROJECT_ROOT / "docs" / "third_party_and_references.md",
            PROJECT_ROOT / "sequences" / "known" / "box.json",
            PROJECT_ROOT / "sequences" / "known" / "box_hole.json",
            PROJECT_ROOT / "sequences" / "invalid" / "cut_distance.json",
            PROJECT_ROOT / "sequences" / "invalid" / "missing_loop_reference.json",
            PROJECT_ROOT / "sequences" / "invalid" / "invalid_operation_cap.json",
            PROJECT_ROOT / "sequences" / "invalid" / "non_unit_frame.json",
        ]
        missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
        self.assertEqual(missing, [], f"missing Gate 1 schema artifacts: {missing}")


class SequenceSchemaValidFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()

    def assert_fixture_is_valid(self, name):
        path = PROJECT_ROOT / "sequences" / "known" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        result = self.validator.validate_sequence(data)
        self.assertEqual(result, {"valid": True, "errors": []})

    def test_known_box_is_valid(self):
        self.assert_fixture_is_valid("box.json")

    def test_known_box_hole_is_valid(self):
        self.assert_fixture_is_valid("box_hole.json")

    def test_explicitly_authorized_absolute_frame_is_valid(self):
        data = copy.deepcopy(
            json.loads(
                (PROJECT_ROOT / "sequences" / "known" / "box.json").read_text(encoding="utf-8")
            )
        )
        data["replay_mode"] = "absolute_fallback"
        data["operations"][0]["sketch_plane"]["semantic_reference"] = {
            "type": "absolute_frame",
            "correction_id": "correction_001",
        }
        data["corrections"] = [
            {
                "correction_id": "correction_001",
                "correction_number": 1,
                "operation_id": "sketch_base",
                "reason": "semantic reference could not be resolved",
                "before": {"reference_type": "origin_plane"},
                "after": {"reference_type": "absolute_frame"},
            }
        ]
        self.assertEqual(self.validator.validate_sequence(data), {"valid": True, "errors": []})


class SequenceSchemaInvalidFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        cls.box = json.loads(
            (PROJECT_ROOT / "sequences" / "known" / "box.json").read_text(encoding="utf-8")
        )
        cls.box_hole = json.loads(
            (PROJECT_ROOT / "sequences" / "known" / "box_hole.json").read_text(encoding="utf-8")
        )

    def assert_error_code(self, data, expected_code):
        result = self.validator.validate_sequence(data)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], expected_code)
        self.assertIn("path", result["errors"][0])
        self.assertIn("message", result["errors"][0])

    def test_named_invalid_fixtures_return_expected_codes(self):
        expected = {
            "cut_distance.json": "invalid_boolean_extent",
            "missing_loop_reference.json": "unknown_loop_reference",
            "invalid_operation_cap.json": "invalid_operation_cap_reference",
            "non_unit_frame.json": "non_unit_vector",
        }
        for name, code in expected.items():
            with self.subTest(name=name):
                data = json.loads(
                    (PROJECT_ROOT / "sequences" / "invalid" / name).read_text(encoding="utf-8")
                )
                self.assert_error_code(data, code)

    def test_duplicate_operation_id_is_rejected(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["operation_id"] = "sketch_base"
        self.assert_error_code(data, "duplicate_operation_id")

    def test_dependency_must_reference_an_earlier_operation(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["dependencies"] = ["extrude_base"]
        self.assert_error_code(data, "dependency_not_earlier")

    def test_profile_sketch_must_be_a_dependency(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["dependencies"] = []
        self.assert_error_code(data, "missing_profile_dependency")

    def test_profile_loops_cannot_repeat_outer_as_inner(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["profile"]["inner_loop_ids"] = ["base_outer"]
        self.assert_error_code(data, "duplicate_profile_loop")

    def test_outer_reference_must_point_to_an_outer_loop(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["loops"][0]["loop_type"] = "inner"
        self.assert_error_code(data, "outer_loop_type_mismatch")

    def test_inner_reference_must_point_to_an_inner_loop(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["loops"].append(
            {
                "loop_id": "wrong_inner",
                "loop_type": "outer",
                "primitives": [
                    {
                        "primitive_id": "circle_inner",
                        "type": "circle",
                        "center": [30.0, 20.0],
                        "radius_mm": 5.0,
                    }
                ],
            }
        )
        data["operations"][1]["profile"]["inner_loop_ids"] = ["wrong_inner"]
        self.assert_error_code(data, "inner_loop_type_mismatch")

    def test_profile_sketch_reference_must_exist(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["profile"]["sketch_id"] = "missing_sketch"
        self.assert_error_code(data, "unknown_sketch_reference")

    def test_extrude_direction_must_follow_sketch_normal(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["direction"] = [1.0, 0.0, 0.0]
        self.assert_error_code(data, "direction_not_parallel")

    def test_distance_must_be_positive(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["extent"]["distance_mm"] = 0.0
        self.assert_error_code(data, "invalid_distance")

    def test_cut_requires_a_previous_new_body(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["boolean_type"] = "cut"
        data["operations"][1]["extent"] = {"type": "through_all"}
        self.assert_error_code(data, "cut_without_body")

    def test_frame_axes_must_be_orthogonal(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["sketch_plane"]["frame"]["x_axis"] = [0.6, 0.0, 0.8]
        self.assert_error_code(data, "frame_not_orthogonal")

    def test_origin_must_lie_on_named_origin_plane(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["sketch_plane"]["frame"]["origin"] = [0.0, 0.0, 2.0]
        self.assert_error_code(data, "origin_not_on_reference_plane")

    def test_operation_cap_frame_normal_must_follow_parent_extrude(self):
        data = copy.deepcopy(self.box_hole)
        frame = data["operations"][2]["sketch_plane"]["frame"]
        frame["normal"] = [1.0, 0.0, 0.0]
        frame["x_axis"] = [0.0, 1.0, 0.0]
        data["operations"][3]["direction"] = [-1.0, 0.0, 0.0]
        self.assert_error_code(data, "operation_cap_frame_mismatch")

    def test_operation_cap_frame_origin_must_lie_on_cap(self):
        data = copy.deepcopy(self.box_hole)
        data["operations"][2]["sketch_plane"]["frame"]["origin"] = [0.0, 0.0, 19.0]
        self.assert_error_code(data, "origin_not_on_reference_plane")

    def test_operation_cap_offset_is_zero_only_in_v0_1(self):
        data = copy.deepcopy(self.box_hole)
        reference = data["operations"][2]["sketch_plane"]["semantic_reference"]
        reference["offset_mm"] = 1.0
        self.assert_error_code(data, "unsupported_operation_cap_offset")

    def test_line_loop_must_close(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["loops"][0]["primitives"][-1]["end"] = [1.0, 0.0]
        self.assert_error_code(data, "open_loop")

    def test_absolute_frame_requires_explicit_correction(self):
        data = copy.deepcopy(self.box)
        data["operations"][0]["sketch_plane"]["semantic_reference"] = {
            "type": "absolute_frame",
            "correction_id": "correction_missing",
        }
        self.assert_error_code(data, "absolute_fallback_not_authorized")

    def test_absolute_fallback_rejects_incomplete_correction_audit(self):
        data = copy.deepcopy(self.box)
        data["replay_mode"] = "absolute_fallback"
        data["operations"][0]["sketch_plane"]["semantic_reference"] = {
            "type": "absolute_frame",
            "correction_id": "correction_001",
        }
        data["corrections"] = [
            {
                "correction_id": "correction_001",
                "operation_id": "sketch_base",
                "reason": "missing required audit fields",
            }
        ]
        self.assert_error_code(data, "invalid_correction_record")

    def test_add_is_not_claimed_as_supported_in_v0_1(self):
        data = copy.deepcopy(self.box)
        data["operations"][1]["boolean_type"] = "add"
        self.assert_error_code(data, "unsupported_boolean_type")


if __name__ == "__main__":
    unittest.main()
