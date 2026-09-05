import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

try:
    import gate4_pipeline
except ImportError:
    gate4_pipeline = None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class Gate4PipelineTests(unittest.TestCase):
    commit = "1" * 40

    def _roots(self, directory):
        code_root = Path(directory) / "code"
        results_root = Path(directory) / "results"
        config = code_root / "config"
        inventory = {
            "input_inventory_schema": "gate4-input-inventory-0.1",
            "benchmark_manifest_sha256": "2" * 64,
            "cases": [],
        }
        for split, prefix in (("development", "D"), ("held_out", "T")):
            for index in range(1, 16):
                case_id = f"{prefix}-X{index:02d}"
                inventory["cases"].append(
                    {
                        "case_id": case_id,
                        "split": split,
                        "source": "fixture",
                        "units": "mm",
                        "path": f"benchmarks/inputs/{split}/{case_id}.step",
                        "sha256": f"{index:064x}",
                    }
                )
        inventory_path = config / "gate4_input_inventory.json"
        write_json(inventory_path, inventory)
        freeze = {
            "freeze_schema": "gate4-freeze-lock-0.1",
            "frozen": True,
            "evaluation_commit_binding": "containing_git_commit",
            "files": {
                "config/gate4_input_inventory.json": hashlib.sha256(
                    inventory_path.read_bytes()
                ).hexdigest()
            },
        }
        write_json(config / "gate4_freeze_lock.json", freeze)
        return code_root, results_root

    def _create_formal(self, code_root, results_root, run_id, split, environment):
        with mock.patch.object(
            gate4_pipeline, "_git_snapshot", return_value=(self.commit, False)
        ):
            return gate4_pipeline.create_formal_run(
                code_root, results_root, run_id, split, environment
            )

    def test_formal_run_uses_clean_freeze_commit_and_label_free_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            code_root, results_root = self._roots(directory)
            run_dir, cases = self._create_formal(
                code_root,
                results_root,
                "gate4-development-formal",
                "development",
                {"environment_schema": "gate4-environment-0.1"},
            )
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(len(cases), 15)
        self.assertEqual(manifest["git_commit"], self.commit)
        self.assertFalse(manifest["git_dirty_at_start"])
        self.assertEqual(manifest["evaluation_split"], "development")
        self.assertFalse(manifest["expected_labels_loaded"])
        self.assertNotIn("family", json.dumps(manifest))
        self.assertNotIn("expected_scope", json.dumps(manifest))

    def test_formal_run_rejects_dirty_freeze_tamper_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            code_root, results_root = self._roots(directory)
            with mock.patch.object(
                gate4_pipeline, "_git_snapshot", return_value=(self.commit, True)
            ):
                with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                    gate4_pipeline.create_formal_run(
                        code_root, results_root, "gate4-dev", "development", {}
                    )
            inventory = code_root / "config" / "gate4_input_inventory.json"
            original = inventory.read_bytes()
            inventory.write_bytes(original + b" ")
            with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                self._create_formal(
                    code_root, results_root, "gate4-dev", "development", {}
                )
            inventory.write_bytes(original)
            self._create_formal(
                code_root, results_root, "gate4-dev", "development", {}
            )
            with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                self._create_formal(
                    code_root, results_root, "gate4-dev", "development", {}
                )

    def test_held_out_formal_run_creates_single_execution_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            code_root, results_root = self._roots(directory)
            self._create_formal(
                code_root,
                results_root,
                "gate4-held-out-formal",
                "held_out",
                {},
            )
            lock_path = results_root / "logs" / "gate4" / "heldout_execution_lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                self._create_formal(
                    code_root,
                    results_root,
                    "gate4-held-out-second",
                    "held_out",
                    {},
                )

        self.assertEqual(lock["attempt_number"], 1)
        self.assertEqual(lock["evaluation_commit"], self.commit)

    def _complete_unsupported_cases(self, run_dir, case_ids):
        for case_id in case_ids:
            case_dir = run_dir / "cases" / case_id
            write_json(
                case_dir / "metadata" / "input_metadata.json",
                {"valid_step": True},
            )
            write_json(case_dir / "analysis" / "brep_summary.json", {})
            write_json(case_dir / "analysis" / "inference_log.json", {})
            write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "unsupported",
                    "ambiguous": False,
                    "scope_rule": "fixture_rule",
                    "not_applicable_reason": "fixture",
                },
            )

    def test_seal_requires_15_complete_packages_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            code_root, results_root = self._roots(directory)
            run_dir, cases = self._create_formal(
                code_root,
                results_root,
                "gate4-development-formal",
                "development",
                {},
            )
            with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                gate4_pipeline.seal_run(run_dir)
            self._complete_unsupported_cases(run_dir, [case["case_id"] for case in cases])
            seal = gate4_pipeline.seal_run(run_dir)
            self.assertTrue(gate4_pipeline.verify_seal(run_dir)["valid"])
            (run_dir / "cases" / cases[0]["case_id"] / "final_status.json").write_text(
                "{}\n", encoding="utf-8"
            )
            self.assertFalse(gate4_pipeline.verify_seal(run_dir)["valid"])
            self.assertEqual(seal["case_count"], 15)

    def test_analysis_passes_only_path_sha_workdir_and_protocols_to_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "benchmarks" / "inputs" / "development" / "leaky-name.step"
            step.parent.mkdir(parents=True)
            step.write_bytes(b"fixture-step")
            digest = hashlib.sha256(step.read_bytes()).hexdigest()
            run_dir = root / "benchmark_results" / "run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "manifest.json", {"evaluation_split": "development"})
            captured = []

            def infer(*args):
                captured.append(args)
                return {
                    "semantic_inference_schema": "gate4-semantic-inference-0.1",
                    "brep_summary": {"brep_summary_schema": "brep-summary-0.1"},
                    "route": {"route": "gate2", "reason": "fixture"},
                    "semantic_outcome": "candidate_selected",
                    "candidate_generation_entered": True,
                    "candidate_set": [{"candidate_id": "candidate-1"}],
                    "selected_candidate_id": "candidate-1",
                    "selected_sequence": {"schema_version": "cadseq-0.2"},
                    "ambiguous": False,
                }

            cases = [
                {
                    "case_id": "D-LEAK01",
                    "split": "development",
                    "source": "fixture",
                    "units": "mm",
                    "path": "benchmarks/inputs/development/leaky-name.step",
                    "sha256": digest,
                }
            ]
            result = gate4_pipeline.run_analysis_cases(
                root,
                run_dir,
                "run",
                cases,
                {"gate": 2},
                {"gate": 3},
                infer_fn=infer,
            )

        self.assertEqual(len(captured), 1)
        self.assertEqual(len(captured[0]), 5)
        self.assertEqual(captured[0][0], step)
        self.assertEqual(captured[0][1], digest)
        self.assertNotIn("D-LEAK01", captured[0])
        self.assertEqual(result["awaiting_fusion_case_ids"], ["D-LEAK01"])

    def test_formal_analysis_rechecks_commit_and_held_out_execution_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "benchmark_results" / "gate4-held-out-formal"
            run_dir.mkdir(parents=True)
            write_json(
                run_dir / "manifest.json",
                {
                    "manifest_schema": "gate4-run-manifest-0.1",
                    "run_id": "gate4-held-out-formal",
                    "evaluation_split": "held_out",
                    "git_commit": self.commit,
                },
            )
            write_json(
                root / "logs" / "gate4" / "heldout_execution_lock.json",
                {
                    "lock_schema": "gate4-heldout-execution-lock-0.1",
                    "run_id": "gate4-held-out-formal",
                    "evaluation_commit": self.commit,
                    "attempt_number": 1,
                },
            )
            with mock.patch.object(
                gate4_pipeline, "_git_snapshot", return_value=("2" * 40, False)
            ), mock.patch.object(gate4_pipeline, "_verify_freeze"):
                with self.assertRaisesRegex(
                    gate4_pipeline.Gate4PipelineError,
                    "evaluation_commit_mismatch",
                ):
                    gate4_pipeline.run_analysis_cases(
                        root, run_dir, "gate4-held-out-formal", [], {}, {}
                    )

            with mock.patch.object(
                gate4_pipeline, "_git_snapshot", return_value=(self.commit, False)
            ), mock.patch.object(gate4_pipeline, "_verify_freeze"):
                (root / "logs" / "gate4" / "heldout_execution_lock.json").unlink()
                with self.assertRaisesRegex(
                    gate4_pipeline.Gate4PipelineError,
                    "held_out_execution_lock_missing",
                ):
                    gate4_pipeline.run_analysis_cases(
                        root, run_dir, "gate4-held-out-formal", [], {}, {}
                    )

    def test_gate4_package_audit_rejects_manual_success_and_fake_unsupported_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            case_dir = Path(directory) / "case"
            write_json(case_dir / "metadata" / "input_metadata.json", {"valid_step": True})
            write_json(case_dir / "analysis" / "brep_summary.json", {})
            write_json(case_dir / "analysis" / "inference_log.json", {})
            write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "unsupported",
                    "ambiguous": False,
                    "scope_rule": "fixture",
                    "not_applicable_reason": "fixture",
                },
            )
            write_json(case_dir / "analysis" / "candidates.json", {})
            audit = gate4_pipeline.audit_gate4_case_package(case_dir)
            self.assertFalse(audit["complete"])
            self.assertIn("unsupported_forbids_candidates", audit["issues"])

            (case_dir / "analysis" / "candidates.json").unlink()
            write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "manual_success",
                    "ambiguous": False,
                },
            )
            audit = gate4_pipeline.audit_gate4_case_package(case_dir)
            self.assertFalse(audit["complete"])
            self.assertIn("manual_success_forbidden", audit["issues"])

    def test_unsupported_case_has_no_fake_candidates_or_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "benchmarks" / "inputs" / "development" / "neutral.step"
            step.parent.mkdir(parents=True)
            step.write_bytes(b"fixture-step")
            digest = hashlib.sha256(step.read_bytes()).hexdigest()
            run_dir = root / "benchmark_results" / "run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "manifest.json", {"evaluation_split": "development"})
            semantic = {
                "semantic_inference_schema": "gate4-semantic-inference-0.1",
                "brep_summary": {"brep_summary_schema": "brep-summary-0.1"},
                "route": {"route": "unsupported", "reason": "blind_hole"},
                "semantic_outcome": "unsupported",
                "candidate_generation_entered": False,
                "candidate_set": [],
                "selected_candidate_id": None,
                "selected_sequence": None,
                "ambiguous": False,
                "failure_code": "NO_SUPPORTED_HYPOTHESIS",
                "unsupported_rule": "blind_hole",
            }
            case = {
                "case_id": "D-X01",
                "split": "development",
                "source": "fixture",
                "units": "mm",
                "path": "benchmarks/inputs/development/neutral.step",
                "sha256": digest,
            }
            gate4_pipeline.run_analysis_cases(
                root,
                run_dir,
                "run",
                [case],
                {},
                {},
                infer_fn=lambda *args: semantic,
            )
            case_dir = run_dir / "cases" / "D-X01"
            status = json.loads((case_dir / "final_status.json").read_text(encoding="utf-8"))
            candidates_exists = (case_dir / "analysis" / "candidates.json").exists()
            sequence_exists = (case_dir / "sequence" / "inferred_sequence.json").exists()

        self.assertEqual(status["terminal_status"], "unsupported")
        self.assertFalse(candidates_exists)
        self.assertFalse(sequence_exists)

    def _replay_case_fixture(self, root):
        case_dir = root / "cases" / "D-S04"
        reference = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-S04.step"
        write_json(
            case_dir / "metadata" / "input_metadata.json",
            {
                "model_id": "D-S04",
                "relative_path": "benchmarks/inputs/development/D-S04.step",
                "source_step_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            },
        )
        write_json(
            case_dir / "analysis" / "candidates.json",
            {
                "route": {"route": "gate2"},
                "selected_candidate_id": "candidate-1",
                "ambiguous": False,
            },
        )
        write_json(
            case_dir / "replay" / "replay_log.json",
            {"status": "success", "world_frame_max_error_mm": 0.0},
        )
        (case_dir / "replay" / "replay.f3d").write_bytes(b"fixture")
        shutil.copyfile(reference, case_dir / "replay" / "replay.step")
        return case_dir

    def test_replay_finalization_adds_iou_without_changing_frozen_geometry_pass(self):
        gate2_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate2_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        gate3_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate3_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            case_dir = self._replay_case_fixture(Path(directory))
            status = gate4_pipeline.finalize_replay_case(
                PROJECT_ROOT, case_dir, gate2_protocol, gate3_protocol
            )
            metrics = json.loads(
                (case_dir / "validation" / "validation_metrics.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(status["terminal_status"], "automatic_success")
        self.assertTrue(metrics["geometry_pass"])
        self.assertAlmostEqual(metrics["volume_iou"], 1.0, places=12)
        self.assertEqual(metrics["validation_mode"], "volume_iou")

    def test_boolean_failure_keeps_frozen_pass_and_reports_surface_only(self):
        gate2_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate2_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        gate3_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate3_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            case_dir = self._replay_case_fixture(Path(directory))
            with mock.patch(
                "gate4_validation._boolean_volumes",
                side_effect=RuntimeError("kernel failure"),
            ):
                status = gate4_pipeline.finalize_replay_case(
                    PROJECT_ROOT, case_dir, gate2_protocol, gate3_protocol
                )
            metrics = json.loads(
                (case_dir / "validation" / "validation_metrics.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(status["terminal_status"], "automatic_success")
        self.assertTrue(metrics["geometry_pass"])
        self.assertIsNone(metrics["volume_iou"])
        self.assertTrue(metrics["boolean_validation_failed"])
        self.assertEqual(metrics["validation_mode"], "surface_only")
        self.assertIsNone(metrics["surface_only_pass"])
        self.assertTrue(metrics["surface_pass"])

    def test_replay_request_matches_run_manifest_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "benchmark_results" / "run"
            run_dir.mkdir(parents=True)
            case_ids = [f"case-{index:02d}" for index in range(15)]
            write_json(
                run_dir / "manifest.json",
                {
                    "manifest_schema": "gate4-run-manifest-0.1",
                    "run_id": "run",
                    "git_commit": self.commit,
                    "case_count": 15,
                    "case_ids": case_ids,
                },
            )
            output = root / "config" / "gate4_replay_request.json"
            with mock.patch.object(
                gate4_pipeline, "_git_snapshot", return_value=(self.commit, False)
            ), mock.patch.object(gate4_pipeline, "_verify_freeze"):
                gate4_pipeline.write_replay_request(
                    root, run_dir, "run", case_ids, output
                )
                request = json.loads(output.read_text(encoding="utf-8"))
                with self.assertRaises(gate4_pipeline.Gate4PipelineError):
                    gate4_pipeline.write_replay_request(
                        root, run_dir, "run", case_ids, output
                    )

        self.assertEqual(request["case_ids"], case_ids)
        self.assertEqual(request["run_relative_path"], "benchmark_results/run")

    def test_finalize_run_accepts_preterminal_unsupported_cases_and_zero_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "benchmark_results" / "run"
            run_dir.mkdir(parents=True)
            case_ids = [f"case-{index:02d}" for index in range(15)]
            write_json(
                run_dir / "manifest.json",
                {
                    "manifest_schema": "gate4-run-manifest-0.1",
                    "run_id": "run",
                    "git_commit": self.commit,
                    "case_count": 15,
                    "case_ids": case_ids,
                },
            )
            for case_id in case_ids:
                write_json(
                    run_dir / "cases" / case_id / "final_status.json",
                    {
                        "terminal_status": "unsupported",
                        "ambiguous": False,
                        "scope_rule": "fixture",
                        "not_applicable_reason": "fixture",
                    },
                )
            write_json(
                run_dir / "batch_replay_log.json",
                {
                    "status": "complete",
                    "run_id": "run",
                    "requested_case_count": 15,
                    "attempted_replay_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "cases": [],
                },
            )
            with mock.patch.object(
                gate4_pipeline, "_git_snapshot", return_value=(self.commit, False)
            ), mock.patch.object(gate4_pipeline, "_verify_freeze"):
                summary = gate4_pipeline.finalize_replay_run(
                    PROJECT_ROOT,
                    run_dir,
                    {},
                    {},
                )

        self.assertEqual(summary["terminal_status_counts"], {"unsupported": 15})


if __name__ == "__main__":
    unittest.main()
