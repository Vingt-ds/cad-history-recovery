import copy
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "external"))

import cadquery as cq
import brep_inspection
import through_hole_inference
import topology_adjacency


DEVELOPMENT_INPUTS = PROJECT_ROOT / "benchmarks" / "inputs" / "development"


def _case_facts(case_id):
    summary, context = brep_inspection.inspect_step_with_context(
        DEVELOPMENT_INPUTS / f"{case_id}.step",
        case_id,
    )
    adjacency = topology_adjacency.build_adjacency(summary, context)
    return summary, adjacency


def _all_keys(value):
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(_all_keys(child))
        return keys
    if isinstance(value, list):
        keys = set()
        for child in value:
            keys.update(_all_keys(child))
        return keys
    return set()


class ThroughHoleInferenceArtifactTests(unittest.TestCase):
    def test_checkpoint1_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("through_hole_inference"))

    def test_checkpoint1_public_api_exists(self):
        import through_hole_inference

        self.assertTrue(hasattr(through_hole_inference, "analyze_through_hole_facts"))

    def test_checkpoint1_structured_error_exists(self):
        import through_hole_inference

        self.assertTrue(hasattr(through_hole_inference, "ThroughHoleInferenceError"))

    def test_checkpoint2_public_api_exists(self):
        import through_hole_inference

        self.assertTrue(hasattr(through_hole_inference, "generate_coupled_candidates"))


class Gate3DevelopmentInputBoundaryTests(unittest.TestCase):
    def test_selector_derives_only_frozen_development_through_holes(self):
        cases = through_hole_inference.load_gate3_development_cases(PROJECT_ROOT)

        self.assertEqual(
            [case["case_id"] for case in cases],
            [f"D-H{index:02d}" for index in range(1, 6)],
        )
        allowed_keys = {"case_id", "split", "family", "output_step", "source", "units"}
        for case in cases:
            self.assertEqual(set(case), allowed_keys)
            self.assertEqual(case["split"], "development")
            self.assertEqual(case["family"], "through_hole")

    def test_input_guard_rejects_held_out_path_without_reading_geometry(self):
        held_out_path = (
            PROJECT_ROOT / "benchmarks" / "inputs" / "held_out" / "T-H01.step"
        )

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.validate_gate3_development_input(
                PROJECT_ROOT,
                "D-H01",
                held_out_path,
            )

        self.assertEqual(raised.exception.code, "held_out_input_forbidden")

    def test_input_guard_rejects_path_outside_frozen_development_inputs(self):
        outside_path = PROJECT_ROOT / "models" / "manual_box_hole.step"

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.validate_gate3_development_input(
                PROJECT_ROOT,
                "D-H01",
                outside_path,
            )

        self.assertEqual(raised.exception.code, "input_not_frozen_development")

    def test_input_guard_rejects_case_id_path_mismatch(self):
        d_h02_path = DEVELOPMENT_INPUTS / "D-H02.step"

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.validate_gate3_development_input(
                PROJECT_ROOT,
                "D-H01",
                d_h02_path,
            )

        self.assertEqual(raised.exception.code, "case_id_path_mismatch")


