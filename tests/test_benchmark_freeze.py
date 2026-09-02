import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import freeze_benchmark


class BenchmarkFreezeTests(unittest.TestCase):
    def make_benchmark(self, root):
        cases = []
        for index in range(30):
            split = "development" if index < 15 else "held_out"
            case_id = f"X-{index:02d}"
            relative = f"benchmarks/inputs/{split}/{case_id}.step"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"step-{index}".encode("ascii"))
            cases.append(
                {
                    "case_id": case_id,
                    "split": split,
                    "source": "cadquery",
                    "expected_scope": "supported",
                    "expected_behavior": "reconstruct_automatically",
                    "output_step": relative,
                }
            )
        matrix_path = root / "benchmarks" / "case_matrix.json"
        matrix_path.write_text(
            json.dumps(
                {
                    "matrix_version": "gate1-draft-0.1",
                    "units": "mm",
                    "frozen": False,
                    "cases": cases,
                }
            ),
            encoding="utf-8",
        )
        return matrix_path

    def test_freeze_writes_manifest_hashes_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = self.make_benchmark(root)
            original_line_count = len(matrix_path.read_text(encoding="utf-8").splitlines())
            result = freeze_benchmark.freeze_benchmark(matrix_path, root)
            manifest_path = root / "benchmarks" / "manifest.json"
            lock_path = root / "benchmarks" / "freeze.lock.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lock = json.loads(lock_path.read_text(encoding="utf-8"))

            self.assertTrue(matrix["frozen"])
            self.assertEqual(matrix["matrix_version"], "gate1-frozen-0.1")
            self.assertEqual(len(manifest["cases"]), 30)
            self.assertEqual(manifest["split_counts"], {"development": 15, "held_out": 15})
            self.assertTrue(all(len(case["sha256"]) == 64 for case in manifest["cases"]))
            self.assertEqual(lock["manifest_sha256"], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
            self.assertEqual(result["manifest_sha256"], lock["manifest_sha256"])
            self.assertLessEqual(
                len(matrix_path.read_text(encoding="utf-8").splitlines()),
                original_line_count + 1,
                "freezing must not reformat the entire case matrix",
            )

    def test_freeze_refuses_missing_step(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = self.make_benchmark(root)
            missing = root / "benchmarks" / "inputs" / "held_out" / "X-29.step"
            missing.unlink()
            with self.assertRaisesRegex(freeze_benchmark.FreezeError, "missing"):
                freeze_benchmark.freeze_benchmark(matrix_path, root)

    def test_freeze_refuses_existing_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = self.make_benchmark(root)
            lock_path = root / "benchmarks" / "freeze.lock.json"
            lock_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(freeze_benchmark.FreezeError, "already"):
                freeze_benchmark.freeze_benchmark(matrix_path, root)

    def test_repository_benchmark_is_frozen_with_matching_manifest_hash(self):
        matrix_path = PROJECT_ROOT / "benchmarks" / "case_matrix.json"
        manifest_path = PROJECT_ROOT / "benchmarks" / "manifest.json"
        lock_path = PROJECT_ROOT / "benchmarks" / "freeze.lock.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertTrue(matrix["frozen"])
        self.assertEqual(matrix["matrix_version"], "gate1-frozen-0.1")
        self.assertTrue(manifest_path.is_file())
        self.assertTrue(lock_path.is_file())
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(lock["manifest_sha256"], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        self.assertEqual(freeze_benchmark.verify_frozen_benchmark(PROJECT_ROOT), [])

    def test_verifier_detects_step_tampering_after_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = self.make_benchmark(root)
            freeze_benchmark.freeze_benchmark(matrix_path, root)
            changed = root / "benchmarks" / "inputs" / "development" / "X-00.step"
            changed.write_bytes(b"tampered")
            errors = freeze_benchmark.verify_frozen_benchmark(root)
            self.assertTrue(any("X-00" in error and "sha256" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
