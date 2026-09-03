import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import calibrate_gate2
import candidate_validation
import geometry_validation
import profile_reconstruction


class CandidateValidationTests(unittest.TestCase):
    def step(self, case_id):
        return PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"

    @staticmethod
    def diagnostic_protocol():
        return {
            "protocol_schema": "gate2-validation-0.1",
            "hard_conditions": {
                "volume_absolute_tolerance_mm3": 1e-6,
                "volume_relative_tolerance": 1e-9,
                "bbox_coordinate_tolerance_mm": 1e-6,
            },
            "surface": {"mode": "diagnostic_only"},
            "sampling": {"total_budget": 4096, "minimum_per_face": 32},
        }

    def test_non_rectangular_sequence_rebuild_passes_hard_geometry_checks(self):
        sequence = profile_reconstruction.recover_sequence(self.step("D-S04"), "D-S04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.step"
            result = candidate_validation.validate_sequence_candidate(
                self.step("D-S04"), sequence, output, self.diagnostic_protocol()
            )
        self.assertTrue(result["valid_single_solid"])
        self.assertTrue(result["volume_pass"])
        self.assertTrue(result["bbox_pass"])
        self.assertTrue(result["geometry_pass"])
        self.assertEqual(result["surface_pass"], None)
        self.assertEqual(result["surface_mode"], "diagnostic_only")

    def test_inference_validation_returns_the_single_import_fact_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            result = candidate_validation.validate_inferred_candidates(
                self.step("D-S04"),
                "D-S04",
                Path(directory),
                self.diagnostic_protocol(),
            )
        summary = result["brep_summary"]
        self.assertEqual(summary["model_id"], "D-S04")
        self.assertEqual(summary["source_step_sha256"], result["source_step_sha256"])
        self.assertNotIn("run_id", summary)

    def test_final_ranking_is_deterministic_and_marks_multiple_qualified_candidates_ambiguous(self):
        candidates = [
            self.validated("candidate-b", 20.0, 4, 0.0, 0.0, 0.02),
            self.validated("candidate-a", 40.0, 4, 0.0, 0.0, 0.01),
            self.validated("candidate-c", 10.0, 3, 1.0, 0.0, 0.0, passed=False),
        ]
        result = candidate_validation.rank_validated_candidates(candidates)
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["qualified_candidate_count"], 2)
        self.assertEqual(result["selected_candidate_id"], "candidate-a")
        self.assertEqual([item["candidate_id"] for item in result["candidates"]], ["candidate-a", "candidate-b", "candidate-c"])

    def test_box_candidates_are_rebuilt_before_final_ambiguity_and_distance_tiebreak(self):
        with tempfile.TemporaryDirectory() as directory:
            result = candidate_validation.validate_inferred_candidates(
                self.step("D-S01"),
                "D-S01",
                Path(directory),
                self.diagnostic_protocol(),
            )
        self.assertEqual(result["ranking"]["qualified_candidate_count"], 3)
        self.assertTrue(result["ranking"]["ambiguous"])
        selected_id = result["ranking"]["selected_candidate_id"]
        selected = next(
            item for item in result["ranking"]["candidates"] if item["candidate_id"] == selected_id
        )
        self.assertEqual(selected["distance_mm"], 20.0)
        self.assertTrue(all(item["validation"]["geometry_pass"] for item in result["ranking"]["candidates"]))

    def test_surface_diagnostics_are_repeatable_across_independent_exports(self):
        runs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                result = candidate_validation.validate_inferred_candidates(
                    self.step("D-S01"),
                    "D-S01",
                    Path(directory),
                    self.diagnostic_protocol(),
                )
                runs.append(
                    [
                        (item["candidate_id"], item["validation"]["surface_sort_value"])
                        for item in result["ranking"]["candidates"]
                    ]
                )
        self.assertEqual(runs[0], runs[1])

    def test_controlled_translation_preserves_volume_and_changes_bbox(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "translated.step"
            calibrate_gate2.write_controlled_translation(self.step("D-S01"), output, 5.0)
            source = geometry_validation.inspect_step(self.step("D-S01"))
            translated = geometry_validation.inspect_step(output)
        self.assertAlmostEqual(source["volume_mm3"], translated["volume_mm3"], places=6)
        self.assertAlmostEqual(translated["bbox_mm"]["xmin"] - source["bbox_mm"]["xmin"], 5.0, places=8)

    def test_existing_replay_step_is_validated_without_rebuilding_it(self):
        replay = (
            PROJECT_ROOT
            / "logs"
            / "gate2"
            / "day5"
            / "D-S04"
            / "candidate_rebuilds"
            / "extrusion-face-006-face-007.step"
        )
        result = candidate_validation.validate_replay_step(
            self.step("D-S04"), replay, self.diagnostic_protocol()
        )
        self.assertTrue(result["geometry_pass"])
        self.assertEqual(result["reference_sha256"], geometry_validation._sha256(self.step("D-S04")))
        self.assertEqual(result["rebuild_sha256"], geometry_validation._sha256(replay))

    @staticmethod
    def validated(candidate_id, distance, primitive_count, volume_error, bbox_error, surface, passed=True):
        return {
            "candidate_id": candidate_id,
            "distance_mm": distance,
            "primitive_count": primitive_count,
            "validation": {
                "geometry_pass": passed,
                "volume_error_mm3": volume_error,
                "bbox_max_coordinate_error_mm": bbox_error,
                "surface_sort_value": surface,
            },
        }


class Gate2CalibrationProtocolTests(unittest.TestCase):
    def test_frozen_protocol_is_git_binary_to_preserve_checksum(self):
        attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("config/gate2_validation_protocol.json binary", attributes)

    def test_frozen_protocol_matches_checksum_and_calibration_contract(self):
        protocol_path = PROJECT_ROOT / "config" / "gate2_validation_protocol.json"
        checksum_path = PROJECT_ROOT / "config" / "gate2_validation_protocol.json.sha256"
        protocol_bytes = protocol_path.read_bytes()
        protocol = json.loads(protocol_bytes)

        self.assertEqual(hashlib.sha256(protocol_bytes).hexdigest(), checksum_path.read_text().strip())
        self.assertTrue(protocol["frozen"])
        self.assertEqual(protocol["surface"]["mode"], "threshold")
        self.assertIn("shared_by_comparison_pair", protocol["sampling"]["seed_policy"])
        self.assertEqual(len(protocol["calibration_records"]), 14)
        self.assertTrue(all(record["numeric_repeatable"] for record in protocol["calibration_records"]))

    def test_nonoverlap_freezes_midpoint_surface_thresholds(self):
        records = [
            {"kind": "roundtrip", "symmetric_p95_ratio": 0.01, "max_face_p95_ratio": 0.02},
            {"kind": "roundtrip", "symmetric_p95_ratio": 0.02, "max_face_p95_ratio": 0.03},
            {"kind": "perturbation", "symmetric_p95_ratio": 0.08, "max_face_p95_ratio": 0.10},
            {"kind": "perturbation", "symmetric_p95_ratio": 0.09, "max_face_p95_ratio": 0.11},
        ]
        surface = calibrate_gate2.derive_surface_protocol(records)
        self.assertEqual(surface["mode"], "threshold")
        self.assertAlmostEqual(surface["symmetric_p95_ratio_threshold"], 0.05)
        self.assertAlmostEqual(surface["max_face_p95_ratio_threshold"], 0.065)

    def test_overlap_forces_surface_metric_to_diagnostic_only(self):
        records = [
            {"kind": "roundtrip", "symmetric_p95_ratio": 0.05, "max_face_p95_ratio": 0.07},
            {"kind": "perturbation", "symmetric_p95_ratio": 0.04, "max_face_p95_ratio": 0.09},
        ]
        surface = calibrate_gate2.derive_surface_protocol(records)
        self.assertEqual(surface, {"mode": "diagnostic_only", "reason": "normalized_intervals_overlap"})

    def test_protocol_writer_refuses_to_overwrite_frozen_file(self):
        protocol = {
            "protocol_schema": "gate2-validation-0.1",
            "frozen": True,
            "surface": {"mode": "diagnostic_only"},
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "protocol.json"
            calibrate_gate2.write_frozen_protocol(protocol, output)
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                calibrate_gate2.write_frozen_protocol(protocol, output)


if __name__ == "__main__":
    unittest.main()
