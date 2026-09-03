import importlib.util
import inspect
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_with_fake_adsk(name, path):
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    adsk.core = core
    adsk.fusion = fusion
    with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion}):
        return load_module(name, path)


class Gate2FusionAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate1_path = (
            PROJECT_ROOT / "fusion_scripts" / "Gate1SequenceReplay" / "Gate1SequenceReplay.py"
        )
        cls.gate2_path = (
            PROJECT_ROOT / "fusion_scripts" / "Gate2SequenceReplay" / "Gate2SequenceReplay.py"
        )

    def request(self):
        case_ids = ["D-S04"] + [
            f"D-S{index:02d}" for index in range(1, 11) if index != 4
        ]
        return {
            "request_version": "gate2-replay-0.1",
            "run_id": "gate2-formal-test",
            "run_relative_path": "benchmark_results/gate2-formal-test",
            "case_ids": case_ids,
        }

    def test_gate1_core_accepts_optional_plane_resolver_without_changing_default(self):
        gate1 = load_with_fake_adsk("gate1_core_for_gate2", self.gate1_path)
        parameter = inspect.signature(gate1._run_sequence).parameters["plane_resolver"]
        self.assertIsNone(parameter.default)

    def test_gate2_artifacts_and_batch_contract_exist(self):
        self.assertTrue(self.gate2_path.is_file())
        manifest_path = self.gate2_path.with_suffix(".manifest")
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["autodeskProduct"], "Fusion")
        source = self.gate2_path.read_text(encoding="utf-8")
        for token in (
            "gate2_replay_request.json",
            "setByOffset",
            "setByAngle",
            "documents.add",
            "document.close(False)",
            "replay_log.json",
            "batch_replay_log.json",
            "_run_sequence",
        ):
            self.assertIn(token, source)
        self.assertNotIn("setByPlane", source)

    def test_batch_paths_require_exact_cases_nonrectangular_first_and_stay_in_project(self):
        gate2 = load_with_fake_adsk("gate2_adapter_paths", self.gate2_path)
        project_root = os.path.abspath("C:/gate2-project")
        paths = gate2._paths(project_root, self.request())
        self.assertEqual(paths["case_ids"][0], "D-S04")
        self.assertEqual(set(paths["case_ids"]), {f"D-S{index:02d}" for index in range(1, 11)})
        self.assertTrue(paths["run_dir"].startswith(project_root))
        self.assertTrue(paths["cases"]["D-S04"]["f3d"].endswith("replay.f3d"))

    def test_batch_paths_reject_escape_duplicate_or_incomplete_case_set(self):
        gate2 = load_with_fake_adsk("gate2_adapter_invalid_paths", self.gate2_path)
        project_root = os.path.abspath("C:/gate2-project")
        request = self.request()
        request["run_relative_path"] = "../escape"
        with self.assertRaises(gate2.ReplayError):
            gate2._paths(project_root, request)
        request = self.request()
        request["case_ids"][-1] = "D-S04"
        with self.assertRaises(gate2.ReplayError):
            gate2._paths(project_root, request)

    def test_reused_gate1_error_code_is_preserved(self):
        gate2 = load_with_fake_adsk("gate2_adapter_error_code", self.gate2_path)

        class Gate1CoreError(Exception):
            code = "world_frame_error_exceeded"

        self.assertEqual(
            gate2._error_code(Gate1CoreError("frame check failed")),
            "world_frame_error_exceeded",
        )

    def test_axis_aligned_absolute_frame_uses_parametric_offset_plane(self):
        gate2 = load_with_fake_adsk("gate2_adapter_parametric_offset", self.gate2_path)

        class ValueInput:
            @staticmethod
            def createByReal(value):
                return value

        class PlaneInput:
            def setByOffset(self, base_plane, offset):
                self.definition = ("offset", base_plane, offset)
                return True

        class ConstructionPlanes:
            def createInput(self):
                return PlaneInput()

            @staticmethod
            def add(plane_input):
                return plane_input.definition

        class Units:
            internalUnits = "cm"

            @staticmethod
            def convert(value, source, target):
                return value / 10.0

        gate2.adsk.core.ValueInput = ValueInput
        component = types.SimpleNamespace(
            xYConstructionPlane="XY",
            xZConstructionPlane="XZ",
            yZConstructionPlane="YZ",
            constructionPlanes=ConstructionPlanes(),
        )
        frame = {
            "origin": [23.0, 20.0, 32.725388601],
            "normal": [0.0, -1.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
        }

        plane = gate2._absolute_frame_plane(component, frame, Units(), 1e-8)

        self.assertEqual(plane, ("offset", "XZ", 2.0))

    def test_rotated_absolute_frame_uses_parametric_angle_plane(self):
        gate2 = load_with_fake_adsk("gate2_adapter_parametric_angle", self.gate2_path)

        class ValueInput:
            @staticmethod
            def createByReal(value):
                return value

        class PlaneInput:
            def setByAngle(self, axis, angle, base_plane):
                self.definition = ("angle", axis, angle, base_plane)
                return True

        class ConstructionPlanes:
            def createInput(self):
                return PlaneInput()

            @staticmethod
            def add(plane_input):
                return plane_input.definition

        gate2.adsk.core.ValueInput = ValueInput
        component = types.SimpleNamespace(
            xConstructionAxis="X_AXIS",
            xYConstructionPlane="XY",
            xZConstructionPlane="XZ",
            yZConstructionPlane="YZ",
            constructionPlanes=ConstructionPlanes(),
        )
        frame = {
            "origin": [24.0, -4.75, 8.227241336],
            "normal": [0.0, 0.866025403781, 0.500000000007],
            "x_axis": [1.0, 0.0, 0.0],
        }

        plane = gate2._absolute_frame_plane(component, frame, None, 1e-8)

        self.assertEqual(plane[0], "angle")
        self.assertEqual(plane[1], "X_AXIS")
        self.assertAlmostEqual(plane[2], -1.04719755119, places=10)
        self.assertEqual(plane[3], "XY")

    def test_case_outputs_are_never_overwritten(self):
        gate2 = load_with_fake_adsk("gate2_adapter_no_overwrite", self.gate2_path)
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "replay.step"
            existing.write_bytes(b"existing")
            paths = {
                "f3d": str(Path(directory) / "replay.f3d"),
                "step": str(existing),
                "log": str(Path(directory) / "replay_log.json"),
            }
            with self.assertRaisesRegex(gate2.ReplayError, "refusing to overwrite"):
                gate2._assert_outputs_absent(paths)
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_gate1_core_is_loaded_from_current_file_not_stale_module_cache(self):
        gate2 = load_with_fake_adsk("gate2_adapter_core_reload", self.gate2_path)
        with tempfile.TemporaryDirectory() as directory:
            core_dir = Path(directory) / "fusion_scripts" / "Gate1SequenceReplay"
            core_dir.mkdir(parents=True)
            (core_dir / "Gate1SequenceReplay.py").write_text(
                "marker = 'fresh-file'\n", encoding="utf-8"
            )
            stale = types.SimpleNamespace(marker="stale-cache")
            with patch.dict(sys.modules, {"Gate1SequenceReplay": stale}):
                loaded = gate2._load_core(directory)
        self.assertEqual(loaded.marker, "fresh-file")

    def test_gate2_shared_loader_ignores_stale_fusion_module_cache(self):
        gate2 = load_with_fake_adsk("gate2_adapter_shared_reload", self.gate2_path)
        sequence = json.loads(
            (
                PROJECT_ROOT
                / "logs"
                / "gate2"
                / "day5"
                / "D-S04"
                / "sequence"
                / "inferred_sequence.json"
            ).read_text(encoding="utf-8")
        )
        stale_validator = types.ModuleType("sequence_validator")
        stale_validator.validate_sequence = lambda data: {
            "valid": False,
            "errors": [{"code": "invalid_schema_version"}],
        }
        stale_frame_math = types.ModuleType("frame_math")
        stale_frame_math.world_point = lambda frame, point: "stale-world-point"
        stale_frame_math.parallel_alignment_error = lambda left, right: -1.0

        with patch.dict(
            sys.modules,
            {
                "sequence_validator": stale_validator,
                "frame_math": stale_frame_math,
            },
        ):
            validate_sequence, world_point, alignment_error = gate2._load_shared(
                str(PROJECT_ROOT)
            )

        self.assertTrue(validate_sequence(sequence)["valid"])
        self.assertEqual(
            world_point(
                {
                    "origin": [1.0, 2.0, 3.0],
                    "normal": [0.0, 0.0, 1.0],
                    "x_axis": [1.0, 0.0, 0.0],
                },
                [4.0, 5.0],
            ),
            (5.0, 7.0, 3.0),
        )
        self.assertEqual(alignment_error([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]), 0.0)

    def test_replay_case_bypasses_all_stale_modules_before_modeling_v02(self):
        gate2 = load_with_fake_adsk("gate2_adapter_replay_reload", self.gate2_path)
        sequence_path = (
            PROJECT_ROOT
            / "logs"
            / "gate2"
            / "day5"
            / "D-S04"
            / "sequence"
            / "inferred_sequence.json"
        )
        sequence = json.loads(sequence_path.read_text(encoding="utf-8"))
        self.assertEqual(sequence["schema_version"], "cadseq-0.2")

        stale_gate1 = types.ModuleType("Gate1SequenceReplay")
        stale_validator = types.ModuleType("sequence_validator")
        stale_validator.validate_sequence = lambda data: {
            "valid": False,
            "errors": [{"code": "invalid_schema_version"}],
        }
        stale_frame_math = types.ModuleType("frame_math")
        stale_frame_math.world_point = lambda frame, point: "stale-world-point"
        stale_frame_math.parallel_alignment_error = lambda left, right: -1.0

        class ReachedModeling(Exception):
            pass

        class Documents:
            @staticmethod
            def add(document_type):
                raise ReachedModeling

        gate2.adsk.core.DocumentTypes = types.SimpleNamespace(
            FusionDesignDocumentType=object()
        )
        app = types.SimpleNamespace(documents=Documents())

        with tempfile.TemporaryDirectory() as directory:
            replay_dir = Path(directory) / "replay"
            case_paths = {
                "sequence": str(sequence_path),
                "replay_dir": str(replay_dir),
                "f3d": str(replay_dir / "replay.f3d"),
                "step": str(replay_dir / "replay.step"),
                "log": str(replay_dir / "replay_log.json"),
            }
            with patch.dict(
                sys.modules,
                {
                    "adsk": gate2.adsk,
                    "adsk.core": gate2.adsk.core,
                    "adsk.fusion": gate2.adsk.fusion,
                    "Gate1SequenceReplay": stale_gate1,
                    "sequence_validator": stale_validator,
                    "frame_math": stale_frame_math,
                },
            ):
                core = gate2._load_core(str(PROJECT_ROOT))
                with self.assertRaises(ReachedModeling):
                    gate2._replay_case(app, core, "D-S04", case_paths)


if __name__ == "__main__":
    unittest.main()
