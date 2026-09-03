import copy
import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "shared" / "sequence_validator.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("sequence_validator_v02", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SequenceSchemaV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        cls.box = json.loads(
            (PROJECT_ROOT / "sequences" / "known" / "box.json").read_text(encoding="utf-8")
        )
        cls.box_hole = json.loads(
            (PROJECT_ROOT / "sequences" / "known" / "box_hole.json").read_text(encoding="utf-8")
        )
        cls.rotated = json.loads(
            (PROJECT_ROOT / "sequences" / "known" / "box_rx30.json").read_text(
                encoding="utf-8"
            )
        )

    def named_root(self):
        data = copy.deepcopy(self.box)
        data["schema_version"] = "cadseq-0.2"
        data["replay_mode"] = "automatic"
        data["operations"][0]["sketch_plane"]["frame_source"] = "origin_named"
        return data

    def inferred_root(self):
        data = copy.deepcopy(self.rotated)
        data["schema_version"] = "cadseq-0.2"
        data["replay_mode"] = "automatic"
        data["corrections"] = []
        plane = data["operations"][0]["sketch_plane"]
        plane["semantic_reference"] = {"type": "absolute_frame"}
        plane["frame_source"] = "inferred_brep"
        plane["frame_provenance"] = {
            "source_step_sha256": "a" * 64,
            "base_face_id": "face-000",
            "source_face_outward_normal": [0.0, 0.5, -0.8660254037844386],
        }
        return data

    def assert_error(self, data, code):
        result = self.validator.validate_sequence(data)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], code)

    def test_origin_named_root_is_valid_only_in_automatic_mode(self):
        data = self.named_root()
        self.assertEqual(self.validator.validate_sequence(data), {"valid": True, "errors": []})
        data["replay_mode"] = "absolute_fallback"
        self.assert_error(data, "frame_source_replay_mode_mismatch")

    def test_inferred_brep_absolute_frame_is_valid_without_correction(self):
        data = self.inferred_root()
        self.assertEqual(self.validator.validate_sequence(data), {"valid": True, "errors": []})
        self.assertEqual(data["corrections"], [])

    def test_inferred_brep_requires_complete_provenance(self):
        data = self.inferred_root()
        del data["operations"][0]["sketch_plane"]["frame_provenance"]["base_face_id"]
        self.assert_error(data, "invalid_frame_provenance")

    def test_inferred_brep_frame_normal_must_equal_extrusion_direction(self):
        data = self.inferred_root()
        data["operations"][1]["direction"] = [0.0, 0.5, -0.8660254037844386]
        self.assert_error(data, "inferred_direction_mismatch")

    def test_manual_correction_absolute_frame_requires_fallback_and_audit(self):
        data = copy.deepcopy(self.rotated)
        data["schema_version"] = "cadseq-0.2"
        data["operations"][0]["sketch_plane"]["frame_source"] = "manual_correction"
        self.assertEqual(self.validator.validate_sequence(data), {"valid": True, "errors": []})
        data["corrections"] = []
        self.assert_error(data, "absolute_fallback_not_authorized")

    def test_operation_cap_has_no_frame_source_exemption(self):
        data = copy.deepcopy(self.box_hole)
        data["schema_version"] = "cadseq-0.2"
        data["replay_mode"] = "automatic"
        data["operations"][0]["sketch_plane"]["frame_source"] = "origin_named"
        self.assertNotIn("frame_source", data["operations"][2]["sketch_plane"])
        self.assertEqual(self.validator.validate_sequence(data), {"valid": True, "errors": []})
        data["operations"][2]["sketch_plane"]["frame_source"] = "origin_named"
        self.assert_error(data, "operation_cap_frame_source_forbidden")

    def test_frame_source_and_reference_type_cannot_be_mixed(self):
        data = self.named_root()
        data["operations"][0]["sketch_plane"]["frame_source"] = "inferred_brep"
        self.assert_error(data, "frame_source_reference_mismatch")

    def test_v02_schema_document_exists_and_records_frozen_frame_sources(self):
        path = PROJECT_ROOT / "docs" / "sequence_schema_v0.2.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        for required in ("origin_named", "inferred_brep", "manual_correction", "operation_cap"):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
