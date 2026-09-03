import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import verify_gate2


class Gate2VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name) / "benchmark_results" / "formal-run"
        self.case_ids = [f"D-S{index:02d}" for index in range(1, 11)]
        self.write_json(
            self.run_dir / "manifest.json",
            {
                "manifest_schema": "gate2-run-manifest-0.1",
                "run_id": "formal-run",
                "git_dirty_at_start": False,
                "case_ids": self.case_ids,
            },
        )
        self.write_json(self.run_dir / "environment.json", {"fusion": {"version": "test"}})
        for index, case_id in enumerate(self.case_ids):
            if index < 8:
                self.write_success(case_id, ambiguous=index == 0)
            else:
                self.write_failure(case_id)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def write_common(self, case_id):
        case = self.run_dir / "cases" / case_id
        self.write_json(case / "metadata" / "input_metadata.json", {"valid_step": True})
        self.write_json(case / "analysis" / "brep_summary.json", {"solid_count": 1})
        self.write_json(case / "analysis" / "inference_log.json", {"status": "complete"})
        return case

    def write_success(self, case_id, ambiguous=False):
        case = self.write_common(case_id)
        self.write_json(case / "analysis" / "candidates.json", {"candidates": []})
        self.write_json(case / "sequence" / "inferred_sequence.json", {"operations": []})
        self.write_json(case / "replay" / "replay_log.json", {"status": "success"})
        (case / "replay" / "replay.f3d").write_bytes(b"f3d")
        (case / "replay" / "replay.step").write_bytes(b"step")
        self.write_json(
            case / "validation" / "validation_metrics.json", {"geometry_pass": True}
        )
        self.write_json(
            case / "final_status.json",
            {"terminal_status": "automatic_success", "ambiguous": ambiguous},
        )

    def write_failure(self, case_id):
        case = self.write_common(case_id)
        self.write_json(
            case / "final_status.json",
            {
                "terminal_status": "failed",
                "ambiguous": False,
                "failure_stage": "fusion_replay",
                "failure_code": "test_failure",
                "error_summary": "controlled test failure",
                "not_applicable_reason": "no replay entity was available",
            },
        )

    def test_reports_complete_packages_separately_from_automatic_success(self):
        report = verify_gate2.verify_run(self.run_dir)
        self.assertEqual(report["package_complete_count"], 10)
        self.assertEqual(report["automatic_success_count"], 8)
        self.assertEqual(report["geometry_pass_count"], 8)
        self.assertEqual(report["ambiguous_count"], 1)
        self.assertTrue(report["gate_pass"])

    def test_geometry_failure_blocks_gate_without_changing_package_completeness(self):
        self.write_json(
            self.run_dir
            / "cases"
            / "D-S01"
            / "validation"
            / "validation_metrics.json",
            {"geometry_pass": False},
        )
        report = verify_gate2.verify_run(self.run_dir)
        self.assertEqual(report["package_complete_count"], 10)
        self.assertEqual(report["automatic_success_count"], 8)
        self.assertEqual(report["geometry_pass_count"], 7)
        self.assertFalse(report["gate_pass"])
        self.assertIn("D-S01", report["successful_geometry_failures"])

    def test_dirty_start_snapshot_blocks_formal_gate(self):
        manifest_path = self.run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["git_dirty_at_start"] = True
        self.write_json(manifest_path, manifest)
        report = verify_gate2.verify_run(self.run_dir)
        self.assertFalse(report["checks"]["git_clean_at_start"])
        self.assertFalse(report["gate_pass"])


if __name__ == "__main__":
    unittest.main()
