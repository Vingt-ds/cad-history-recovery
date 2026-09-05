import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

try:
    import gate4_policy
except ImportError:
    gate4_policy = None


class RetryPolicyTests(unittest.TestCase):
    def test_retry_allowlist_is_exact_and_excludes_algorithmic_outcomes(self):
        self.assertEqual(
            gate4_policy.INFRASTRUCTURE_RETRY_CODES,
            {
                "FUSION_LAUNCH_FAILURE",
                "PATH_IO_FAILURE",
                "EXPORT_IO_FAILURE",
                "LOGGING_FAILURE",
                "PACKAGE_WRITE_FAILURE",
            },
        )
        for code in (
            "NO_SUPPORTED_HYPOTHESIS",
            "AMBIGUOUS_CANDIDATE_FAILURE",
            "VALIDATION_FAILURE",
            "GEOMETRY_MISMATCH",
            "SCHEMA_REJECTION",
            "ROUTING_REJECTION",
            "FUSION_GEOMETRIC_OPERATION_FAILURE",
        ):
            self.assertFalse(gate4_policy.is_retryable(code))

    def test_retry_requires_preserved_first_attempt_same_hashes_and_dev_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            first_attempt = Path(directory) / "attempt-1.json"
            first_attempt.write_text("{}\n", encoding="utf-8")
            hashes = {"external/gate4_inference.py": "a" * 64}
            self.assertTrue(
                gate4_policy.authorize_retry(
                    "FUSION_LAUNCH_FAILURE",
                    first_attempt,
                    hashes,
                    dict(hashes),
                    development_rerun_complete=True,
                )
            )
            for kwargs in (
                {"failure_code": "VALIDATION_FAILURE"},
                {"first_attempt_path": Path(directory) / "missing.json"},
                {"semantic_hashes_after": {"external/gate4_inference.py": "b" * 64}},
                {"development_rerun_complete": False},
            ):
                values = {
                    "failure_code": "FUSION_LAUNCH_FAILURE",
                    "first_attempt_path": first_attempt,
                    "semantic_hashes_before": hashes,
                    "semantic_hashes_after": dict(hashes),
                    "development_rerun_complete": True,
                }
                values.update(kwargs)
                with self.assertRaises(gate4_policy.Gate4PolicyError):
                    gate4_policy.authorize_retry(**values)


class InputInventoryTests(unittest.TestCase):
    def test_inventory_strips_all_expected_labels_and_geometry(self):
        inventory = gate4_policy.build_input_inventory(PROJECT_ROOT)
        self.assertEqual(len(inventory["cases"]), 30)
        self.assertEqual(
            {case["split"] for case in inventory["cases"]},
            {"development", "held_out"},
        )
        forbidden = {
            "family",
            "expected_scope",
            "expected_behavior",
            "geometry",
            "output_step",
        }
        self.assertTrue(
            all(forbidden.isdisjoint(case) for case in inventory["cases"])
        )
        self.assertTrue(
            all(
                set(case) == {"case_id", "split", "source", "units", "path", "sha256"}
                for case in inventory["cases"]
            )
        )

    def test_inventory_split_selection_has_exact_15_cases(self):
        inventory = gate4_policy.build_input_inventory(PROJECT_ROOT)
        development = gate4_policy.select_cases(inventory, "development")
        held_out = gate4_policy.select_cases(inventory, "held_out")
        self.assertEqual(len(development), 15)
        self.assertEqual(len(held_out), 15)
        self.assertTrue(all(case["case_id"].startswith("D-") for case in development))
        self.assertTrue(all(case["case_id"].startswith("T-") for case in held_out))


if __name__ == "__main__":
    unittest.main()
