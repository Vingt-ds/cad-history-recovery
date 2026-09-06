import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
EXTERNAL = PROJECT_ROOT / "external"
for directory in (TOOLS, EXTERNAL):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import gate5_demo


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def fixture_project(directory, *, split="development", case_id="D-S04"):
    root = Path(directory)
    step = root / "benchmarks" / "inputs" / split / f"{case_id}.step"
    step.parent.mkdir(parents=True)
    step.write_bytes(b"fixture-step\n")
    digest = hashlib.sha256(step.read_bytes()).hexdigest()
    write_json(
        root / "config" / "gate4_input_inventory.json",
        {
            "input_inventory_schema": "gate4-input-inventory-0.1",
            "cases": [
                {
                    "case_id": case_id,
                    "path": step.relative_to(root).as_posix(),
                    "sha256": digest,
                    "source": "fixture",
                    "split": split,
                    "units": "mm",
                }
            ],
        },
    )
    write_json(root / "config" / "gate2_validation_protocol.json", {"gate": 2})
    write_json(root / "config" / "gate3_validation_protocol.json", {"gate": 3})
    return root, step, digest


def successful_semantic(source_sha):
    return {
        "brep_summary": {"source_step_sha256": source_sha},
        "route": {"route": "gate2", "reason": "fixture"},
        "semantic_outcome": "candidate_selected",
        "candidate_generation_entered": True,
        "candidate_set": [{"candidate_id": "candidate-1", "status": "accepted"}],
        "selected_candidate_id": "candidate-1",
        "selected_sequence": {
            "schema_version": "cadseq-0.2",
            "model_id": "shape-fixture",
            "replay_mode": "parametric",
            "source_step_sha256": source_sha,
            "tolerance": {"length_mm": 0.01},
            "operations": [],
        },
        "validation": {"geometry_pass": True},
        "ambiguous": False,
    }


class Gate5DemoArtifactTests(unittest.TestCase):
    def test_demo_tool_exists(self):
        self.assertTrue((PROJECT_ROOT / "tools" / "gate5_demo.py").is_file())

    def test_fusion_wrapper_artifacts_exist(self):
        directory = PROJECT_ROOT / "fusion_scripts" / "Gate5DemoWrapper"
        self.assertTrue((directory / "Gate5DemoWrapper.py").is_file())
        self.assertTrue((directory / "Gate5DemoWrapper.manifest").is_file())


class Gate5DemoPrepareTests(unittest.TestCase):
    def test_prepare_development_case_writes_demo_contract_and_hides_case_id_from_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root, step, digest = fixture_project(directory)
            calls = []

            def infer(*args):
                calls.append((args, Path(args[0]).read_bytes()))
                return successful_semantic(digest)

            result = gate5_demo.prepare_demo(
                root,
                "D-S04",
                "runs/gate5",
                run_id="demo-d-s04",
                infer_fn=infer,
            )
            manifest = json.loads(
                (result["run_dir"] / "manifest.json").read_text(encoding="utf-8")
            )
            request = json.loads(
                (root / "runs" / "gate5_active_request.json").read_text(
                    encoding="utf-8"
                )
            )
            sequence_exists = (
                result["run_dir"] / "sequence" / "inferred_sequence.json"
            ).is_file()
            inference_args, inference_step_bytes = calls[0]
            inference_step = Path(inference_args[0])

        self.assertNotEqual(inference_step, step)
        self.assertEqual(inference_step.name, "source.step")
        self.assertEqual(inference_step_bytes, b"fixture-step\n")
        self.assertEqual(inference_args[1], digest)
        self.assertNotIn("d-s04", " ".join(str(item).lower() for item in inference_args))
        self.assertEqual(manifest["evidence_role"], "demonstration_only")
        self.assertFalse(manifest["formal_evaluation"])
        self.assertEqual(manifest["source_split"], "development")
        self.assertEqual(manifest["baseline_tag"], "gate0-4-frozen-baseline-v1")
        self.assertEqual(request["run_relative_path"], "runs/gate5/demo-d-s04")
        self.assertTrue(sequence_exists)

    def test_prepare_rejects_held_out_and_sealed_only_ambiguity_case(self):
        with tempfile.TemporaryDirectory() as directory:
            held_root, _, _ = fixture_project(
                Path(directory) / "held", split="held_out", case_id="T-S01"
            )
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "held_out_forbidden"):
                gate5_demo.prepare_demo(
                    held_root, "T-S01", "runs/gate5", infer_fn=lambda *args: None
                )
            sealed_root, _, _ = fixture_project(
                Path(directory) / "sealed", case_id="D-S01"
            )
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "sealed_artifact_only"):
                gate5_demo.prepare_demo(
                    sealed_root, "D-S01", "runs/gate5", infer_fn=lambda *args: None
                )

    def test_prepare_rejects_unsafe_output_paths_hash_mismatch_and_existing_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, digest = fixture_project(directory)
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "invalid_output_root"):
                gate5_demo.prepare_demo(
                    root, "D-S04", Path(directory).resolve(), infer_fn=lambda *args: None
                )
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "invalid_output_root"):
                gate5_demo.prepare_demo(
                    root, "D-S04", "runs/gate5/../escape", infer_fn=lambda *args: None
                )
            inventory_path = root / "config" / "gate4_input_inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["cases"][0]["sha256"] = "0" * 64
            write_json(inventory_path, inventory)
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "source_sha256_mismatch"):
                gate5_demo.prepare_demo(
                    root, "D-S04", "runs/gate5", infer_fn=lambda *args: None
                )
            inventory["cases"][0]["sha256"] = digest
            write_json(inventory_path, inventory)
            (root / "runs" / "gate5" / "existing").mkdir(parents=True)
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "run_exists"):
                gate5_demo.prepare_demo(
                    root,
                    "D-S04",
                    "runs/gate5",
                    run_id="existing",
                    infer_fn=lambda *args: successful_semantic(digest),
                )


