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


if __name__ == "__main__":
    unittest.main()
