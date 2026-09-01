import json
import shutil
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
    def load_case(self, case_id):
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        case = next(item for item in data["cases"] if item["case_id"] == case_id)
        return data, case

    def generate_temp_case(self, case_id):
        import cadquery as cq

        data, case = self.load_case(case_id)
        directory = tempfile.TemporaryDirectory()
        output_path = Path(directory.name) / f"{case_id}.step"
        try:
            record = benchmark_generator.generate_case(case, data["frames"], output_path)
        except benchmark_generator.MatrixError as error:
            directory.cleanup()
            self.fail(f"{case_id} generation is not implemented: {error}")
        imported = cq.importers.importStep(str(output_path))
        return directory, record, imported.solids().val()

    def test_generator_module_exists(self):
        self.assertTrue(GENERATOR_PATH.is_file(), "Gate 1 requires external/benchmark_generator.py")

    def test_matrix_validator_function_exists(self):
        self.assertTrue(callable(getattr(benchmark_generator, "load_and_validate_matrix", None)))

    def test_generate_case_function_exists(self):
        self.assertTrue(callable(getattr(benchmark_generator, "generate_case", None)))

    def test_generate_all_function_exists(self):
        self.assertTrue(callable(getattr(benchmark_generator, "generate_all", None)))

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
            self.assertIn("volume_mm3", record)
            self.assertAlmostEqual(record["volume_mm3"], 60 * 40 * 20, places=6)
            self.assertIn("volume_relative_error", record)
            self.assertLess(record["volume_relative_error"], 1e-9)

    def test_generate_case_creates_valid_through_hole_step(self):
        directory, record, solid = self.generate_temp_case("D-H01")
        try:
            self.assertTrue(solid.isValid())
            self.assertEqual(len(solid.Faces()), 7)
            self.assertLess(solid.Volume(), 55 * 38 * 20)
            self.assertEqual(record["status"], "generated")
            self.assertIn("volume_mm3", record)
            self.assertAlmostEqual(
                record["volume_mm3"],
                55 * 38 * 20 - 3.141592653589793 * 5 ** 2 * 20,
                places=5,
            )
            self.assertIn("volume_relative_error", record)
            self.assertLess(record["volume_relative_error"], 1e-9)
        finally:
            directory.cleanup()

    def test_generate_case_creates_ambiguous_cube_source_geometry(self):
        directory, record, solid = self.generate_temp_case("T-C01")
        try:
            self.assertTrue(solid.isValid())
            self.assertEqual(len(solid.Faces()), 6)
            self.assertAlmostEqual(solid.Volume(), 20 ** 3, places=6)
            self.assertEqual(record["status"], "generated")
        finally:
            directory.cleanup()

    def test_generate_case_creates_unsupported_filleted_source_geometry(self):
        directory, record, solid = self.generate_temp_case("T-C02")
        try:
            self.assertTrue(solid.isValid())
            self.assertGreater(len(solid.Faces()), 6)
            self.assertLess(solid.Volume(), 40 * 30 * 20)
            self.assertEqual(record["status"], "generated")
        finally:
            directory.cleanup()

    def test_generate_all_refuses_to_run_after_benchmark_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock_path = root / "benchmarks" / "freeze.lock.json"
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text("{}", encoding="utf-8")
            try:
                benchmark_generator.generate_all(MATRIX_PATH, root)
            except NotImplementedError:
                self.fail("generate_all is not implemented")
            except benchmark_generator.MatrixError as error:
                self.assertIn("lock", str(error).lower())
            else:
                self.fail("generate_all must refuse to run after benchmark freeze")

    def test_generate_all_creates_27_generated_and_one_existing_manual_step(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "models" / "manual_box_hole.step"
            source.parent.mkdir(parents=True)
            shutil.copy2(PROJECT_ROOT / "models" / "manual_box_hole.step", source)
            try:
                records = benchmark_generator.generate_all(MATRIX_PATH, root)
            except NotImplementedError:
                self.fail("generate_all is not implemented")

            status_counts = Counter(record["status"] for record in records)
            self.assertEqual(
                status_counts,
                {"generated": 27, "copied_manual": 1, "pending_manual": 2},
            )
            self.assertEqual(len(list((root / "benchmarks" / "inputs").rglob("*.step"))), 28)
            self.assertEqual(len(list((root / "benchmarks" / "thumbnails").glob("*.svg"))), 28)
            self.assertTrue((root / "benchmarks" / "generation_report.json").is_file())
            self.assertTrue((root / "benchmarks" / "contact_sheet.html").is_file())
            self.assertTrue(
                all(not Path(record["output_step"]).is_absolute() for record in records),
                "generation report paths must remain repository-relative",
            )

    def test_generate_all_recognizes_completed_manual_pending_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate0_source = root / "models" / "manual_box_hole.step"
            gate0_source.parent.mkdir(parents=True)
            shutil.copy2(PROJECT_ROOT / "models" / "manual_box_hole.step", gate0_source)

            held_out = root / "benchmarks" / "inputs" / "held_out"
            held_out.mkdir(parents=True)
            for case_id in ("T-H04", "T-C03"):
                shutil.copy2(
                    PROJECT_ROOT / "benchmarks" / "inputs" / "held_out" / f"{case_id}.step",
                    held_out / f"{case_id}.step",
                )

            records = benchmark_generator.generate_all(MATRIX_PATH, root)
            status_counts = Counter(record["status"] for record in records)
            self.assertEqual(
                status_counts,
                {"generated": 27, "copied_manual": 1, "existing_manual": 2},
            )
            self.assertEqual(len(list((root / "benchmarks" / "inputs").rglob("*.step"))), 30)
            self.assertEqual(len(list((root / "benchmarks" / "thumbnails").glob("*.svg"))), 30)
            self.assertNotIn("PENDING MANUAL FUSION MODEL", (root / "benchmarks" / "contact_sheet.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
