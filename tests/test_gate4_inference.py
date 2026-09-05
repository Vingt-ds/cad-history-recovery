import importlib
import hashlib
import inspect
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cadquery as cq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

import brep_inspection
import gate4_inference
import through_hole_inference
import topology_adjacency


class Gate4InferenceArtifactTests(unittest.TestCase):
    def test_content_driven_inference_module_exists(self):
        self.assertTrue((EXTERNAL / "gate4_inference.py").is_file())

    def test_public_api_exposes_no_case_identifier_argument(self):
        module = importlib.import_module("gate4_inference")
        parameters = list(inspect.signature(module.inspect_and_infer_step).parameters)
        self.assertEqual(
            parameters,
            [
                "step_path",
                "source_sha256",
                "work_dir",
                "gate2_protocol",
                "gate3_protocol",
            ],
        )


class FactDrivenRoutingTests(unittest.TestCase):
    def _route_for(self, case_id):
        path = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / f"{case_id}.step"
        summary, context = brep_inspection.inspect_step_with_context(path, "content-shape")
        adjacency = topology_adjacency.build_adjacency(summary, context)
        facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
        return gate4_inference.classify_route(summary, facts)

    def test_supported_through_hole_routes_to_gate3(self):
        route = self._route_for("D-H01")
        self.assertEqual(route["route"], "gate3")
        self.assertEqual(route["supported_hole_group_count"], 1)

    def test_solid_cylinder_routes_to_gate2_not_gate3(self):
        route = self._route_for("D-S07")
        self.assertEqual(route["route"], "gate2")
        self.assertFalse(route["inner_circular_opening_evidence"])

    def test_cylindrical_boss_never_routes_to_gate3(self):
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
            summary, context = brep_inspection.inspect_step_with_context(path, "content-shape")
            adjacency = topology_adjacency.build_adjacency(summary, context)
            facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        route = gate4_inference.classify_route(summary, facts)
        self.assertNotEqual(route["route"], "gate3")

    def test_blind_hole_is_hole_like_but_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blind.step"
            shape = cq.Workplane("XY").box(50, 35, 20).faces(">Z").workplane().hole(10, 8)
            cq.exporters.export(shape, str(path))
            summary, context = brep_inspection.inspect_step_with_context(path, "content-shape")
            adjacency = topology_adjacency.build_adjacency(summary, context)
            facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        route = gate4_inference.classify_route(summary, facts)
        self.assertEqual(route["route"], "unsupported")

    def test_two_through_holes_are_unsupported_not_gate3(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_holes.step"
            shape = (
                cq.Workplane("XY")
                .box(60, 40, 20)
                .faces(">Z")
                .workplane()
                .pushPoints([(-15, 0), (15, 0)])
                .hole(8)
            )
            cq.exporters.export(shape, str(path))
            summary, context = brep_inspection.inspect_step_with_context(path, "content-shape")
            adjacency = topology_adjacency.build_adjacency(summary, context)
            facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)

        route = gate4_inference.classify_route(summary, facts)
        self.assertEqual(route["route"], "unsupported")


class LabelFirewallTests(unittest.TestCase):
    @staticmethod
    def _protocols():
        gate2_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate2_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        gate3_protocol = json.loads(
            (PROJECT_ROOT / "config" / "gate3_validation_protocol.json").read_text(
                encoding="utf-8"
            )
        )
        return gate2_protocol, gate3_protocol

    def test_same_step_bytes_are_invariant_to_filename_and_parent_directory(self):
        source = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-H01.step"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        gate2_protocol, gate3_protocol = self._protocols()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                root / "a" / "D-S01.step",
                root / "b" / "D-H99.step",
                root / "c" / "random_abc.step",
                root / "nested" / "unsupported_case.step",
            ]
            outputs = []
            for index, path in enumerate(paths):
                path.parent.mkdir(parents=True)
                shutil.copyfile(source, path)
                outputs.append(
                    gate4_inference.inspect_and_infer_step(
                        path,
                        digest,
                        root / "work" / str(index),
                        gate2_protocol,
                        gate3_protocol,
                    )
                )

        self.assertTrue(all(output == outputs[0] for output in outputs[1:]))
        self.assertEqual(outputs[0]["route"]["route"], "gate3")
        self.assertEqual(outputs[0]["semantic_outcome"], "candidate_selected")
        self.assertEqual(outputs[0]["brep_summary"]["source_step_sha256"], digest)
        self.assertTrue(outputs[0]["candidate_generation_entered"])

    def test_plain_extrusion_uses_gate2_without_case_metadata(self):
        source = PROJECT_ROOT / "benchmarks" / "inputs" / "development" / "D-S04.step"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        gate2_protocol, gate3_protocol = self._protocols()
        with tempfile.TemporaryDirectory() as directory:
            result = gate4_inference.inspect_and_infer_step(
                source,
                digest,
                Path(directory),
                gate2_protocol,
                gate3_protocol,
            )

        self.assertEqual(result["route"]["route"], "gate2")
        self.assertEqual(result["semantic_outcome"], "candidate_selected")
        self.assertIsNotNone(result["selected_sequence"])
        self.assertEqual(result["brep_summary"]["source_step_sha256"], digest)
        self.assertTrue(result["candidate_generation_entered"])

    def test_filleted_extrusion_returns_unsupported_without_expected_label(self):
        gate2_protocol, gate3_protocol = self._protocols()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "neutral_name.step"
            shape = cq.Workplane("XY").box(40, 30, 20).edges().fillet(3)
            cq.exporters.export(shape, str(path))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result = gate4_inference.inspect_and_infer_step(
                path,
                digest,
                root / "work",
                gate2_protocol,
                gate3_protocol,
            )

        self.assertEqual(result["semantic_outcome"], "unsupported")
        self.assertEqual(result["failure_code"], "NO_SUPPORTED_HYPOTHESIS")


if __name__ == "__main__":
    unittest.main()