class Gate5DemoFinalizeTests(unittest.TestCase):
    def _prepared(self, directory, case_id="D-S04", route="gate2"):
        root, _, digest = fixture_project(directory, case_id=case_id)
        semantic = successful_semantic(digest)
        semantic["route"] = {"route": route, "reason": "fixture"}
        result = gate5_demo.prepare_demo(
            root,
            case_id,
            "runs/gate5",
            run_id="demo-run",
            infer_fn=lambda *args: semantic,
        )
        replay = result["run_dir"] / "replay"
        replay.mkdir()
        (replay / "replay.f3d").write_bytes(b"f3d")
        (replay / "replay.step").write_bytes(b"step")
        write_json(
            replay / "replay_log.json",
            {"status": "success", "world_frame_max_error_mm": 0.0},
        )
        write_json(
            result["run_dir"] / "batch_replay_log.json",
            {"status": "complete", "case_count": 1, "success_count": 1},
        )
        write_json(result["run_dir"] / "environment.json", {"fusion": {"version": "fixture"}})
        return root, result["run_dir"]

    def test_finalize_uses_frozen_gate2_or_gate3_validation_function(self):
        for case_id, route, target in (
            ("D-S04", "gate2", "candidate_validation.validate_replay_step"),
            ("D-H01", "gate3", "gate3_pipeline.validate_gate3_replay"),
        ):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as directory:
                root, run_dir = self._prepared(directory, case_id, route)
                metrics = {"geometry_pass": True, "validation_schema": "fixture"}
                with mock.patch(target, return_value=metrics) as validator:
                    status = gate5_demo.finalize_demo(root, run_dir)
                self.assertEqual(status["terminal_status"], "automatic_success")
                self.assertEqual(validator.call_count, 1)
                self.assertFalse((root / "runs" / "gate5_active_request.json").exists())
                self.assertTrue((run_dir / "replay_request_used.json").is_file())

    def test_finalize_rejects_missing_outputs_and_duplicate_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, digest = fixture_project(directory)
            result = gate5_demo.prepare_demo(
                root,
                "D-S04",
                "runs/gate5",
                run_id="demo-run",
                infer_fn=lambda *args: successful_semantic(digest),
            )
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "replay_artifact_missing"):
                gate5_demo.finalize_demo(root, result["run_dir"])
            replay = result["run_dir"] / "replay"
            replay.mkdir()
            (replay / "replay.f3d").write_bytes(b"f3d")
            (replay / "replay.step").write_bytes(b"step")
            write_json(replay / "replay_log.json", {"status": "success"})
            with mock.patch(
                "candidate_validation.validate_replay_step",
                return_value={"geometry_pass": True},
            ):
                gate5_demo.finalize_demo(root, result["run_dir"])
            with self.assertRaisesRegex(gate5_demo.Gate5DemoError, "already_finalized"):
                gate5_demo.finalize_demo(root, result["run_dir"])

    def test_verify_checks_complete_demo_without_writing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root, run_dir = self._prepared(directory)
            with mock.patch(
                "candidate_validation.validate_replay_step",
                return_value={"geometry_pass": True},
            ):
                gate5_demo.finalize_demo(root, run_dir)
            before = sorted(path.relative_to(run_dir) for path in run_dir.rglob("*"))
            report = gate5_demo.verify_demo(root, run_dir)
            after = sorted(path.relative_to(run_dir) for path in run_dir.rglob("*"))
        self.assertTrue(report["valid"])
        self.assertEqual(before, after)


class Gate5FusionWrapperTests(unittest.TestCase):
    def test_wrapper_only_delegates_frozen_replay_case(self):
        source = (
            PROJECT_ROOT
            / "fusion_scripts"
            / "Gate5DemoWrapper"
            / "Gate5DemoWrapper.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_replay_case", source)
        self.assertIn("Gate2SequenceReplay.py", source)
        self.assertNotIn("_run_sequence", source)
        for forbidden in ("sketches.add", "extrudeFeatures.add", "cutFeatures.add"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
