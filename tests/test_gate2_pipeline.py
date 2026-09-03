import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import gate2_pipeline
import result_package


class Gate2AnalysisPipelineTests(unittest.TestCase):
    @staticmethod
    def protocol():
        return {
            "protocol_schema": "gate2-validation-0.1",
            "frozen": True,
            "hard_conditions": {
                "volume_absolute_tolerance_mm3": 1e-6,
                "volume_relative_tolerance": 1e-9,
                "bbox_coordinate_tolerance_mm": 1e-6,
            },
            "surface": {"mode": "diagnostic_only"},
            "sampling": {"total_budget": 512, "minimum_per_face": 16},
        }

    @staticmethod
    def case(case_id):
        return {
            "case_id": case_id,
            "split": "development",
            "family": "single_extrusion",
            "source": "test",
            "units": "mm",
            "output_step": f"benchmarks/inputs/development/{case_id}.step",
        }

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        inputs = self.root / "benchmarks" / "inputs" / "development"
        inputs.mkdir(parents=True)
        shutil.copyfile(
            PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-S04.step",
            inputs / "D-S04.step",
        )
        (inputs / "D-S02.step").write_text("not a STEP file", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_debug_run_refuses_overwrite(self):
        gate2_pipeline.create_debug_run(self.root, "pipeline-debug", ["D-S04"])
        with self.assertRaisesRegex(result_package.ResultPackageError, "run_exists"):
            gate2_pipeline.create_debug_run(self.root, "pipeline-debug", ["D-S04"])

    def test_replay_request_is_project_relative_nonoverwriting_and_runs_d_s04_first(self):
        run_dir = self.root / "benchmark_results" / "formal-run"
        run_dir.mkdir(parents=True)
        output = self.root / "config" / "gate2_replay_request.json"
        case_ids = [f"D-S{index:02d}" for index in range(1, 11)]
        gate2_pipeline.write_replay_request(
            self.root, run_dir, "formal-run", case_ids, output
        )
        request = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(request["case_ids"][0], "D-S04")
        self.assertEqual(set(request["case_ids"]), set(case_ids))
        self.assertEqual(request["run_relative_path"], "benchmark_results/formal-run")
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            gate2_pipeline.write_replay_request(
                self.root, run_dir, "formal-run", case_ids, output
            )

    def test_case_failure_is_isolated_and_valid_case_stays_pending_fusion(self):
        run_dir = gate2_pipeline.create_debug_run(
            self.root, "pipeline-isolation", ["D-S02", "D-S04"]
        )
        summary = gate2_pipeline.run_analysis_cases(
            self.root,
            run_dir,
            "pipeline-isolation",
            [self.case("D-S02"), self.case("D-S04")],
            self.protocol(),
        )

        self.assertEqual(summary["failed_case_ids"], ["D-S02"])
        self.assertEqual(summary["awaiting_fusion_case_ids"], ["D-S04"])

        failed_dir = run_dir / "cases" / "D-S02"
        failed = json.loads((failed_dir / "final_status.json").read_text(encoding="utf-8"))
        self.assertEqual(failed["terminal_status"], "failed")
        self.assertEqual(failed["failure_stage"], "brep_inspection")
        self.assertTrue(failed["failure_code"].startswith("step_import_failed"))
        self.assertTrue(result_package.audit_case_package(failed_dir)["complete"])

        valid_dir = run_dir / "cases" / "D-S04"
        metadata = json.loads(
            (valid_dir / "metadata" / "input_metadata.json").read_text(encoding="utf-8")
        )
        brep_summary = json.loads(
            (valid_dir / "analysis" / "brep_summary.json").read_text(encoding="utf-8")
        )
        inference_log = json.loads(
            (valid_dir / "analysis" / "inference_log.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["run_id"], "pipeline-isolation")
        self.assertEqual(metadata["relative_path"], "benchmarks/inputs/development/D-S04.step")
        self.assertNotIn("run_id", brep_summary)
        self.assertEqual(inference_log["status"], "awaiting_fusion")
        self.assertTrue((valid_dir / "analysis" / "candidates.json").is_file())
        self.assertTrue((valid_dir / "sequence" / "inferred_sequence.json").is_file())
        self.assertFalse((valid_dir / "final_status.json").exists())

    def prepared_replay_case(self, run_id):
        run_dir = gate2_pipeline.create_debug_run(self.root, run_id, ["D-S04"])
        gate2_pipeline.run_analysis_cases(
            self.root, run_dir, run_id, [self.case("D-S04")], self.protocol()
        )
        return run_dir / "cases" / "D-S04"

    def test_successful_fusion_replay_is_validated_before_automatic_success(self):
        case_dir = self.prepared_replay_case("finalize-success")
        replay_dir = case_dir / "replay"
        replay_dir.mkdir(parents=True)
        shutil.copyfile(
            PROJECT_ROOT
            / "logs"
            / "gate2"
            / "day5"
            / "D-S04"
            / "candidate_rebuilds"
            / "extrusion-face-006-face-007.step",
            replay_dir / "replay.step",
        )
        (replay_dir / "replay.f3d").write_bytes(b"fusion archive evidence")
        self._write_json(replay_dir / "replay_log.json", {"status": "success"})

        status = gate2_pipeline.finalize_replay_case(
            self.root, case_dir, self.protocol()
        )
        metrics = json.loads(
            (case_dir / "validation" / "validation_metrics.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["terminal_status"], "automatic_success")
        self.assertTrue(metrics["geometry_pass"])
        self.assertTrue(result_package.audit_case_package(case_dir)["complete"])

    def test_failed_fusion_replay_gets_structured_terminal_failure_without_validation(self):
        case_dir = self.prepared_replay_case("finalize-failure")
        self._write_json(
            case_dir / "replay" / "replay_log.json",
            {
                "status": "failure",
                "error_code": "construction_plane_failed",
                "error": "Fusion rejected the inferred plane",
            },
        )
        status = gate2_pipeline.finalize_replay_case(
            self.root, case_dir, self.protocol()
        )
        self.assertEqual(status["terminal_status"], "failed")
        self.assertEqual(status["failure_stage"], "fusion_replay")
        self.assertEqual(status["failure_code"], "construction_plane_failed")
        self.assertFalse((case_dir / "validation" / "validation_metrics.json").exists())
        self.assertTrue(result_package.audit_case_package(case_dir)["complete"])

    def test_run_finalization_requires_complete_batch_log_before_writing_status(self):
        case_dir = self.prepared_replay_case("incomplete-batch")
        run_dir = case_dir.parents[1]
        with self.assertRaisesRegex(result_package.ResultPackageError, "batch_replay_incomplete"):
            gate2_pipeline.finalize_replay_run(self.root, run_dir, self.protocol())
        self.assertFalse((case_dir / "final_status.json").exists())

    @staticmethod
    def _write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class Gate2FormalRunPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "benchmarks").mkdir()
        (self.root / "config").mkdir()
        shutil.copyfile(
            PROJECT_ROOT / "benchmarks" / "case_matrix.json",
            self.root / "benchmarks" / "case_matrix.json",
        )
        shutil.copyfile(
            PROJECT_ROOT / "benchmarks" / "manifest.json",
            self.root / "benchmarks" / "manifest.json",
        )
        shutil.copyfile(
            PROJECT_ROOT / "config" / "gate2_validation_protocol.json",
            self.root / "config" / "gate2_validation_protocol.json",
        )
        shutil.copyfile(
            PROJECT_ROOT / "config" / "gate2_validation_protocol.json.sha256",
            self.root / "config" / "gate2_validation_protocol.json.sha256",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_formal_run_uses_frozen_hashes_and_exact_case_selection(self):
        run_dir, cases, protocol = gate2_pipeline.create_formal_run(
            self.root,
            "formal-test",
            git_commit="a" * 40,
            git_dirty_at_start=False,
            environment={"external_python": {"version": "3.11"}},
        )
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([case["case_id"] for case in cases], [f"D-S{i:02d}" for i in range(1, 11)])
        self.assertTrue(protocol["frozen"])
        self.assertEqual(
            manifest["validation_protocol_sha256"],
            (self.root / "config" / "gate2_validation_protocol.json.sha256")
            .read_text()
            .strip(),
        )
        self.assertFalse(manifest["git_dirty_at_start"])

    def test_formal_run_refuses_dirty_start_before_creating_directory(self):
        with self.assertRaisesRegex(result_package.ResultPackageError, "formal_run_requires_clean_git"):
            gate2_pipeline.create_formal_run(
                self.root,
                "dirty-run",
                git_commit="b" * 40,
                git_dirty_at_start=True,
                environment={},
            )
        self.assertFalse((self.root / "benchmark_results" / "dirty-run").exists())

    def test_environment_snapshot_records_external_stack_and_pending_fusion_capture(self):
        environment = gate2_pipeline.capture_environment()
        self.assertRegex(environment["external_python"]["version"], r"^3\.11\.")
        self.assertTrue(environment["external_python"]["executable"])
        for package in ("cadquery", "ocp", "numpy", "scipy"):
            self.assertTrue(environment["packages"][package])
        self.assertEqual(environment["fusion"]["status"], "pending_runtime_capture")


if __name__ == "__main__":
    unittest.main()
