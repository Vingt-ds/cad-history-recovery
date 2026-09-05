import ast
import hashlib
import importlib.metadata
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

from gate0_common import ConfigError, load_gate0_config, sha256_file
import cadquery_smoke
from verify_gate0 import verify_project


VALID_CONFIG = {
    "schema_version": "gate0-0.1",
    "units": "mm",
    "model": {
        "type": "box",
        "width": 60.0,
        "depth": 40.0,
        "height": 20.0,
    },
}


class ConfigTests(unittest.TestCase):
    def write_config(self, root: Path, data: dict) -> Path:
        path = root / "gate0_box.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_loads_valid_mm_box_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(Path(directory), VALID_CONFIG)
            config = load_gate0_config(path)
            self.assertEqual(config["model"]["width"], 60.0)

    def test_rejects_non_mm_units(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = dict(VALID_CONFIG)
            invalid["units"] = "cm"
            path = self.write_config(Path(directory), invalid)
            with self.assertRaisesRegex(ConfigError, "units"):
                load_gate0_config(path)

    def test_rejects_non_positive_dimension(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = json.loads(json.dumps(VALID_CONFIG))
            invalid["model"]["height"] = 0
            path = self.write_config(Path(directory), invalid)
            with self.assertRaisesRegex(ConfigError, "height"):
                load_gate0_config(path)

    def test_sha256_matches_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.bin"
            payload = b"gate0-shared-json"
            path.write_bytes(payload)
            self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())

    def test_gate0_shared_config_is_git_binary_to_preserve_frozen_hash(self):
        attributes = (PROJECT_ROOT / ".gitattributes").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertIn("config/gate0_box.json binary", attributes)

    def test_fusion_manifest_matches_installed_script_contract(self):
        manifest_path = (
            PROJECT_ROOT
            / "fusion_scripts"
            / "Gate0BoxExport"
            / "Gate0BoxExport.manifest"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["autodeskProduct"], "Fusion")
        self.assertEqual(manifest["type"], "script")
        self.assertIsInstance(manifest["description"], dict)
        self.assertIn("", manifest["description"])
        self.assertIn("windows", manifest["supportedOS"])

    def test_fusion_mm_conversion_uses_convert_api(self):
        script_path = (
            PROJECT_ROOT
            / "fusion_scripts"
            / "Gate0BoxExport"
            / "Gate0BoxExport.py"
        )
        tree = ast.parse(script_path.read_text(encoding="utf-8"))
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_mm_to_internal"
        ]
        self.assertEqual(len(functions), 1, "Fusion script must define _mm_to_internal")
        function = functions[0]
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(script_path), "exec"), namespace)

        class FakeUnitsManager:
            internalUnits = "internalUnits"

            def convert(self, value, input_units, output_units):
                self.call = (value, input_units, output_units)
                return 6.0

        units = FakeUnitsManager()
        result = namespace["_mm_to_internal"](units, 60.0)
        self.assertEqual(result, 6.0)
        self.assertEqual(units.call, (60.0, "mm", "internalUnits"))

    def test_distribution_version_falls_back_to_conda_ocp_name(self):
        resolver = getattr(cadquery_smoke, "distribution_version", None)
        self.assertTrue(callable(resolver), "cadquery_smoke must provide distribution_version")

        def fake_version(name):
            if name == "cadquery-ocp":
                raise importlib.metadata.PackageNotFoundError(name)
            if name == "ocp":
                return "7.8.1.1"
            raise AssertionError(f"unexpected package name: {name}")

        with patch("cadquery_smoke.importlib.metadata.version", side_effect=fake_version):
            self.assertEqual(resolver("cadquery-ocp", "ocp"), "7.8.1.1")

    def test_ocp_version_falls_back_to_module_attribute(self):
        resolver = getattr(cadquery_smoke, "ocp_version", None)
        self.assertTrue(callable(resolver), "cadquery_smoke must provide ocp_version")
        missing = importlib.metadata.PackageNotFoundError("ocp")
        fake_ocp = types.SimpleNamespace(__version__="7.9.3.1")
        with patch("cadquery_smoke.importlib.metadata.version", side_effect=missing):
            with patch.dict(sys.modules, {"OCP": fake_ocp}):
                self.assertEqual(resolver(), "7.9.3.1")


