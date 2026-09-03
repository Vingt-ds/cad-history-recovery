import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
