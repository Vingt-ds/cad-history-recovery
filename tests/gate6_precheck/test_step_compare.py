import copy
import tempfile
import unittest
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape, TopoDS_Shell
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Pnt

from tools.gate6_precheck.contract import ContractError, load_contract
from tools.gate6_precheck.step_compare import (
    GraphNode,
    GraphRelation,
    ObservableGraph,
    classify_wire_polygons,
    compare_graphs,
    compare_steps,
    inspect_step,
    normalize_line,
    normalize_plane,
    probe_outward,
    symmetric_difference_volume,
    _canonicalize_entries,
    _add_edge_connections,
    _compare_graphs_unbound,
    _validate_shell_separation,
    _validate_shell_topology,
    _face_cells,
    _shell_contains,
    SurfaceRectangle,
)


def _write_step(shape, path):
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError('STEP transfer failed')
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError('STEP write failed')


class StepReaderTests(unittest.TestCase):
    def setUp(self):
        self.config = load_contract()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_inspect_step_roundtrip_single_box(self):
        path = self.root / 'box.step'
        _write_step(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), path)

        inspected = inspect_step(path, self.config)

        self.assertAlmostEqual(inspected.volume, 24.0, places=9)
        self.assertEqual(inspected.solid_count, 1)
        self.assertEqual(inspected.component_count, 1)
        self.assertTrue(inspected.valid)
        self.assertEqual(inspected.reader_settings, {
            'read.precision.mode': {'type': 'integer', 'value': 0},
            'read.precision.val': {'type': 'real', 'value': 0.001},
            'read.maxprecision.mode': {'type': 'integer', 'value': 0},
            'read.maxprecision.val': {'type': 'real', 'value': 1.0},
            'read.surfacecurve.mode': {'type': 'integer', 'value': 0},
            'read.step.resource.name': {'type': 'string', 'value': 'STEP'},
            'read.step.sequence': {'type': 'string', 'value': 'FromSTEP'},
            'xstep.cascade.unit': {'type': 'string', 'value': 'MM'},
        })

    def test_step_reader_policy_pollution_fails_closed_and_is_restored(self):
        path = self.root / 'box.step'
        _write_step(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), path)
        STEPControl_Writer()  # ensure shared Interface_Static resources are initialized
        original = Interface_Static.IVal_s('read.precision.mode')
        try:
            self.assertTrue(Interface_Static.SetIVal_s('read.precision.mode', 1))
            with self.assertRaises(ContractError) as caught:
                inspect_step(path, self.config)
            self.assertEqual(caught.exception.code, 'environment_mismatch')
        finally:
            Interface_Static.SetIVal_s('read.precision.mode', original)
        self.assertEqual(Interface_Static.IVal_s('read.precision.mode'), original)

    def test_inspect_step_rejects_multiple_solids(self):
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        builder.Add(compound, BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape())
        builder.Add(compound, BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape())
        path = self.root / 'two.step'
        _write_step(compound, path)

        with self.assertRaises(ContractError) as caught:
            inspect_step(path, self.config)

        self.assertEqual(caught.exception.code, 'invalid_result_solid')

    def test_inspect_step_rejects_single_solid_plus_free_edge(self):
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        builder.Add(compound, BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape())
        builder.Add(compound, BRepBuilderAPI_MakeEdge(
            gp_Pnt(3.0, 0.0, 0.0), gp_Pnt(4.0, 0.0, 0.0)
        ).Shape())
        path = self.root / 'solid-plus-edge.step'
        _write_step(compound, path)
        with self.assertRaises(ContractError) as caught:
            inspect_step(path, self.config)
        self.assertEqual(caught.exception.code, 'invalid_result_solid')

    def test_public_comparator_apis_reject_mutated_contract_first(self):
        mutated = copy.deepcopy(self.config)
        mutated['graph']['max_search_states'] = 0
        graph = ObservableGraph(nodes={0: GraphNode('Solid', {})}, relations=[])
        calls = (
            lambda: inspect_step(self.root / 'missing.step', mutated),
            lambda: compare_steps(self.root / 'missing-a.step', self.root / 'missing-b.step', mutated),
            lambda: compare_graphs(graph, graph, mutated),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(ContractError) as caught:
                    call()
                self.assertEqual(caught.exception.code, 'specification_binding_failure')


class ObservableExtractionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_contract()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def _inspect(self, shape, name):
        path = self.root / name
        _write_step(shape, path)
        return inspect_step(path, self.config)

    def test_plane_and_line_gauge_reversal_normalize_identically(self):
        self.assertEqual(
            normalize_plane((0.0, -1.0, 0.0), -3.0, self.config),
            normalize_plane((0.0, 1.0, 0.0), 3.0, self.config),
        )

    def test_gauge_sign_uses_first_component_strictly_above_zero_threshold(self):
        above = normalize_plane((2e-12, -1.0, 0.0), 3.0, self.config)
        reversed_above = normalize_plane((-2e-12, 1.0, 0.0), -3.0, self.config)
        at_boundary = normalize_plane((1e-12, -1.0, 0.0), 3.0, self.config)
        self.assertEqual(above, reversed_above)
        self.assertEqual(above, {'normal': (0.0, -1.0, 0.0), 'offset': 3.0})
        self.assertEqual(at_boundary, {'normal': (0.0, 1.0, 0.0), 'offset': -3.0})

    def test_reversed_wire_canonicalization_keeps_edge_incidence(self):
        polygon = [(0, 0), (0, 1), (1, 1), (1, 0)]
        edge_endpoints = {
            'e0': {polygon[0], polygon[1]}, 'e1': {polygon[1], polygon[2]},
            'e2': {polygon[2], polygon[3]}, 'e3': {polygon[3], polygon[0]},
        }
        entries = [(f'e{index}', point) for index, point in enumerate(polygon)]

        canonical_entries, canonical_polygon = _canonicalize_entries(entries, polygon, 1)

        for index, (edge, start) in enumerate(canonical_entries):
            end = canonical_polygon[(index + 1) % len(canonical_polygon)]
            self.assertEqual(start, canonical_polygon[index])
            self.assertEqual({start, end}, edge_endpoints[edge])
        self.assertEqual(
            normalize_line((0.0, 0.0, 1.0), (2.0, 3.0, 4.0), self.config),
            normalize_line((0.0, 0.0, -1.0), (2.0, 3.0, -7.0), self.config),
        )

    def test_box_graph_contains_all_required_topology_levels(self):
        inspected = self._inspect(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'box.step')
        node_types = [node.kind for node in inspected.graph.nodes.values()]
        self.assertEqual(node_types.count('Solid'), 1)
        self.assertEqual(node_types.count('Shell'), 1)
        self.assertEqual(node_types.count('Face'), 6)
        self.assertEqual(node_types.count('Wire'), 6)
        self.assertEqual(node_types.count('EdgeUse'), 24)
        self.assertEqual(node_types.count('Edge'), 12)
        self.assertEqual(node_types.count('Vertex'), 8)
        self.assertEqual(inspected.shell_roles, ('outer',))

    def test_xz_projection_uses_negative_handedness(self):
        inspected = self._inspect(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'xz.step')
        y_faces = [
            n for n in inspected.graph.nodes.values()
            if n.kind == 'Face' and abs(n.attrs['plane']['normal'][1]) == 1.0
        ]
        self.assertEqual(len(y_faces), 2)
        for face in y_faces:
            expected = -face.attrs['outward_sign']
            self.assertEqual(face.attrs['outer_wire_area_sign'], expected)

    def test_wire_hole_roles_survive_step_roundtrip(self):
        outer = BRepPrimAPI_MakeBox(4.0, 4.0, 1.0).Shape()
        cutter = BRepPrimAPI_MakeBox(gp_Pnt(1.0, 1.0, -1.0), 2.0, 2.0, 3.0).Shape()
        holed = BRepAlgoAPI_Cut(outer, cutter).Shape()
        inspected = self._inspect(holed, 'holed.step')
        roles = [n.attrs['role'] for n in inspected.graph.nodes.values() if n.kind == 'Wire']
        self.assertGreaterEqual(roles.count('inner'), 2)
        self.assertGreater(roles.count('outer'), roles.count('inner'))

    def test_touching_wire_polygons_fail_closed(self):
        outer = [(0, 0), (4, 0), (4, 4), (0, 4)]
        touching = [(0, 1), (1, 1), (1, 2), (0, 2)]
        with self.assertRaises(ContractError) as caught:
            classify_wire_polygons([outer, touching], self.config)
        self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_self_intersection_and_depth_two_wires_fail_closed(self):
        self_intersecting = [(0, 0), (3, 0), (3, 3), (1, 3),
                             (1, -1), (2, -1), (2, 2), (0, 2)]
        with self.assertRaises(ContractError) as crossed:
            classify_wire_polygons([self_intersecting], self.config)
        self.assertEqual(crossed.exception.code, 'comparison_indeterminate')

        outer = [(0, 0), (6, 0), (6, 6), (0, 6)]
        hole = [(1, 1), (5, 1), (5, 5), (1, 5)]
        island = [(2, 2), (3, 2), (3, 3), (2, 3)]
        with self.assertRaises(ContractError) as nested:
            classify_wire_polygons([outer, hole, island], self.config)
        self.assertEqual(nested.exception.code, 'comparison_indeterminate')

    def test_near_epsilon_cell_coordinates_fail_closed(self):
        polygon = [(0, 0), (0.000005, 0), (1, 0), (1, 1), (0, 1)]
        with self.assertRaises(ContractError) as caught:
            _face_cells([polygon], ('outer',), 2, 0.0, self.config)
        self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_shell_ray_boundary_and_coplanar_hits_fail_closed(self):
        rectangle = SurfaceRectangle(0, 2.0, (0.0, 0.0), (2.0, 2.0))
        bbox = (2.0, 0.0, 0.0, 2.0, 2.0, 2.0)
        for point in ((0.0, 0.0, 1.0), (2.0, 1.0, 1.0)):
            with self.subTest(point=point):
                with self.assertRaises(ContractError) as caught:
                    _shell_contains(point, [rectangle], bbox, self.config)
                self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_probe_with_non_in_out_pair_fails_closed(self):
        with self.assertRaises(ContractError) as caught:
            probe_outward(lambda point: 'ON', (1, 1, 1), (1, 0, 0), self.config)
        self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_shell_cavity_roles_are_independent_of_material_classifier(self):
        outer = BRepPrimAPI_MakeBox(4.0, 4.0, 4.0).Shape()
        cavity = BRepPrimAPI_MakeBox(gp_Pnt(1.0, 1.0, 1.0), 2.0, 2.0, 2.0).Shape()
        shape = BRepAlgoAPI_Cut(outer, cavity).Shape()
        inspected = self._inspect(shape, 'cavity.step')
        self.assertEqual(inspected.shell_roles, ('cavity', 'outer'))

    def test_open_and_disconnected_shells_fail_closed(self):
        source = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
        faces = []
        explorer = TopExp_Explorer(source, TopAbs_FACE)
        while explorer.More():
            faces.append(TopoDS.Face(explorer.Current()))
            explorer.Next()
        open_shell = TopoDS_Shell()
        builder = BRep_Builder()
        builder.MakeShell(open_shell)
        builder.Add(open_shell, faces[0])
        with self.assertRaises(ContractError) as opened:
            _validate_shell_topology(open_shell)
        self.assertEqual(opened.exception.code, 'comparison_indeterminate')

        disconnected = TopoDS_Shell()
        builder.MakeShell(disconnected)
        for box in (
            BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(),
            BRepPrimAPI_MakeBox(gp_Pnt(3.0, 0.0, 0.0), 1.0, 1.0, 1.0).Shape(),
        ):
            explorer = TopExp_Explorer(box, TopAbs_FACE)
            while explorer.More():
                builder.Add(disconnected, explorer.Current())
                explorer.Next()
        with self.assertRaises(ContractError) as separated:
            _validate_shell_topology(disconnected)
        self.assertEqual(separated.exception.code, 'comparison_indeterminate')

    def test_intersecting_shell_surfaces_fail_closed(self):
        shells = []
        for shape in (
            BRepPrimAPI_MakeBox(2.0, 2.0, 2.0).Shape(),
            BRepPrimAPI_MakeBox(gp_Pnt(1.0, 1.0, 1.0), 2.0, 2.0, 2.0).Shape(),
        ):
            explorer = TopExp_Explorer(shape, TopAbs_SHELL)
            shells.append(TopoDS.Shell(explorer.Current()))
        with self.assertRaises(ContractError) as caught:
            _validate_shell_separation(shells)
        self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_curved_observable_type_is_rejected(self):
        path = self.root / 'cylinder.step'
        _write_step(BRepPrimAPI_MakeCylinder(1.0, 2.0).Shape(), path)
        with self.assertRaises(ContractError) as caught:
            inspect_step(path, self.config)
        self.assertEqual(caught.exception.code, 'unsupported_observable_type')


class GraphEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.config = load_contract()

    def test_graph_id_permutation_and_cycle_start_are_equivalent(self):
        first = ObservableGraph(
            nodes={
                0: GraphNode('Wire', {'role': 'outer'}),
                1: GraphNode('EdgeUse', {'direction': 1}),
                2: GraphNode('EdgeUse', {'direction': 1}),
                3: GraphNode('EdgeUse', {'direction': 1}),
            },
            relations=[
                GraphRelation(0, 1, 'contains'), GraphRelation(0, 2, 'contains'),
                GraphRelation(0, 3, 'contains'), GraphRelation(1, 2, 'next'),
                GraphRelation(2, 3, 'next'), GraphRelation(3, 1, 'next'),
            ],
        )
        second = ObservableGraph(
            nodes={
                40: GraphNode('EdgeUse', {'direction': 1}),
                10: GraphNode('Wire', {'role': 'outer'}),
                20: GraphNode('EdgeUse', {'direction': 1}),
                30: GraphNode('EdgeUse', {'direction': 1}),
            },
            relations=[
                GraphRelation(10, 20, 'contains'), GraphRelation(10, 30, 'contains'),
                GraphRelation(10, 40, 'contains'), GraphRelation(30, 40, 'next'),
                GraphRelation(40, 20, 'next'), GraphRelation(20, 30, 'next'),
            ],
        )

        result = compare_graphs(first, second, self.config)

        self.assertTrue(result.equivalent)
        self.assertFalse(result.indeterminate)

    def test_real_face_split_is_not_equivalent(self):
        one_face = ObservableGraph(
            nodes={0: GraphNode('Solid', {}), 1: GraphNode('Face', {'area': 2.0})},
            relations=[GraphRelation(0, 1, 'contains')],
        )
        split_face = ObservableGraph(
            nodes={
                0: GraphNode('Solid', {}),
                1: GraphNode('Face', {'area': 1.0}),
                2: GraphNode('Face', {'area': 1.0}),
            },
            relations=[GraphRelation(0, 1, 'contains'), GraphRelation(0, 2, 'contains')],
        )

        self.assertFalse(compare_graphs(one_face, split_face, self.config).equivalent)

    def test_search_bound_exhaustion_is_indeterminate(self):
        graph = ObservableGraph(nodes={0: GraphNode('Solid', {})}, relations=[])
        limited = copy.deepcopy(self.config)
        limited['graph']['max_search_states'] = 0

        result = _compare_graphs_unbound(graph, graph, limited)

        self.assertFalse(result.equivalent)
        self.assertTrue(result.indeterminate)

    def test_coincident_distinct_vertices_are_not_merged_in_edge_incidence(self):
        graph = ObservableGraph(
            nodes={
                0: GraphNode('Edge', {}),
                1: GraphNode('Vertex', {'point': (0.0, 0.0, 0.0)}),
                2: GraphNode('Vertex', {'point': (0.0, 0.0, 0.0)}),
            },
            relations=[],
        )

        _add_edge_connections(graph, 0, [1])

        self.assertEqual(graph.relations, [GraphRelation(0, 1, 'connects')])

    @staticmethod
    def _long_chain(count, offset=0):
        nodes = {
            offset + index: GraphNode('Vertex', {'point': (float(index), 0.0, 0.0)})
            for index in range(count)
        }
        relations = [
            GraphRelation(offset + index, offset + index + 1, 'next')
            for index in range(count - 1)
        ]
        return ObservableGraph(nodes=nodes, relations=relations)

    def test_1100_node_equivalent_graph_does_not_depend_on_python_recursion(self):
        result = compare_graphs(self._long_chain(1100), self._long_chain(1100, 5000), self.config)
        self.assertTrue(result.equivalent)
        self.assertFalse(result.indeterminate)
        self.assertEqual(result.search_states, 1100)

    def test_iterative_matcher_search_exhaustion_is_indeterminate(self):
        limited = copy.deepcopy(self.config)
        limited['graph']['max_search_states'] = 10
        result = _compare_graphs_unbound(self._long_chain(20), self._long_chain(20, 100), limited)
        self.assertFalse(result.equivalent)
        self.assertTrue(result.indeterminate)
        self.assertEqual(result.reason, 'search_limit')


class GeometryComparisonTests(unittest.TestCase):
    def setUp(self):
        self.config = load_contract()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def _step(self, shape, name):
        path = self.root / name
        _write_step(shape, path)
        return path

    def test_equivalent_step_exports_compare_equal(self):
        first = self._step(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'a.step')
        second = self._step(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'b.step')

        result = compare_steps(first, second, self.config)

        self.assertTrue(result.equivalent)
        self.assertTrue(result.geometry_equivalent)
        self.assertTrue(result.graph_equivalent)
        self.assertLessEqual(result.symmetric_difference_volume, 0.001)
        self.assertLessEqual(result.surface_distance, 0.0001)
        expected_samples = 6 * 64 * 64 + 8 + 12
        self.assertEqual(result.sample_count_a, expected_samples)
        self.assertEqual(result.sample_count_b, expected_samples)

    def test_separated_fixture_compares_different(self):
        first = self._step(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'a.step')
        shifted = BRepPrimAPI_MakeBox(gp_Pnt(0.25, 0.0, 0.0), 2.0, 3.0, 4.0).Shape()
        second = self._step(shifted, 'shifted.step')

        result = compare_steps(first, second, self.config)

        self.assertFalse(result.equivalent)
        self.assertFalse(result.geometry_equivalent)
        self.assertGreater(result.symmetric_difference_volume, 0.001)
        self.assertGreater(result.surface_distance, 0.0001)

    def test_same_geometry_with_real_face_split_is_observably_different(self):
        canonical = self._step(BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape(), 'canonical.step')
        left = BRepPrimAPI_MakeBox(1.0, 3.0, 4.0).Shape()
        right = BRepPrimAPI_MakeBox(gp_Pnt(1.0, 0.0, 0.0), 1.0, 3.0, 4.0).Shape()
        split = self._step(BRepAlgoAPI_Fuse(left, right).Shape(), 'split.step')

        result = compare_steps(canonical, split, self.config)

        self.assertTrue(result.geometry_equivalent)
        self.assertFalse(result.graph_equivalent)
        self.assertFalse(result.equivalent)

    def test_boolean_measurement_failure_is_indeterminate_not_zero(self):
        valid = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
        with self.assertRaises(ContractError) as caught:
            symmetric_difference_volume(valid, TopoDS_Shape())
        self.assertEqual(caught.exception.code, 'comparison_indeterminate')

    def test_compare_steps_rejects_fault_injection_through_public_config(self):
        first = self._step(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), 'a.step')
        second = self._step(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), 'b.step')
        limited = copy.deepcopy(self.config)
        limited['graph']['max_search_states'] = 0
        with self.assertRaises(ContractError) as caught:
            compare_steps(first, second, limited)
        self.assertEqual(caught.exception.code, 'specification_binding_failure')


if __name__ == '__main__':
    unittest.main()