class VerifierTests(unittest.TestCase):
    def make_complete_project(self, root: Path) -> str:
        config_path = root / "config" / "gate0_box.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps(VALID_CONFIG), encoding="utf-8")
        config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

        artifact_paths = [
            "models/manual_box_hole.f3d",
            "models/manual_box_hole.step",
            "models/manual_box_hole_reimported.f3d",
            "models/fusion_script_box_run01.step",
            "models/fusion_script_box_run02.step",
            "models/cadquery_box.step",
            "evidence/01_original_timeline.png",
            "evidence/02_reimported_timeline.png",
            "evidence/export_settings.md",
            "docs/gate0_reuse_audit.md",
            "environment/environment.yml",
            "environment/pip-freeze.txt",
        ]
        for relative in artifact_paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"non-empty")

        (root / "evidence" / "export_settings.md").write_text(
            "Fusion version: 2704.1.53\nOriginal timeline visual review: PASS\n"
            "Reimported timeline visual review: PASS\nSTEP export format: STEP\n",
            encoding="utf-8",
        )
        (root / "environment" / "environment.yml").write_text(
            "name: cadseq\ndependencies:\n  - python=3.11\n  - pip\n",
            encoding="utf-8",
        )
        (root / "environment" / "pip-freeze.txt").write_text(
            "cadquery==2.8.0\ncadquery-ocp==7.8.1.1.post1\n",
            encoding="utf-8",
        )

        logs = root / "logs"
        logs.mkdir(parents=True)
        for run_id in ("run01", "run02"):
            (logs / f"fusion_{run_id}.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": run_id,
                        "json_sha256": config_hash,
                        "fusion_version": "2704.1.53",
                        "python_version": "3.x",
                        "body_count": 1,
                        "face_count": 6,
                        "output_path": f"models/fusion_script_box_{run_id}.step",
                    }
                ),
                encoding="utf-8",
            )

        (logs / "external_python.json").write_text(
            json.dumps(
                {
                    "status": "success",
                    "json_sha256": config_hash,
                    "versions": {
                        "python": "3.11.11",
                        "cadquery": "2.8.0",
                        "cadquery_ocp": "7.x",
                    },
                    "checks": {
                        "cadquery_box": {"solid_count": 1, "face_count": 6, "edge_count": 12, "valid": True},
                        "fusion_run01": {"solid_count": 1, "face_count": 6, "valid": True},
                        "fusion_run02": {"solid_count": 1, "face_count": 6, "valid": True},
                        "manual_box_hole": {"solid_count": 1, "valid": True},
                    },
                }
            ),
            encoding="utf-8",
        )
        return config_hash

    def test_complete_project_passes_automated_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            checks = verify_project(root)
            self.assertTrue(all(check.passed for check in checks), [check.detail for check in checks if not check.passed])

    def test_missing_required_artifact_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            (root / "models" / "manual_box_hole.step").unlink()
            checks = verify_project(root)
            failed_names = {check.name for check in checks if not check.passed}
            self.assertIn("artifact:models/manual_box_hole.step", failed_names)

    def test_mismatched_fusion_hash_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            log_path = root / "logs" / "fusion_run02.json"
            data = json.loads(log_path.read_text(encoding="utf-8"))
            data["json_sha256"] = "0" * 64
            log_path.write_text(json.dumps(data), encoding="utf-8")
            checks = verify_project(root)
            failed_names = {check.name for check in checks if not check.passed}
            self.assertIn("shared_json_hash", failed_names)

    def test_pending_manual_review_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            (root / "evidence" / "export_settings.md").write_text(
                "Original timeline visual review: PENDING\n",
                encoding="utf-8",
            )
            checks = verify_project(root)
            failed_names = {check.name for check in checks if not check.passed}
            self.assertIn("manual_evidence_record", failed_names)

    def test_placeholder_environment_record_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            (root / "environment" / "pip-freeze.txt").write_text(
                "PENDING: run pip freeze\n",
                encoding="utf-8",
            )
            checks = verify_project(root)
            failed_names = {check.name for check in checks if not check.passed}
            self.assertIn("environment_record", failed_names)

    def test_real_conda_environment_record_does_not_require_pip_ocp_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_project(root)
            (root / "environment" / "environment.yml").write_text(
                "name: cadseq\nchannels:\n  - conda-forge\ndependencies:\n"
                "  - cadquery=2.8.0\n  - python=3.11\n",
                encoding="utf-8",
            )
            (root / "environment" / "pip-freeze.txt").write_text(
                "cadquery @ file:///conda-build/cadquery/work\n",
                encoding="utf-8",
            )
            checks = verify_project(root)
            environment_check = next(check for check in checks if check.name == "environment_record")
            self.assertTrue(environment_check.passed, environment_check.detail)


if __name__ == "__main__":
    unittest.main()
