import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

import gate4_pipeline
try:
    import verify_gate4
except ImportError:
    verify_gate4 = None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class Gate4VerifierTests(unittest.TestCase):
    commit = "a" * 40

    def _project(self, directory):
        root = Path(directory)
        inventory_path = root / "config" / "gate4_input_inventory.json"
        write_json(
            inventory_path,
            {
                "input_inventory_schema": "gate4-input-inventory-0.1",
                "benchmark_manifest_sha256": "b" * 64,
                "cases": [],
            },
        )
        write_json(
            root / "config" / "gate4_freeze_lock.json",
            {
                "freeze_schema": "gate4-freeze-lock-0.1",
                "frozen": True,
                "evaluation_commit_binding": "containing_git_commit",
                "files": {
                    "config/gate4_input_inventory.json": hashlib.sha256(
                        inventory_path.read_bytes()
                    ).hexdigest()
                },
            },
        )
        runs = []
        for split in ("development", "held_out"):
            run_id = f"gate4-{split}"
            run_dir = root / "benchmark_results" / run_id
            case_ids = [f"{split}-{index:02d}" for index in range(15)]
            write_json(
                run_dir / "manifest.json",
                {
                    "manifest_schema": "gate4-run-manifest-0.1",
                    "run_id": run_id,
                    "evaluation_split": split,
                    "git_commit": self.commit,
                    "git_dirty_at_start": False,
                    "expected_labels_loaded": False,
                    "case_count": 15,
                    "case_ids": case_ids,
                },
            )
            write_json(run_dir / "environment.json", {})
            for case_id in case_ids:
                case_dir = run_dir / "cases" / case_id
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
            gate4_pipeline.seal_run(run_dir)
            runs.append(run_dir)
        write_json(
            root / "logs" / "gate4" / "heldout_execution_lock.json",
            {
                "lock_schema": "gate4-heldout-execution-lock-0.1",
                "run_id": "gate4-held_out",
                "evaluation_commit": self.commit,
                "attempt_number": 1,
            },
        )
        return root, runs[0], runs[1]

    def test_protocol_integrity_passes_even_with_zero_algorithm_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root, development, held_out = self._project(directory)
            report = verify_gate4.verify(root, development, held_out)

        self.assertTrue(report["gate_pass"])
        self.assertEqual(report["package_complete_count"], 30)
        self.assertEqual(report["automatic_success_count"], 0)

    def test_tampered_raw_run_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root, development, held_out = self._project(directory)
            status = next((held_out / "cases").glob("*/final_status.json"))
            status.write_text("{}\n", encoding="utf-8")
            report = verify_gate4.verify(root, development, held_out)

        self.assertFalse(report["gate_pass"])
        self.assertIn("held_out_seal", report["failed_checks"])


if __name__ == "__main__":
    unittest.main()
