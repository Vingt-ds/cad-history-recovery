import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import result_package


class Gate2SelectionTests(unittest.TestCase):
    def test_selector_derives_only_frozen_development_single_extrusions(self):
        cases = result_package.load_gate2_cases(PROJECT_ROOT)
        self.assertEqual([case["case_id"] for case in cases], [f"D-S{i:02d}" for i in range(1, 11)])
        for case in cases:
            self.assertEqual(case["split"], "development")
            self.assertEqual(case["family"], "single_extrusion")
            self.assertNotIn("expected_scope", case)
            self.assertNotIn("expected_behavior", case)

    def test_input_guard_rejects_held_out_path(self):
        path = PROJECT_ROOT / "benchmarks" / "inputs" / "held_out" / "T-S01.step"
        with self.assertRaisesRegex(result_package.ResultPackageError, "held_out_input_forbidden"):
            result_package.validate_development_input(PROJECT_ROOT, path)

    def test_input_guard_rejects_path_outside_frozen_inputs(self):
        with self.assertRaisesRegex(result_package.ResultPackageError, "input_path_outside_benchmark"):
            result_package.validate_development_input(PROJECT_ROOT, PROJECT_ROOT / "models" / "manual_box_hole.step")


class RunLayoutTests(unittest.TestCase):
    def test_create_run_writes_start_snapshot_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "benchmark_results").mkdir()
            run = result_package.create_run(
                root,
                run_id="gate2-dev-20260903T000000Z-deadbee",
                git_commit="deadbeef",
                git_dirty_at_start=False,
                matrix_sha256="a" * 64,
                benchmark_manifest_sha256="b" * 64,
                case_ids=["D-S01"],
                environment={"python": "3.11"},
            )
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["git_dirty_at_start"])
            self.assertEqual(manifest["case_ids"], ["D-S01"])
            self.assertEqual(manifest["environment_ref"], "environment.json")
            with self.assertRaisesRegex(result_package.ResultPackageError, "run_exists"):
                result_package.create_run(
                    root,
                    run_id="gate2-dev-20260903T000000Z-deadbee",
                    git_commit="deadbeef",
                    git_dirty_at_start=False,
                    matrix_sha256="a" * 64,
                    benchmark_manifest_sha256="b" * 64,
                    case_ids=["D-S01"],
                    environment={"python": "3.11"},
                )

    def test_create_run_rejects_unsafe_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(result_package.ResultPackageError, "invalid_run_id"):
                result_package.create_run(
                    Path(directory), "../escape", "abc", False, "a" * 64, "b" * 64, ["D-S01"], {}
                )


class CompletenessAuditTests(unittest.TestCase):
    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_automatic_success_requires_all_success_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            self._write_json(case / "metadata" / "input_metadata.json", {"run_id": "r"})
            self._write_json(case / "analysis" / "brep_summary.json", {"solid_count": 1})
            self._write_json(case / "analysis" / "inference_log.json", {"status": "success"})
            self._write_json(case / "final_status.json", {"terminal_status": "automatic_success"})
            audit = result_package.audit_case_package(case)
            self.assertFalse(audit["complete"])
            self.assertIn("analysis/candidates.json", audit["missing"])
            self.assertIn("replay/replay.f3d", audit["missing"])
            self.assertIn("validation/validation_metrics.json", audit["missing"])

    def test_failed_case_requires_structured_failure_but_not_replay_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            self._write_json(case / "metadata" / "input_metadata.json", {"run_id": "r"})
            self._write_json(case / "analysis" / "brep_summary.json", {"solid_count": 1})
            self._write_json(case / "analysis" / "inference_log.json", {"status": "failure"})
            self._write_json(
                case / "final_status.json",
                {
                    "terminal_status": "failed",
                    "failure_stage": "candidate_generation",
                    "failure_code": "no_extrusion_candidate",
                    "error_summary": "no candidate passed hard checks",
                    "not_applicable_reason": "Fusion replay was not attempted",
                },
            )
            audit = result_package.audit_case_package(case)
            self.assertTrue(audit["complete"])
            self.assertEqual(audit["missing"], [])

    def test_failed_case_without_failure_code_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            self._write_json(case / "metadata" / "input_metadata.json", {"run_id": "r"})
            self._write_json(case / "analysis" / "inference_log.json", {"status": "failure"})
            self._write_json(case / "final_status.json", {"terminal_status": "failed"})
            audit = result_package.audit_case_package(case)
            self.assertFalse(audit["complete"])
            self.assertIn("final_status.failure_code", audit["invalid"])


if __name__ == "__main__":
    unittest.main()
