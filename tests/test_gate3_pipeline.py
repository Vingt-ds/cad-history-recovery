import json
import hashlib
import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import gate3_pipeline
import candidate_validation
import result_package
import through_hole_reconstruction
import verify_gate3


class Gate3PipelineArtifactTests(unittest.TestCase):
    def test_gate3_pipeline_and_verifier_modules_exist(self):
        self.assertTrue((PROJECT_ROOT / "external" / "gate3_pipeline.py").is_file())
        self.assertTrue((PROJECT_ROOT / "external" / "verify_gate3.py").is_file())

    def test_frozen_gate3_protocol_has_matching_hash(self):
        protocol = PROJECT_ROOT / "config" / "gate3_validation_protocol.json"
        checksum = PROJECT_ROOT / "config" / "gate3_validation_protocol.json.sha256"
        self.assertTrue(protocol.is_file())
        self.assertTrue(checksum.is_file())
        self.assertEqual(
            hashlib.sha256(protocol.read_bytes()).hexdigest(),
            checksum.read_text(encoding="ascii").strip(),
        )
        record = json.loads(protocol.read_text(encoding="utf-8"))
        self.assertTrue(record["frozen"])
        self.assertEqual(record["surface"]["mode"], "diagnostic_only")
        self.assertEqual(
            set(record["feature_conditions"]),
            {
                "radius_tolerance_mm",
                "axis_angular_tolerance_rad",
                "axis_line_offset_tolerance_mm",
                "opening_center_tolerance_mm",
                "span_tolerance_mm",
            },
        )