class ThroughHoleFactAnalysisTests(unittest.TestCase):
    def test_wrong_fact_schema_is_rejected_before_analysis(self):
        summary, adjacency = _case_facts("D-H01")
        for artifact, field in (
            (summary, "brep_summary_schema"),
            (adjacency, "adjacency_schema"),
        ):
            with self.subTest(field=field):
                changed_summary = copy.deepcopy(summary)
                changed_adjacency = copy.deepcopy(adjacency)
                target = changed_summary if artifact is summary else changed_adjacency
                target[field] = "future-schema"
                with self.assertRaisesRegex(
                    through_hole_inference.ThroughHoleInferenceError,
                    "unsupported_fact_schema",
                ):
                    through_hole_inference.analyze_through_hole_facts(
                        changed_summary,
                        changed_adjacency,
                    )

    def test_mismatched_summary_and_adjacency_are_rejected_before_analysis(self):
        summary, adjacency = _case_facts("D-H01")
        for field, value in (
            ("model_id", "different-model"),
            ("source_step_sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                mismatched = copy.deepcopy(adjacency)
                mismatched[field] = value
                with self.assertRaisesRegex(
                    through_hole_inference.ThroughHoleInferenceError,
                    "summary_adjacency_mismatch",
                ):
                    through_hole_inference.analyze_through_hole_facts(summary, mismatched)

    def test_d_h01_identifies_line_outer_wires_and_one_paired_hole_group(self):
        summary, adjacency = _case_facts("D-H01")

        report = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        self.assertEqual(report.get("through_hole_facts_schema"), "through-hole-facts-0.1")
        self.assertEqual(len(report.get("planar_wire_roles", [])), 2)
        for role in report.get("planar_wire_roles", []):
            self.assertEqual(role.get("outer_wire_kind"), "line_only")
            self.assertEqual(len(role.get("inner_circle_wire_ids", [])), 1)
            self.assertTrue(all(check["passed"] for check in role.get("checks", [])))
        accepted = [
            group for group in report.get("hole_fact_groups", [])
            if group.get("status") == "accepted"
        ]
        self.assertEqual(len(accepted), 1)
        group = accepted[0]
        self.assertEqual(len(set(group["circle_edge_ids"])), 2)
        self.assertEqual(len(set(group["inner_wire_ids"])), 2)
        self.assertEqual(len(set(group["planar_face_ids"])), 2)
        self.assertTrue(all(check["passed"] for check in group["checks"]))

    def test_all_five_development_holes_have_one_deterministic_fact_group(self):
        for case_id in ("D-H01", "D-H02", "D-H03", "D-H04", "D-H05"):
            with self.subTest(case_id=case_id):
                summary, adjacency = _case_facts(case_id)
                first = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
                second = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
                accepted = [
                    group for group in first.get("hole_fact_groups", [])
                    if group.get("status") == "accepted"
                ]
                self.assertEqual(len(accepted), 1)
                self.assertEqual(
                    json.dumps(first, sort_keys=True, separators=(",", ":")),
                    json.dumps(second, sort_keys=True, separators=(",", ":")),
                )

    def test_wire_role_does_not_depend_on_face_wire_traversal_order(self):
        summary, adjacency = _case_facts("D-H01")
        reordered = copy.deepcopy(summary)
        for face in reordered["solids"][0]["faces"]:
            face["wire_uses"].reverse()

        original = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        changed = through_hole_inference.analyze_through_hole_facts(reordered, adjacency)

        self.assertEqual(original.get("planar_wire_roles"), changed.get("planar_wire_roles"))
        self.assertEqual(original.get("hole_fact_groups"), changed.get("hole_fact_groups"))

    def test_adjacency_convexity_is_diagnostic_not_an_acceptance_condition(self):
        summary, adjacency = _case_facts("D-H01")
        relabelled = copy.deepcopy(adjacency)
        for relation in relabelled["relations"]:
            relation["classification"] = (
                "concave" if relation["classification"] == "convex" else "convex"
            )

        original = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        changed = through_hole_inference.analyze_through_hole_facts(summary, relabelled)

        self.assertEqual(
            [group.get("status") for group in original.get("hole_fact_groups", [])],
            [group.get("status") for group in changed.get("hole_fact_groups", [])],
        )

    def test_controlled_cylindrical_boss_is_not_accepted_as_a_through_hole(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controlled_boss.step"
            boss = (
                cq.Workplane("XY")
                .box(55.0, 38.0, 20.0)
                .faces(">Z")
                .workplane()
                .circle(5.0)
                .extrude(8.0)
            )
            cq.exporters.export(boss, str(path))
            summary, context = brep_inspection.inspect_step_with_context(path, "controlled-boss")
            adjacency = topology_adjacency.build_adjacency(summary, context)

            report = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        self.assertFalse(
            any(group.get("status") == "accepted" for group in report.get("hole_fact_groups", []))
        )
        group = report["hole_fact_groups"][0]
        self.assertEqual(
            group["rejection_reasons"],
            [check["reason"] for check in group["checks"] if not check["passed"]],
        )
        self.assertIn("no_accepted_hole_fact_group", report.get("rejection_reasons", []))

    def test_box_without_cylinder_has_structured_rejection_and_no_future_stage_fields(self):
        summary, adjacency = _case_facts("D-S01")

        report = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        self.assertEqual(report.get("hole_fact_groups"), [])
        self.assertIn("no_cylindrical_face", report.get("rejection_reasons", []))
        self.assertTrue(
            _all_keys(report).isdisjoint(
                {"sequence", "cut", "candidate_rank", "fusion", "correction", "final_status"}
            )
        )


class CoupledCandidateTests(unittest.TestCase):
    def test_candidate_generation_rejects_wrong_summary_or_adjacency_schema(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        for artifact, field in (
            ("summary", "brep_summary_schema"),
            ("adjacency", "adjacency_schema"),
        ):
            with self.subTest(artifact=artifact):
                changed_summary = copy.deepcopy(summary)
                changed_adjacency = copy.deepcopy(adjacency)
                target = changed_summary if artifact == "summary" else changed_adjacency
                target[field] = "future-schema"

                with self.assertRaises(
                    through_hole_inference.ThroughHoleInferenceError
                ) as raised:
                    through_hole_inference.generate_coupled_candidates(
                        changed_summary,
                        changed_adjacency,
                        facts,
                    )

                self.assertEqual(raised.exception.code, "candidate_input_schema_mismatch")

    def test_candidate_generation_rejects_mismatched_hole_fact_artifact(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        for field, value in (
            ("through_hole_facts_schema", "future-schema"),
            ("model_id", "different-model"),
            ("source_step_sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(facts)
                changed[field] = value
                with self.assertRaisesRegex(
                    through_hole_inference.ThroughHoleInferenceError,
                    "hole_facts_mismatch",
                ):
                    through_hole_inference.generate_coupled_candidates(
                        summary,
                        adjacency,
                        changed,
                    )

    def test_candidate_generation_wraps_malformed_accepted_group_or_roles(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        malformed = copy.deepcopy(facts)
        required_face_id = malformed["hole_fact_groups"][0]["planar_face_ids"][0]
        malformed["planar_wire_roles"] = [
            role for role in malformed["planar_wire_roles"]
            if role["face_id"] != required_face_id
        ]

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.generate_coupled_candidates(
                summary,
                adjacency,
                malformed,
            )

        self.assertEqual(raised.exception.code, "malformed_candidate_facts")

    def test_candidate_generation_rejects_missing_circle_edge_reference(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        malformed = copy.deepcopy(facts)
        malformed["hole_fact_groups"][0]["circle_edge_ids"][0] = "edge-missing"

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.generate_coupled_candidates(
                summary,
                adjacency,
                malformed,
            )

        self.assertEqual(raised.exception.code, "malformed_candidate_facts")

    def test_candidate_generation_rejects_nonnumeric_measured_axis(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        malformed = copy.deepcopy(facts)
        malformed["hole_fact_groups"][0]["measured_axis"] = ["not-numeric", 0.0, 1.0]

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.generate_coupled_candidates(
                summary,
                adjacency,
                malformed,
            )

        self.assertEqual(raised.exception.code, "malformed_candidate_facts")

    def test_candidate_generation_rejects_circle_wire_used_as_outer_wire(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        malformed = copy.deepcopy(facts)
        malformed["planar_wire_roles"][0]["outer_wire_id"] = (
            malformed["planar_wire_roles"][0]["inner_circle_wire_ids"][0]
        )

        with self.assertRaises(through_hole_inference.ThroughHoleInferenceError) as raised:
            through_hole_inference.generate_coupled_candidates(
                summary,
                adjacency,
                malformed,
            )

        self.assertEqual(raised.exception.code, "malformed_candidate_facts")

    def test_candidate_generation_does_not_mask_internal_type_error(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        with mock.patch.object(
            through_hole_inference,
            "_coupled_candidate",
            side_effect=TypeError("internal regression"),
        ):
            with self.assertRaisesRegex(TypeError, "^internal regression$"):
                through_hole_inference.generate_coupled_candidates(
                    summary,
                    adjacency,
                    facts,
                )

    def test_five_development_cases_have_one_correct_base_hole_candidate(self):
        expected_distances = {
            "D-H01": 20.0,
            "D-H02": 24.0,
            "D-H03": 18.0,
            "D-H04": 21.0,
            "D-H05": 20.0,
        }
        for case_id, expected_distance in expected_distances.items():
            with self.subTest(case_id=case_id):
                summary, adjacency = _case_facts(case_id)
                facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

                report = through_hole_inference.generate_coupled_candidates(
                    summary,
                    adjacency,
                    facts,
                )

                self.assertEqual(
                    report.get("coupled_candidates_schema"),
                    "coupled-through-hole-candidates-0.1",
                )
                accepted = [
                    candidate for candidate in report.get("candidates", [])
                    if candidate.get("status") == "accepted"
                ]
                self.assertEqual(len(accepted), 1)
                candidate = accepted[0]
                self.assertAlmostEqual(candidate["base"]["distance_mm"], expected_distance, places=6)
                self.assertTrue(all(check["passed"] for check in candidate["checks"]))
                self.assertEqual(
                    set(candidate["base"]["end_face_ids"]),
                    set(candidate["hole"]["planar_face_ids"]),
                )

    def test_zero_centroid_separation_returns_structured_rejected_candidate(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        changed = copy.deepcopy(summary)
        end_face_ids = facts["hole_fact_groups"][0]["planar_face_ids"]
        face_by_id = {
            face["face_id"]: face
            for face in changed["solids"][0]["faces"]
        }
        face_by_id[end_face_ids[1]]["centroid_mm"] = list(
            face_by_id[end_face_ids[0]]["centroid_mm"]
        )

        candidate = through_hole_inference.generate_coupled_candidates(
            changed,
            adjacency,
            facts,
        )["candidates"][0]

        positive_distance = next(
            check for check in candidate["checks"]
            if check["name"] == "positive_base_distance"
        )
        self.assertEqual(candidate["status"], "rejected")
        self.assertFalse(positive_distance["passed"])
        self.assertEqual(positive_distance["reason"], "base_distance_not_positive")
        self.assertEqual(
            candidate["rejection_reasons"],
            [check["reason"] for check in candidate["checks"] if not check["passed"]],
        )
        json.dumps(candidate, allow_nan=False)

    def test_outer_wire_matching_excludes_inner_circle_edges_and_side_face_pairs(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        report = through_hole_inference.generate_coupled_candidates(summary, adjacency, facts)

        self.assertEqual(len(report.get("candidates", [])), 1)
        candidate = report["candidates"][0]
        matched = candidate["base"]["matched_outer_edge_pairs"]
        self.assertEqual(len(matched), 4)
        matched_edge_ids = {edge_id for pair in matched for edge_id in pair}
        self.assertTrue(matched_edge_ids.isdisjoint(candidate["hole"]["circle_edge_ids"]))
        self.assertEqual(
            set(candidate["base"]["end_face_ids"]),
            set(facts["hole_fact_groups"][0]["planar_face_ids"]),
        )

    def test_semantic_cap_and_cut_direction_are_derived_from_normalized_base_direction(self):
        summary, adjacency = _case_facts("D-H04")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        report = through_hole_inference.generate_coupled_candidates(
            summary,
            adjacency,
            facts,
        )
        self.assertTrue(report.get("candidates"))
        candidate = report["candidates"][0]

        base_direction = candidate["base"]["extrusion_direction"]
        cut_direction = candidate["semantic_replay"]["cut_direction"]
        self.assertEqual(candidate["semantic_replay"]["operation_cap"]["role"], "positive_end_cap")
        self.assertAlmostEqual(sum(a * b for a, b in zip(base_direction, cut_direction)), -1.0)
        self.assertGreater(candidate["base"]["distance_mm"], 0.0)

    def test_cut_direction_hard_check_is_measured_against_support_face_normal(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        changed = copy.deepcopy(summary)
        support_face_id = sorted(facts["hole_fact_groups"][0]["planar_face_ids"])[1]
        support_face = next(
            face for face in changed["solids"][0]["faces"]
            if face["face_id"] == support_face_id
        )
        support_face["surface_parameters"]["normal"] = [1.0, 0.0, 0.0]

        candidate = through_hole_inference.generate_coupled_candidates(
            changed,
            adjacency,
            facts,
        )["candidates"][0]

        direction_check = next(
            check for check in candidate["checks"]
            if check["name"] == "cut_direction_into_material_from_support_face"
        )
        self.assertEqual(candidate["semantic_replay"]["support_face_id"], support_face_id)
        self.assertEqual(candidate["semantic_replay"]["cut_direction"], [0.0, 0.0, -1.0])
        self.assertEqual(direction_check["measurement"]["support_face_outward_normal"], [1.0, 0.0, 0.0])
        self.assertAlmostEqual(direction_check["measurement"]["normal_dot_cut_direction"], 0.0)
        self.assertFalse(direction_check["passed"])
        self.assertEqual(direction_check["reason"], "cut_direction_not_into_material")
        self.assertEqual(candidate["status"], "rejected")

    def test_unsupported_end_face_orientations_reject_with_finite_failed_checks(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        support_face_id = sorted(facts["hole_fact_groups"][0]["planar_face_ids"])[1]
        for unsupported in ("internal", "external", "unknown"):
            with self.subTest(orientation=unsupported):
                changed = copy.deepcopy(summary)
                support_face = next(
                    face for face in changed["solids"][0]["faces"]
                    if face["face_id"] == support_face_id
                )
                support_face["orientation"] = unsupported

                candidate = through_hole_inference.generate_coupled_candidates(
                    changed,
                    adjacency,
                    facts,
                )["candidates"][0]

                checks = {check["name"]: check for check in candidate["checks"]}
                orientation_check = checks["supported_end_face_orientations"]
                cut_check = checks["cut_direction_into_material_from_support_face"]
                self.assertEqual(candidate["status"], "rejected")
                self.assertFalse(orientation_check["passed"])
                self.assertEqual(
                    orientation_check["reason"],
                    "unsupported_end_face_orientation",
                )
                self.assertIn(
                    "unsupported_end_face_orientation",
                    candidate["rejection_reasons"],
                )
                self.assertFalse(cut_check["passed"])
                self.assertTrue(
                    math.isfinite(cut_check["measurement"]["normal_dot_cut_direction"])
                )
                json.dumps(candidate, allow_nan=False)

    def test_candidate_vectors_do_not_serialize_negative_zero(self):
        summary, adjacency = _case_facts("D-H01")
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        candidate = through_hole_inference.generate_coupled_candidates(
            summary,
            adjacency,
            facts,
        )["candidates"][0]

        for vector in (
            candidate["base"]["source_face_outward_normal"],
            candidate["base"]["extrusion_direction"],
            candidate["semantic_replay"]["cut_direction"],
        ):
            for value in vector:
                if value == 0.0:
                    self.assertGreater(math.copysign(1.0, value), 0.0)

    def test_convexity_relabelling_does_not_change_coupled_candidate_acceptance(self):
        summary, adjacency = _case_facts("D-H01")
        changed_adjacency = copy.deepcopy(adjacency)
        for relation in changed_adjacency["relations"]:
            relation["classification"] = (
                "concave" if relation["classification"] == "convex" else "convex"
            )
        original_facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        changed_facts = through_hole_inference.analyze_through_hole_facts(
            summary,
            changed_adjacency,
        )

        original = through_hole_inference.generate_coupled_candidates(
            summary,
            adjacency,
            original_facts,
        )
        changed = through_hole_inference.generate_coupled_candidates(
            summary,
            changed_adjacency,
            changed_facts,
        )

        self.assertEqual(
            [candidate.get("status") for candidate in original.get("candidates", [])],
            [candidate.get("status") for candidate in changed.get("candidates", [])],
        )

    def test_controlled_boss_produces_no_coupled_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controlled_boss.step"
            boss = (
                cq.Workplane("XY")
                .box(55.0, 38.0, 20.0)
                .faces(">Z")
                .workplane()
                .circle(5.0)
                .extrude(8.0)
            )
            cq.exporters.export(boss, str(path))
            summary, context = brep_inspection.inspect_step_with_context(path, "controlled-boss")
            adjacency = topology_adjacency.build_adjacency(summary, context)
            facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

            report = through_hole_inference.generate_coupled_candidates(
                summary,
                adjacency,
                facts,
            )

        self.assertEqual(report.get("candidates"), [])
        self.assertIn("no_accepted_hole_fact_group", report.get("rejection_reasons", []))


if __name__ == "__main__":
    unittest.main()
