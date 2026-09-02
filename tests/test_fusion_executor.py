import importlib.util
import json
import math
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FusionExecutorArtifactTests(unittest.TestCase):
    def test_gate1_executor_artifacts_exist(self):
        required = [
            PROJECT_ROOT / "config" / "gate1_replay_request.json",
            PROJECT_ROOT / "shared" / "frame_math.py",
            PROJECT_ROOT / "fusion_scripts" / "Gate1SequenceReplay" / "Gate1SequenceReplay.py",
            PROJECT_ROOT / "fusion_scripts" / "Gate1SequenceReplay" / "Gate1SequenceReplay.manifest",
            PROJECT_ROOT / "sequences" / "known" / "box_xz.json",
            PROJECT_ROOT / "sequences" / "known" / "box_yz.json",
            PROJECT_ROOT / "sequences" / "known" / "box_rx30.json",
            PROJECT_ROOT / "sequences" / "known" / "box_ry45.json",
            PROJECT_ROOT / "sequences" / "known" / "cylinder_xy.json",
        ]
        missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
        self.assertEqual(missing, [], f"missing Fusion executor artifacts: {missing}")


class FrameMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame_math = load_module("frame_math", PROJECT_ROOT / "shared" / "frame_math.py")
        cls.validator = load_module(
            "sequence_validator", PROJECT_ROOT / "shared" / "sequence_validator.py"
        )

    def assert_world_point(self, frame, point_2d, expected):
        try:
            actual = self.frame_math.world_point(frame, point_2d)
        except NotImplementedError:
            self.fail("frame_math.world_point is not implemented")
        self.assertEqual(len(actual), 3)
        for observed, target in zip(actual, expected):
            self.assertAlmostEqual(observed, target, places=10)

    def test_xy_frame_maps_local_coordinates_to_world(self):
        frame = {"origin": [0, 0, 0], "normal": [0, 0, 1], "x_axis": [1, 0, 0]}
        self.assert_world_point(frame, [50, 35], [50, 35, 0])

    def test_xz_frame_uses_right_handed_negative_z_local_y(self):
        frame = {"origin": [0, 0, 0], "normal": [0, 1, 0], "x_axis": [1, 0, 0]}
        self.assert_world_point(frame, [50, 35], [50, 0, -35])

    def test_yz_frame_maps_local_coordinates_to_world(self):
        frame = {"origin": [0, 0, 0], "normal": [1, 0, 0], "x_axis": [0, 1, 0]}
        self.assert_world_point(frame, [50, 35], [0, 50, 35])

    def test_rx30_frame_matches_fixed_rotation(self):
        frame = {
            "origin": [0, 0, 0],
            "normal": [0, -0.5, 0.8660254037844386],
            "x_axis": [1, 0, 0],
        }
        self.assert_world_point(frame, [0, 2], [0, 1.7320508075688772, 1])

    def test_ry45_frame_matches_fixed_rotation(self):
        root = 0.7071067811865476
        frame = {
            "origin": [0, 0, 0],
            "normal": [root, 0, root],
            "x_axis": [root, 0, -root],
        }
        self.assert_world_point(frame, [2, 3], [2 * root, 3, -2 * root])

    def test_parallel_alignment_error_accepts_either_normal_orientation(self):
        alignment_error = self.frame_math.parallel_alignment_error
        self.assertAlmostEqual(alignment_error((0, 0, 1), (0, 0, 1)), 0.0)
        self.assertAlmostEqual(alignment_error((0, 0, 1), (0, 0, -1)), 0.0)
        self.assertAlmostEqual(alignment_error((0, 0, 1), (0, 1, 0)), math.pi / 2)

    def test_all_new_executor_sequence_fixtures_pass_shared_validation(self):
        for name in ("box_xz.json", "box_yz.json", "box_rx30.json", "box_ry45.json", "cylinder_xy.json"):
            with self.subTest(name=name):
                data = json.loads(
                    (PROJECT_ROOT / "sequences" / "known" / name).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    self.validator.validate_sequence(data), {"valid": True, "errors": []}
                )


class FusionExecutorStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script_path = (
            PROJECT_ROOT
            / "fusion_scripts"
            / "Gate1SequenceReplay"
            / "Gate1SequenceReplay.py"
        )
        cls.source = cls.script_path.read_text(encoding="utf-8")

    def test_manifest_matches_fusion_script_contract(self):
        manifest = json.loads(
            self.script_path.with_suffix(".manifest").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["autodeskProduct"], "Fusion")
        self.assertEqual(manifest["type"], "script")
        self.assertIn("windows", manifest["supportedOS"])

    def test_executor_contains_required_gate1_api_contract(self):
        required_tokens = [
            "validate_sequence",
            "app.documents.add",
            "modelToSketchSpace",
            "sketchToModelSpace",
            "setByAngle",
            "createFusionArchiveExportOptions",
            "createSTEPExportOptions",
            "NewBodyFeatureOperation",
            "world_frame_max_error_mm",
            "parallel_alignment_error",
            "plane_offset_mm",
            "unsupported_operation_combination",
            "ThroughAllExtentDefinition.create",
            "CutFeatureOperation",
            "setOneSideExtent",
            "semantic_reference_failed",
            "boolean_no_intersection",
            '"replay_mode": sequence["replay_mode"]',
            "profileLoops",
        ]
        missing = [token for token in required_tokens if token not in self.source]
        self.assertEqual(missing, [], f"Fusion executor is missing required contracts: {missing}")

    def test_executor_does_not_introduce_external_python_dependencies(self):
        forbidden = ["jsonschema", "requests", "cadquery", "numpy", "scipy"]
        present = [name for name in forbidden if name in self.source]
        self.assertEqual(present, [])

    def test_replay_request_targets_a_known_fixture_without_overwrite_flag(self):
        request = json.loads(
            (PROJECT_ROOT / "config" / "gate1_replay_request.json").read_text(encoding="utf-8")
        )
        self.assertEqual(request["request_version"], "gate1-replay-0.1")
        sequence_path = PROJECT_ROOT / request["sequence_path"]
        self.assertEqual(sequence_path.parent, PROJECT_ROOT / "sequences" / "known")
        self.assertTrue(sequence_path.is_file())
        self.assertRegex(request["run_id"], r"_run\d{2}$")
        self.assertNotIn("overwrite", request)


class FusionExecutorSemanticReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adsk = types.ModuleType("adsk")
        core = types.ModuleType("adsk.core")
        fusion = types.ModuleType("adsk.fusion")
        adsk.core = core
        adsk.fusion = fusion
        with patch.dict(
            sys.modules,
            {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion},
        ):
            cls.executor = load_module(
                "gate1_sequence_replay",
                PROJECT_ROOT
                / "fusion_scripts"
                / "Gate1SequenceReplay"
                / "Gate1SequenceReplay.py",
            )

    def test_missing_parent_feature_returns_semantic_reference_failed(self):
        reference = {
            "type": "operation_cap",
            "operation_id": "extrude_base",
            "role": "positive_end_cap",
            "offset_mm": 0,
        }
        with self.assertRaises(self.executor.ReplayError) as raised:
            self.executor._resolve_operation_cap(reference, {})
        self.assertEqual(raised.exception.code, "semantic_reference_failed")

    def test_profile_resolution_chooses_declared_single_loop_region(self):
        class Collection:
            def __init__(self, items):
                self.items = items
                self.count = len(items)

            def item(self, index):
                return self.items[index]

        class ProfileLoop:
            def __init__(self, curve_count):
                self.isOuter = True
                self.profileCurves = Collection([object()] * curve_count)

        class Profile:
            def __init__(self, curve_counts):
                self.profileLoops = Collection(
                    [ProfileLoop(curve_count) for curve_count in curve_counts]
                )

        outer_face_region = Profile([4, 1])
        circle_interior = Profile([1])
        profiles = Collection([outer_face_region, circle_interior])
        selected = self.executor._select_profile(profiles, expected_curve_count=1)
        self.assertIs(selected, circle_interior)


if __name__ == "__main__":
    unittest.main()