class Gate3PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "benchmarks" / "inputs" / "development").mkdir(parents=True)
        (self.root / "config").mkdir()
        for relative in (
            "benchmarks/case_matrix.json",
            "benchmarks/manifest.json",
            "config/gate3_validation_protocol.json",
            "config/gate3_validation_protocol.json.sha256",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / relative, destination)
        shutil.copyfile(
            PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-H01.step",
            self.root / "benchmarks" / "inputs" / "development" / "D-H01.step",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_formal_run_uses_only_frozen_development_holes_and_refuses_dirty_start(self):
        with self.assertRaisesRegex(result_package.ResultPackageError, "formal_run_requires_clean_git"):
            gate3_pipeline.create_formal_run(
                self.root, "dirty", "a" * 40, True, {"fusion": {"status": "pending"}}
            )
        self.assertFalse((self.root / "benchmark_results" / "dirty").exists())

        run_dir, cases, protocol = gate3_pipeline.create_formal_run(
            self.root, "formal", "b" * 40, False, {"fusion": {"status": "pending"}}
        )
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([case["case_id"] for case in cases], [f"D-H{i:02d}" for i in range(1, 6)])
        self.assertEqual(manifest["case_ids"], [f"D-H{i:02d}" for i in range(1, 6)])
        self.assertEqual(manifest["manifest_schema"], "gate3-run-manifest-0.1")
        self.assertFalse(manifest["git_dirty_at_start"])
        self.assertTrue(protocol["frozen"])

    def test_replay_request_is_nonoverwriting_and_runs_offset_case_first(self):
        run_dir = self.root / "benchmark_results" / "formal"
        run_dir.mkdir(parents=True)
        output = self.root / "config" / "gate3_replay_request.json"
        case_ids = [f"D-H{i:02d}" for i in range(1, 6)]
        gate3_pipeline.write_replay_request(self.root, run_dir, "formal", case_ids, output)
        request = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(request["case_ids"][0], "D-H04")
        self.assertEqual(set(request["case_ids"]), set(case_ids))
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            gate3_pipeline.write_replay_request(self.root, run_dir, "formal", case_ids, output)

    def test_analysis_writes_fact_candidate_sequence_and_waits_for_fusion(self):
        run_dir = gate3_pipeline.create_debug_run(self.root, "debug", ["D-H01"])
        case = next(
            item
            for item in gate3_pipeline.load_cases(self.root)
            if item["case_id"] == "D-H01"
        )
        summary = gate3_pipeline.run_analysis_cases(
            self.root, run_dir, "debug", [case], gate3_pipeline.load_protocol(self.root)
        )
        self.assertEqual(summary["awaiting_fusion_case_ids"], ["D-H01"])
        case_dir = run_dir / "cases" / "D-H01"
        for relative in (
            "metadata/input_metadata.json",
            "analysis/brep_summary.json",
            "analysis/candidates.json",
            "analysis/inference_log.json",
            "sequence/inferred_sequence.json",
        ):
            self.assertTrue((case_dir / relative).is_file(), relative)
        candidates = json.loads((case_dir / "analysis" / "candidates.json").read_text())
        self.assertEqual(candidates["selected_candidate_id"], candidates["coupled_candidates"]["candidates"][0]["candidate_id"])
        self.assertTrue(candidates["pre_fusion_validation"]["geometry_pass"])
        self.assertEqual(candidates["pre_fusion_validation"]["surface_mode"], "diagnostic_only")
        self.assertTrue((case_dir / "work" / "candidate_rebuild.step").is_file())
        self.assertFalse((case_dir / "final_status.json").exists())

    def test_successful_replay_is_validated_before_automatic_success(self):
        run_dir = gate3_pipeline.create_debug_run(self.root, "finalize", ["D-H01"])
        case = next(item for item in gate3_pipeline.load_cases(self.root) if item["case_id"] == "D-H01")
        gate3_pipeline.run_analysis_cases(
            self.root, run_dir, "finalize", [case], gate3_pipeline.load_protocol(self.root)
        )
        case_dir = run_dir / "cases" / "D-H01"
        sequence = json.loads((case_dir / "sequence" / "inferred_sequence.json").read_text())
        replay_dir = case_dir / "replay"
        replay_dir.mkdir()
        through_hole_reconstruction.rebuild_sequence_step(sequence, replay_dir / "replay.step")
        (replay_dir / "replay.f3d").write_bytes(b"fusion archive evidence")
        (replay_dir / "replay_log.json").write_text(
            json.dumps({"status": "success", "world_frame_max_error_mm": 0.0}),
            encoding="utf-8",
        )
        status = gate3_pipeline.finalize_replay_case(
            self.root, case_dir, gate3_pipeline.load_protocol(self.root)
        )
        self.assertEqual(status["terminal_status"], "automatic_success")
        self.assertTrue(json.loads((case_dir / "validation" / "validation_metrics.json").read_text())["geometry_pass"])
        self.assertTrue(result_package.audit_case_package(case_dir)["complete"])

    def test_gate3_feature_validation_rejects_shifted_hole_that_volume_bbox_accept(self):
        reference = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-H01.step"
        recovered = through_hole_reconstruction.recover_development_sequence(
            PROJECT_ROOT, "D-H01", reference
        )
        shifted = copy.deepcopy(recovered["sequence"])
        shifted["operations"][2]["loops"][0]["primitives"][0]["center"][0] += 1.0
        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / "shifted.step"
            through_hole_reconstruction.rebuild_sequence_step(shifted, replay)
            base_metrics = candidate_validation.validate_replay_step(
                reference, replay, gate3_pipeline.load_protocol(PROJECT_ROOT)
            )
            metrics = gate3_pipeline.validate_gate3_replay(
                reference, replay, "D-H01", gate3_pipeline.load_protocol(PROJECT_ROOT)
            )
        self.assertTrue(base_metrics["geometry_pass"])
        self.assertFalse(metrics["feature_match_pass"])
        self.assertFalse(metrics["geometry_pass"])
        self.assertGreater(metrics["feature_match"]["axis_line_offset_mm"], 0.9)


class Gate3VerifierTests(unittest.TestCase):
    def test_verifier_requires_three_automatic_five_success_and_five_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "benchmark_results" / "formal"
            run_dir.mkdir(parents=True)
            for relative in (
                "benchmarks/case_matrix.json",
                "benchmarks/manifest.json",
                "config/gate3_validation_protocol.json",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PROJECT_ROOT / relative, destination)
            (run_dir / "environment.json").write_text(
                json.dumps({"environment_schema": "gate3-environment-0.1", "fusion": {"version": "test", "python_version": "test"}}),
                encoding="utf-8",
            )
            protocol_hash = hashlib.sha256((root / "config" / "gate3_validation_protocol.json").read_bytes()).hexdigest()
            manifest = {
                "manifest_schema": "gate3-run-manifest-0.1",
                "run_id": "formal",
                "git_commit": "a" * 40,
                "git_dirty_at_start": False,
                "case_ids": [f"D-H{i:02d}" for i in range(1, 6)],
                "validation_protocol_sha256": protocol_hash,
                "matrix_sha256": hashlib.sha256((root / "benchmarks" / "case_matrix.json").read_bytes()).hexdigest(),
                "benchmark_manifest_sha256": hashlib.sha256((root / "benchmarks" / "manifest.json").read_bytes()).hexdigest(),
            }
            (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            for index in range(1, 6):
                case_id = f"D-H{index:02d}"
                case_dir = run_dir / "cases" / case_id
                for relative in (
                    "metadata/input_metadata.json",
                    "analysis/brep_summary.json",
                    "analysis/candidates.json",
                    "analysis/inference_log.json",
                    "sequence/inferred_sequence.json",
                    "replay/replay_log.json",
                    "replay/replay.f3d",
                    "replay/replay.step",
                    "validation/validation_metrics.json",
                ):
                    path = case_dir / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == ".json":
                        value = {"valid_step": True} if "input_metadata" in path.name else ({"geometry_pass": True, "feature_match_pass": True} if "validation_metrics" in path.name else {})
                        path.write_text(json.dumps(value), encoding="utf-8")
                    else:
                        path.write_bytes(b"evidence")
                status = {"terminal_status": "automatic_success", "ambiguous": False}
                (case_dir / "final_status.json").write_text(json.dumps(status), encoding="utf-8")
            report = verify_gate3.verify_run(run_dir)
            self.assertTrue(report["gate_pass"])
            self.assertEqual(report["verifier_schema"], "gate3-verifier-0.2")
            self.assertEqual(report["automatic_success_count"], 5)
            self.assertEqual(report["feature_match_pass_count"], 5)
            self.assertEqual(report["package_complete_count"], 5)

            metrics_path = run_dir / "cases" / "D-H05" / "validation" / "validation_metrics.json"
            metrics_path.write_text(
                json.dumps({"geometry_pass": True, "feature_match_pass": False}),
                encoding="utf-8",
            )
            report = verify_gate3.verify_run(run_dir)
            self.assertFalse(report["gate_pass"])
            self.assertFalse(report["checks"]["successful_cases_feature_match_pass"])
            metrics_path.write_text(
                json.dumps({"geometry_pass": True, "feature_match_pass": True}),
                encoding="utf-8",
            )

            (root / "config" / "gate3_validation_protocol.json").write_text("{}", encoding="utf-8")
            self.assertFalse(verify_gate3.verify_run(run_dir)["gate_pass"])

            shutil.copyfile(
                PROJECT_ROOT / "config" / "gate3_validation_protocol.json",
                root / "config" / "gate3_validation_protocol.json",
            )

            (run_dir / "cases" / "D-H05" / "final_status.json").write_text(
                json.dumps({"terminal_status": "failed", "ambiguous": False, "failure_stage": "fusion_replay", "failure_code": "x", "error_summary": "x"}),
                encoding="utf-8",
            )
            report = verify_gate3.verify_run(run_dir)
            self.assertFalse(report["gate_pass"])


if __name__ == "__main__":
    unittest.main()
