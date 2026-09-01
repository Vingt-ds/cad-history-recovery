import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PROJECT_ROOT / "benchmarks" / "case_matrix.json"
GENERATOR_PATH = PROJECT_ROOT / "external" / "benchmark_generator.py"
ATTRIBUTES_PATH = PROJECT_ROOT / ".gitattributes"
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import benchmark_generator


class BenchmarkMatrixFileTests(unittest.TestCase):
    def load_matrix(self):
        self.assertTrue(MATRIX_PATH.is_file(), "Gate 1 requires benchmarks/case_matrix.json")
        return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    def test_case_matrix_file_exists(self):
        self.assertTrue(MATRIX_PATH.is_file(), "Gate 1 requires benchmarks/case_matrix.json")

    def test_case_matrix_has_frozen_partition_counts(self):
        data = self.load_matrix()
        cases = data["cases"]
        self.assertEqual(len(cases), 30)
        self.assertEqual(Counter(case["split"] for case in cases), {"development": 15, "held_out": 15})
        self.assertEqual(Counter(case["source"] for case in cases), {"cadquery": 27, "fusion_manual": 3})

    def test_case_ids_and_output_paths_are_unique(self):
        data = self.load_matrix()
        case_ids = [case["case_id"] for case in data["cases"]]
        output_paths = [case["output_step"] for case in data["cases"]]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(len(output_paths), len(set(output_paths)))

    def test_special_held_out_behaviors_are_explicit(self):
        data = self.load_matrix()
        by_id = {case["case_id"]: case for case in data["cases"]}
        self.assertEqual(
            by_id["T-C01"]["expected_behavior"],
            "detect_ambiguity_and_emit_canonical_candidate",
        )
        self.assertEqual(by_id["T-C02"]["expected_behavior"], "reject_unsupported_fillet")
        self.assertEqual(by_id["T-C03"]["expected_behavior"], "reject_unsupported_blind_hole")

    def test_step_files_are_git_binary_to_preserve_frozen_hashes(self):
        self.assertTrue(ATTRIBUTES_PATH.is_file(), "Gate 1 requires .gitattributes")
        attributes = ATTRIBUTES_PATH.read_text(encoding="utf-8").splitlines()
        self.assertIn("*.step binary", attributes)


class BenchmarkGeneratorContractTests(unittest.TestCase):
    def test_generator_module_exists(self):
        self.assertTrue(GENERATOR_PATH.is_file(), "Gate 1 requires external/benchmark_generator.py")

    def test_matrix_validator_function_exists(self):
        self.assertTrue(callable(getattr(benchmark_generator, "load_and_validate_matrix", None)))

    def test_generate_case_function_exists(self):
        self.assertTrue(callable(getattr(benchmark_generator, "generate_case", None)))

    def test_load_and_validate_matrix_accepts_fixed_30_case_contract(self):
        try:
            data = benchmark_generator.load_and_validate_matrix(MATRIX_PATH)
        except NotImplementedError:
            self.fail("load_and_validate_matrix is not implemented")
        self.assertEqual(len(data["cases"]), 30)
        self.assertEqual(set(data["frames"]), {"XY", "XZ", "YZ", "RX30", "RY45"})

    def test_generate_case_creates_valid_axis_aligned_box_step(self):
        import cadquery as cq

        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        case = next(item for item in data["cases"] if item["case_id"] == "D-S01")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "D-S01.step"
            try:
                record = benchmark_generator.generate_case(case, data["frames"], output_path)
            except NotImplementedError:
                self.fail("generate_case is not implemented")
            imported = cq.importers.importStep(str(output_path))
            solids = imported.solids().vals()
            self.assertEqual(len(solids), 1)
            self.assertTrue(solids[0].isValid())
            self.assertEqual(len(solids[0].Faces()), 6)
            self.assertEqual(record["status"], "generated")


if __name__ == "__main__":
    unittest.main()
