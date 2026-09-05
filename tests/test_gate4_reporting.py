import json
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
    import gate4_reporting
except ImportError:
    gate4_reporting = None


class Gate4StatisticsTests(unittest.TestCase):
    def test_collect_case_records_reads_conditional_artifacts_without_reclassifying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development = root / "development"
            held_out = root / "held-out"
            case_id = "T-C02"
            case_dir = held_out / "cases" / case_id
            development.mkdir()
            held_out.mkdir()
            (development / "manifest.json").write_text(
                json.dumps({"run_id": "dev", "case_ids": []}), encoding="utf-8"
            )
            (held_out / "manifest.json").write_text(
                json.dumps({"run_id": "test", "case_ids": [case_id]}),
                encoding="utf-8",
            )
            (case_dir / "metadata").mkdir(parents=True)
            (case_dir / "analysis").mkdir()
            (case_dir / "metadata" / "input_metadata.json").write_text(
                json.dumps({"valid_step": True}), encoding="utf-8"
            )
            (case_dir / "analysis" / "brep_summary.json").write_text(
                "{}", encoding="utf-8"
            )
            (case_dir / "analysis" / "inference_log.json").write_text(
                json.dumps(
                    {
                        "status": "unsupported",
                        "automatic_processing_seconds": 0.25,
                        "route": {"route": "gate2"},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis" / "candidates.json").write_text(
                json.dumps(
                    {
                        "candidate_set": [
                            {"candidate_id": "candidate-1", "status": "rejected"}
                        ],
                        "selected_candidate_id": None,
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "final_status.json").write_text(
                json.dumps(
                    {
                        "terminal_status": "unsupported",
                        "ambiguous": False,
                        "scope_rule": "fixture",
                        "not_applicable_reason": "fixture",
                    }
                ),
                encoding="utf-8",
            )
            labels = {
                case_id: {
                    "split": "held_out",
                    "family": "unsupported_fillet",
                    "expected_scope": "unsupported",
                    "expected_behavior": "reject_unsupported_fillet",
                }
            }

            records = gate4_reporting.collect_case_records(
                development, held_out, labels
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["terminal_status"], "unsupported")
        self.assertTrue(records[0]["package_complete"])
        self.assertFalse(records[0]["fusion_attempted"])
        self.assertEqual(records[0]["automatic_processing_seconds"], 0.25)

    def test_statistics_keep_success_completeness_iou_and_surface_only_separate(self):
        records = []
        for index in range(27):
            records.append(
                {
                    "split": "development" if index < 15 else "held_out",
                    "expected_scope": "supported",
                    "terminal_status": "automatic_success" if index < 20 else "failed",
                    "ambiguous": False,
                    "package_complete": True,
                    "fusion_attempted": True,
                    "fusion_failed": index == 26,
                    "geometry_validated": index < 24,
                    "geometry_pass": index < 23,
                    "volume_iou": 1.0 if index < 22 else None,
                    "validation_mode": "volume_iou" if index < 22 else "surface_only",
                    "automatic_processing_seconds": 1.0,
                    "manual_correction_count": 0,
                    "failure_stage": "fusion_replay" if index == 26 else None,
                    "failure_code": "FUSION_GEOMETRIC_OPERATION_FAILURE" if index == 26 else None,
                }
            )
        records.extend(
            [
                {
                    "split": "held_out",
                    "expected_scope": "ambiguous",
                    "terminal_status": "automatic_success",
                    "ambiguous": True,
                    "package_complete": True,
                    "fusion_attempted": True,
                    "fusion_failed": False,
                    "geometry_validated": True,
                    "geometry_pass": True,
                    "volume_iou": 0.9,
                    "validation_mode": "volume_iou",
                    "automatic_processing_seconds": 1.0,
                    "manual_correction_count": 0,
                    "failure_stage": None,
                    "failure_code": None,
                },
                {
                    "split": "held_out",
                    "expected_scope": "unsupported",
                    "terminal_status": "unsupported",
                    "ambiguous": False,
                    "package_complete": True,
                    "fusion_attempted": False,
                    "fusion_failed": False,
                    "geometry_validated": False,
                    "geometry_pass": None,
                    "volume_iou": None,
                    "validation_mode": None,
                    "automatic_processing_seconds": 1.0,
                    "manual_correction_count": 0,
                    "failure_stage": None,
                    "failure_code": None,
                },
                {
                    "split": "held_out",
                    "expected_scope": "unsupported",
                    "terminal_status": "failed",
                    "ambiguous": False,
                    "package_complete": True,
                    "fusion_attempted": False,
                    "fusion_failed": False,
                    "geometry_validated": False,
                    "geometry_pass": None,
                    "volume_iou": None,
                    "validation_mode": None,
                    "automatic_processing_seconds": 1.0,
                    "manual_correction_count": 0,
                    "failure_stage": "semantic_inference",
                    "failure_code": "ROUTING_REJECTION",
                },
            ]
        )

        report = gate4_reporting.compute_statistics(records)

        self.assertEqual(report["overall"]["package_complete"], {"count": 30, "total": 30})
        self.assertEqual(report["overall"]["supported_automatic_success"], {"count": 20, "total": 27})
        self.assertEqual(report["overall"]["unsupported_correct_rejection"], {"count": 1, "total": 2})
        self.assertEqual(report["overall"]["ambiguous_case_count"], 1)
        self.assertEqual(report["overall"]["volume_iou"]["count"], 23)
        self.assertEqual(report["overall"]["surface_only_count"], 2)
        self.assertEqual(report["overall"]["fusion_replay_failure"], {"count": 1, "total": 28})
        self.assertIn("development", report["by_split"])
        self.assertIn("held_out", report["by_split"])


class LabelReleaseTests(unittest.TestCase):
    def test_expected_labels_cannot_load_until_both_raw_runs_are_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark = root / "benchmarks" / "case_matrix.json"
            benchmark.parent.mkdir(parents=True)
            benchmark.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "X",
                                "split": "held_out",
                                "family": "fixture",
                                "expected_scope": "supported",
                                "expected_behavior": "fixture",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            for name, split in (("dev", "development"), ("test", "held_out")):
                run = root / name
                run.mkdir()
                (run / "manifest.json").write_text(
                    json.dumps(
                        {
                            "manifest_schema": "gate4-run-manifest-0.1",
                            "evaluation_split": split,
                            "git_commit": "a" * 40,
                        }
                    ),
                    encoding="utf-8",
                )
            with mock.patch(
                "gate4_pipeline.verify_seal",
                side_effect=[{"valid": True}, {"valid": False}],
            ):
                with self.assertRaises(gate4_reporting.Gate4ReportingError):
                    gate4_reporting.load_expected_labels_after_seal(
                        root, root / "dev", root / "test"
                    )
            with mock.patch(
                "gate4_pipeline.verify_seal",
                side_effect=[{"valid": True}, {"valid": True}],
            ):
                labels = gate4_reporting.load_expected_labels_after_seal(
                    root, root / "dev", root / "test"
                )

        self.assertEqual(labels["X"]["expected_scope"], "supported")

    def test_two_development_seals_cannot_release_expected_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark = root / "benchmarks" / "case_matrix.json"
            benchmark.parent.mkdir(parents=True)
            benchmark.write_text('{"cases": []}\n', encoding="utf-8")
            dev_a = root / "dev-a"
            dev_b = root / "dev-b"
            for run in (dev_a, dev_b):
                run.mkdir()
                (run / "manifest.json").write_text(
                    json.dumps(
                        {
                            "manifest_schema": "gate4-run-manifest-0.1",
                            "evaluation_split": "development",
                            "git_commit": "a" * 40,
                        }
                    ),
                    encoding="utf-8",
                )
            with mock.patch(
                "gate4_pipeline.verify_seal", return_value={"valid": True}
            ):
                with self.assertRaisesRegex(
                    gate4_reporting.Gate4ReportingError,
                    "sealed_run_roles_invalid",
                ):
                    gate4_reporting.load_expected_labels_after_seal(
                        root, dev_a, dev_b
                    )


if __name__ == "__main__":
    unittest.main()
