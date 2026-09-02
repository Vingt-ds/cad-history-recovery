import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import verify_gate1


class Gate1VerifierTests(unittest.TestCase):
    def test_complete_project_passes_all_gate1_checks(self):
        checks = verify_gate1.run_checks(PROJECT_ROOT)
        failures = [check for check in checks if not check["passed"]]
        self.assertEqual(failures, [])
        names = {check["name"] for check in checks}
        self.assertIn("box_stability", names)
        self.assertIn("box_hole_stability", names)
        self.assertIn("benchmark_freeze", names)
        self.assertIn("geometry_baseline", names)

    def test_incomplete_project_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            checks = verify_gate1.run_checks(Path(directory))
        self.assertTrue(any(not check["passed"] for check in checks))

    def test_report_renderer_preserves_failed_status(self):
        report = verify_gate1.render_report(
            [{"name": "example", "passed": False, "detail": "missing evidence"}]
        )
        self.assertIn("Overall status: **FAIL**", report)
        self.assertIn("| FAIL | `example` | missing evidence |", report)


if __name__ == "__main__":
    unittest.main()
