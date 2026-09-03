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
            "Plane.create",
            "setByPlane",
            "documents.add",
            "document.close(False)",
            "replay_log.json",
            "batch_replay_log.json",
            "_run_sequence",
        ):
            self.assertIn(token, source)

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

    def test_absolute_frame_plane_uses_declared_origin_and_normal(self):
        gate2 = load_with_fake_adsk("gate2_adapter_absolute_plane", self.gate2_path)

        class Point3D:
            @staticmethod
            def create(x, y, z):
                return (x, y, z)

        class Vector3D:
            @staticmethod
            def create(x, y, z):
                return (x, y, z)

        class Plane:
            @staticmethod
            def create(origin, normal):
                return {"origin": origin, "normal": normal}

        class PlaneInput:
            def __init__(self):
                self.geometry = None

            def setByPlane(self, geometry):
                self.geometry = geometry
                return True

        class ConstructionPlanes:
            def __init__(self):
                self.plane_input = PlaneInput()

            def createInput(self):
                return self.plane_input

            def add(self, plane_input):
                return plane_input.geometry

        class Units:
            internalUnits = "cm"

            @staticmethod
            def convert(value, source, target):
                return value / 10.0

        gate2.adsk.core.Point3D = Point3D
        gate2.adsk.core.Vector3D = Vector3D
        gate2.adsk.core.Plane = Plane
        component = types.SimpleNamespace(constructionPlanes=ConstructionPlanes())
        frame = {"origin": [10, -20, 30], "normal": [0, 0, -1]}
        plane = gate2._absolute_frame_plane(component, frame, Units())
        self.assertEqual(plane["origin"], (1.0, -2.0, 3.0))
        self.assertEqual(plane["normal"], (0.0, 0.0, -1.0))

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


if __name__ == "__main__":
    unittest.main()
