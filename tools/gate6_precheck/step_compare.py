"""Fail-closed external STEP inspection and comparison for Gate 6 qualification."""
from dataclasses import dataclass, field
import math
from pathlib import Path

from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Section
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_ON,
    TopAbs_OUT,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt

from .contract import ContractError, validate_contract


_READER_SETTING_TYPES = {
    'read.precision.mode': ('integer', Interface_Static.IVal_s),
    'read.precision.val': ('real', Interface_Static.RVal_s),
    'read.maxprecision.mode': ('integer', Interface_Static.IVal_s),
    'read.maxprecision.val': ('real', Interface_Static.RVal_s),
    'read.surfacecurve.mode': ('integer', Interface_Static.IVal_s),
    'read.step.resource.name': ('string', Interface_Static.CVal_s),
    'read.step.sequence': ('string', Interface_Static.CVal_s),
    'xstep.cascade.unit': ('string', Interface_Static.CVal_s),
}

_EXPECTED_READER_SETTINGS = {
    'read.precision.mode': {'type': 'integer', 'value': 0},
    'read.precision.val': {'type': 'real', 'value': 0.001},
    'read.maxprecision.mode': {'type': 'integer', 'value': 0},
    'read.maxprecision.val': {'type': 'real', 'value': 1.0},
    'read.surfacecurve.mode': {'type': 'integer', 'value': 0},
    'read.step.resource.name': {'type': 'string', 'value': 'STEP'},
    'read.step.sequence': {'type': 'string', 'value': 'FromSTEP'},
    'xstep.cascade.unit': {'type': 'string', 'value': 'MM'},
}


@dataclass(frozen=True)
class GraphNode:
    kind: str
    attrs: dict


@dataclass(frozen=True)
class GraphRelation:
    source: int
    target: int
    kind: str
    attrs: dict = field(default_factory=dict)


@dataclass
class ObservableGraph:
    nodes: dict = field(default_factory=dict)
    relations: list = field(default_factory=list)

    def add_node(self, kind, attrs):
        node_id = len(self.nodes)
        self.nodes[node_id] = GraphNode(kind, attrs)
        return node_id

    def add_relation(self, source, target, kind, attrs=None):
        self.relations.append(GraphRelation(source, target, kind, attrs or {}))


@dataclass(frozen=True)
class GraphComparison:
    equivalent: bool
    indeterminate: bool
    search_states: int
    reason: str = ''


@dataclass(frozen=True)
class StepComparison:
    equivalent: bool
    geometry_equivalent: bool
    graph_equivalent: bool
    indeterminate: bool
    volume_difference: float
    symmetric_difference_volume: float
    surface_distance: float
    sample_count_a: int
    sample_count_b: int
    graph_search_states: int


@dataclass(frozen=True)
class SurfaceRectangle:
    axis: int
    coordinate: float
    minimum: tuple
    maximum: tuple


@dataclass(frozen=True)
class StepInspection:
    shape: object
    volume: float
    solid_count: int
    component_count: int
    valid: bool
    reader_settings: dict
    graph: ObservableGraph
    rectangles: tuple
    edge_segments: tuple
    shell_roles: tuple


def _count(shape, kind):
    result = 0
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        result += 1
        explorer.Next()
    return result


def _shape_map(shape, kind):
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, mapped)
    return mapped


def _validate_root_topology(root):
    solid_explorer = TopExp_Explorer(root, TopAbs_SOLID)
    solids = []
    while solid_explorer.More():
        solids.append(TopoDS.Solid(solid_explorer.Current()))
        solid_explorer.Next()
    if len(solids) != 1:
        raise ContractError('invalid_result_solid', f'Expected one solid, got {len(solids)}')
    solid = solids[0]
    for kind in (TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX):
        root_map = _shape_map(root, kind)
        solid_map = _shape_map(solid, kind)
        if root_map.Extent() != solid_map.Extent():
            raise ContractError('invalid_result_solid', 'STEP root contains free non-solid topology')
        for index in range(1, root_map.Extent() + 1):
            if not solid_map.Contains(root_map.FindKey(index)):
                raise ContractError('invalid_result_solid', 'STEP root topology differs from its solid')
    return solid


def _vector_tuple(direction):
    return (float(direction.X()), float(direction.Y()), float(direction.Z()))


def _point_tuple(point):
    return (float(point.X()), float(point.Y()), float(point.Z()))


def _axis_vector(vector, config):
    angle_tol = config['tolerances']['parameter_angle_rad']
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= config['tolerances']['zero_direction_component']:
        raise ContractError('unsupported_observable_type', 'Zero direction')
    unit = tuple(value / magnitude for value in vector)
    axis = max(range(3), key=lambda index: abs(unit[index]))
    if math.acos(min(1.0, abs(unit[axis]))) > angle_tol:
        raise ContractError('unsupported_observable_type', 'Direction is not world-axis aligned')
    zero = config['tolerances']['zero_direction_component']
    first = next((value for value in unit if abs(value) > zero), None)
    if first is None:
        raise ContractError('unsupported_observable_type', 'Zero direction')
    sign = 1.0 if first > 0 else -1.0
    canonical_axis_sign = 1.0 if unit[axis] * sign > 0 else -1.0
    canonical = tuple(canonical_axis_sign if index == axis else 0.0 for index in range(3))
    return axis, sign, canonical


def normalize_plane(normal, offset, config):
    """Canonicalize n.x=d by the first nonzero component sign."""
    _, sign, canonical = _axis_vector(tuple(normal), config)
    return {'normal': canonical, 'offset': float(offset) * sign}


def normalize_line(direction, point, config):
    """Canonical line direction and its closest point to the world origin."""
    _, sign, canonical = _axis_vector(tuple(direction), config)
    signed = tuple(value * sign for value in direction)
    norm2 = sum(value * value for value in signed)
    projection = sum(point[i] * signed[i] for i in range(3)) / norm2
    nearest = tuple(float(point[i] - projection * signed[i]) for i in range(3))
    return {'direction': canonical, 'nearest_origin_point': nearest}


def _project(point, axis):
    if axis == 0:
        return (point[1], point[2])
    if axis == 1:
        return (point[0], point[2])
    return (point[0], point[1])


def _signed_area(polygon):
    return 0.5 * sum(
        polygon[i][0] * polygon[(i + 1) % len(polygon)][1]
        - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
        for i in range(len(polygon))
    )


def _point_segment_distance(point, start, end):
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _point_in_polygon(point, polygon, epsilon):
    if any(
        _point_segment_distance(point, polygon[i], polygon[(i + 1) % len(polygon)]) <= epsilon
        for i in range(len(polygon))
    ):
        return 'BOUNDARY'
    x, y = point
    inside = False
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        if (y1 <= y < y2) or (y2 <= y < y1):
            cross_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if cross_x > x:
                inside = not inside
    return 'IN' if inside else 'OUT'


def _segments_intersect_or_touch(a1, a2, b1, b2, epsilon):
    def orientation(p, q, r):
        value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        if abs(value) <= epsilon:
            return 0
        return 1 if value > 0 else -1

    def on_segment(p, q, r):
        return (
            min(p[0], r[0]) - epsilon <= q[0] <= max(p[0], r[0]) + epsilon
            and min(p[1], r[1]) - epsilon <= q[1] <= max(p[1], r[1]) + epsilon
        )

    o1, o2 = orientation(a1, a2, b1), orientation(a1, a2, b2)
    o3, o4 = orientation(b1, b2, a1), orientation(b1, b2, a2)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and on_segment(a1, b1, a2))
        or (o2 == 0 and on_segment(a1, b2, a2))
        or (o3 == 0 and on_segment(b1, a1, b2))
        or (o4 == 0 and on_segment(b1, a2, b2))
    )


def _validate_polygon(polygon, epsilon):
    if len(polygon) < 4 or abs(_signed_area(polygon)) <= epsilon * epsilon:
        raise ContractError('comparison_indeterminate', 'Degenerate wire polygon')
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        if not (abs(a[0] - b[0]) <= epsilon or abs(a[1] - b[1]) <= epsilon):
            raise ContractError('unsupported_observable_type', 'Wire is not axis aligned')
        for other in range(index + 1, len(polygon)):
            if other in (index, (index + 1) % len(polygon)):
                continue
            if index == 0 and other == len(polygon) - 1:
                continue
            c, d = polygon[other], polygon[(other + 1) % len(polygon)]
            if _segments_intersect_or_touch(a, b, c, d, epsilon):
                raise ContractError('comparison_indeterminate', 'Self-intersecting or touching wire')


def classify_wire_polygons(polygons, config):
    """Return outer/inner roles using half-open even/odd containment."""
    epsilon = config['tolerances']['polygon_boundary_mm']
    for polygon in polygons:
        _validate_polygon(polygon, epsilon)
    for first in range(len(polygons)):
        for second in range(first + 1, len(polygons)):
            for index in range(len(polygons[first])):
                a, b = polygons[first][index], polygons[first][(index + 1) % len(polygons[first])]
                for other in range(len(polygons[second])):
                    c = polygons[second][other]
                    d = polygons[second][(other + 1) % len(polygons[second])]
                    if _segments_intersect_or_touch(a, b, c, d, epsilon):
                        raise ContractError('comparison_indeterminate', 'Distinct wires touch or intersect')
    depths = []
    for index, polygon in enumerate(polygons):
        point = polygon[0]
        depth = 0
        for other, container in enumerate(polygons):
            if other == index:
                continue
            state = _point_in_polygon(point, container, epsilon)
            if state == 'BOUNDARY':
                raise ContractError('comparison_indeterminate', 'Wire containment point is on boundary')
            depth += state == 'IN'
        if depth > 1:
            raise ContractError('comparison_indeterminate', 'Wire nesting deeper than one')
        depths.append(depth)
    if depths.count(0) != 1:
        raise ContractError('comparison_indeterminate', 'Face does not have one outer wire')
    return tuple('outer' if depth == 0 else 'inner' for depth in depths)


def probe_outward(classify, point, normal, config):
    distance = config['tolerances']['normal_probe_distance_mm']
    plus = tuple(point[i] + distance * normal[i] for i in range(3))
    minus = tuple(point[i] - distance * normal[i] for i in range(3))
    plus_state, minus_state = classify(plus), classify(minus)
    if {plus_state, minus_state} != {'IN', 'OUT'}:
        raise ContractError('comparison_indeterminate', f'Probe states are {plus_state}/{minus_state}')
    return 1 if plus_state == 'OUT' else -1


def _shape_slot(shapes, shape):
    for index, existing in enumerate(shapes):
        if existing.IsSame(shape):
            return index
    shapes.append(shape)
    return len(shapes) - 1


def _add_edge_connections(graph, edge_id, vertex_ids):
    """Connect only the topological vertices used by this edge."""
    for vertex_id in vertex_ids:
        graph.add_relation(edge_id, vertex_id, 'connects')


def _properties(shape, mode):
    props = GProp_GProps()
    if mode == 'volume':
        BRepGProp.VolumeProperties_s(shape, props)
    elif mode == 'surface':
        BRepGProp.SurfaceProperties_s(shape, props)
    else:
        BRepGProp.LinearProperties_s(shape, props)
    return float(props.Mass()), _point_tuple(props.CentreOfMass())


def _bbox(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return tuple(float(value) for value in box.Get())


def _wire_entries(wire, face):
    entries = []
    explorer = BRepTools_WireExplorer(wire, face)
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())
        vertex = TopoDS.Vertex(explorer.CurrentVertex())
        entries.append((edge, _point_tuple(BRep_Tool.Pnt_s(vertex))))
        explorer.Next()
    if len(entries) < 3:
        raise ContractError('comparison_indeterminate', 'Broken or empty wire')
    return entries


def _face_cells(polygons, roles, axis, coordinate, config):
    epsilon = config['tolerances']['polygon_boundary_mm']
    xs = sorted(set(point[0] for polygon in polygons for point in polygon))
    ys = sorted(set(point[1] for polygon in polygons for point in polygon))
    if any(b - a <= epsilon for values in (xs, ys) for a, b in zip(values, values[1:])):
        raise ContractError('comparison_indeterminate', 'Cell coordinates are within boundary epsilon')
    outer = polygons[roles.index('outer')]
    holes = [polygon for polygon, role in zip(polygons, roles) if role == 'inner']
    cells = []
    for x1, x2 in zip(xs, xs[1:]):
        for y1, y2 in zip(ys, ys[1:]):
            center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if _point_in_polygon(center, outer, epsilon) != 'IN':
                continue
            if any(_point_in_polygon(center, hole, epsilon) != 'OUT' for hole in holes):
                continue
            if min(
                _point_segment_distance(center, polygon[index], polygon[(index + 1) % len(polygon)])
                for polygon in polygons for index in range(len(polygon))
            ) <= epsilon:
                raise ContractError('comparison_indeterminate', 'Cell center lies on wire boundary')
            cells.append(SurfaceRectangle(axis, coordinate, (x1, y1), (x2, y2)))
    if not cells:
        raise ContractError('comparison_indeterminate', 'Face has no valid rectangular cell')
    return cells


def _cell_center_3d(cell):
    u = (cell.minimum[0] + cell.maximum[0]) / 2.0
    v = (cell.minimum[1] + cell.maximum[1]) / 2.0
    if cell.axis == 0:
        return (cell.coordinate, u, v)
    if cell.axis == 1:
        return (u, cell.coordinate, v)
    return (u, v, cell.coordinate)


def _classifier(shape, tolerance):
    classifier = BRepClass3d_SolidClassifier(shape)

    def classify(point):
        classifier.Perform(gp_Pnt(*point), tolerance)
        state = classifier.State()
        if state == TopAbs_IN:
            return 'IN'
        if state == TopAbs_OUT:
            return 'OUT'
        if state == TopAbs_ON:
            return 'ON'
        return 'UNKNOWN'

    return classify


def _canonicalize_entries(entries, polygon, expected_sign):
    area_sign = 1 if _signed_area(polygon) > 0 else -1
    if area_sign != expected_sign:
        original_entries = entries
        polygon = list(reversed(polygon))
        count = len(polygon)
        entries = [
            (original_entries[(count - 2 - index) % count][0], point)
            for index, point in enumerate(polygon)
        ]
    start = min(range(len(polygon)), key=lambda index: (polygon[index], polygon[(index + 1) % len(polygon)]))
    polygon = polygon[start:] + polygon[:start]
    entries = entries[start:] + entries[:start]
    return entries, polygon


def _shell_contains(point, rectangles, bbox, config):
    epsilon = config['tolerances']['polygon_boundary_mm']
    if not (bbox[1] - epsilon <= point[1] <= bbox[4] + epsilon and bbox[2] - epsilon <= point[2] <= bbox[5] + epsilon):
        return False
    hits = 0
    for rect in rectangles:
        if rect.axis != 0 or rect.coordinate < point[0] - epsilon:
            continue
        u, v = point[1], point[2]
        on_u = abs(u - rect.minimum[0]) <= epsilon or abs(u - rect.maximum[0]) <= epsilon
        on_v = abs(v - rect.minimum[1]) <= epsilon or abs(v - rect.maximum[1]) <= epsilon
        inside = (
            rect.minimum[0] - epsilon <= u <= rect.maximum[0] + epsilon
            and rect.minimum[1] - epsilon <= v <= rect.maximum[1] + epsilon
        )
        if not inside:
            continue
        if on_u or on_v or abs(rect.coordinate - point[0]) <= epsilon:
            raise ContractError('comparison_indeterminate', 'Shell parity ray hits boundary or is coplanar')
        hits += 1
    return bool(hits % 2)


def _validate_shell_topology(shell):
    """Require a closed shell whose face adjacency graph is connected."""
    if not BRep_Tool.IsClosed_s(shell):
        raise ContractError('comparison_indeterminate', 'Shell is not closed')
    faces = []
    face_edges = []
    edge_shapes = []
    explorer = TopExp_Explorer(shell, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        faces.append(face)
        slots = set()
        edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_explorer.More():
            slots.add(_shape_slot(edge_shapes, edge_explorer.Current()))
            edge_explorer.Next()
        face_edges.append(slots)
        explorer.Next()
    if not faces:
        raise ContractError('comparison_indeterminate', 'Shell contains no faces')
    reached = {0}
    pending = [0]
    while pending:
        current = pending.pop()
        for other in range(len(faces)):
            if other not in reached and face_edges[current].intersection(face_edges[other]):
                reached.add(other)
                pending.append(other)
    if len(reached) != len(faces):
        raise ContractError('comparison_indeterminate', 'Shell face adjacency is disconnected')


def _validate_shell_separation(shells):
    """Reject any contact or intersection between distinct shell boundaries."""
    for first in range(len(shells)):
        for second in range(first + 1, len(shells)):
            try:
                section = BRepAlgoAPI_Section(shells[first], shells[second])
                section.Build()
                if not section.IsDone():
                    raise ContractError('comparison_indeterminate', 'Shell intersection test failed')
                result = section.Shape()
            except ContractError:
                raise
            except Exception as exc:
                raise ContractError('comparison_indeterminate', f'Shell intersection test failed: {exc}') from exc
            if not result.IsNull() and (
                _count(result, TopAbs_EDGE) > 0 or _count(result, TopAbs_VERTEX) > 0
            ):
                raise ContractError('comparison_indeterminate', 'Distinct shells intersect or touch')


def _extract_observables(shape, config):
    graph = ObservableGraph()
    volume, centroid = _properties(shape, 'volume')
    solid_id = graph.add_node('Solid', {'volume': volume, 'centroid': centroid, 'bbox': _bbox(shape)})
    shells, faces, edges, vertices = [], [], [], []
    face_records = []
    shell_records = []
    classifier = _classifier(shape, config['tolerances']['solid_classifier_mm'])

    shell_explorer = TopExp_Explorer(shape, TopAbs_SHELL)
    while shell_explorer.More():
        shell = TopoDS.Shell(shell_explorer.Current())
        _validate_shell_topology(shell)
        shell_index = _shape_slot(shells, shell)
        shell_id = graph.add_node('Shell', {'closed': bool(BRep_Tool.IsClosed_s(shell)), 'role': None})
        graph.add_relation(solid_id, shell_id, 'contains')
        shell_rectangles = []
        shell_vertices = []
        face_explorer = TopExp_Explorer(shell, TopAbs_FACE)
        while face_explorer.More():
            face = TopoDS.Face(face_explorer.Current())
            _shape_slot(faces, face)
            adaptor = BRepAdaptor_Surface(face, True)
            if adaptor.GetType() != GeomAbs_Plane:
                raise ContractError('unsupported_observable_type', 'Only planar faces are supported')
            plane = adaptor.Plane()
            raw_normal = _vector_tuple(plane.Axis().Direction())
            raw_location = _point_tuple(plane.Location())
            raw_offset = sum(raw_normal[i] * raw_location[i] for i in range(3))
            normalized = normalize_plane(raw_normal, raw_offset, config)
            axis = next(index for index, value in enumerate(normalized['normal']) if value != 0.0)
            coordinate = normalized['offset'] / normalized['normal'][axis]
            wire_data = []
            wire_explorer = TopExp_Explorer(face, TopAbs_WIRE)
            while wire_explorer.More():
                wire = TopoDS.Wire(wire_explorer.Current())
                entries = _wire_entries(wire, face)
                polygon = [_project(point, axis) for _, point in entries]
                wire_data.append((wire, entries, polygon))
                wire_explorer.Next()
            roles = classify_wire_polygons([data[2] for data in wire_data], config)
            cells = _face_cells([data[2] for data in wire_data], roles, axis, coordinate, config)
            probe_cell = sorted(
                cells,
                key=lambda cell: (
                    -((cell.maximum[0] - cell.minimum[0]) * (cell.maximum[1] - cell.minimum[1])),
                    cell.minimum,
                    cell.maximum,
                ),
            )[0]
            outward_sign = probe_outward(classifier, _cell_center_3d(probe_cell), normalized['normal'], config)
            area, face_centroid = _properties(face, 'surface')
            face_id = graph.add_node('Face', {
                'plane': normalized,
                'outward_sign': outward_sign,
                'area': area,
                'centroid': face_centroid,
                'outer_wire_area_sign': None,
            })
            graph.add_relation(shell_id, face_id, 'contains')
            h = (1, -1, 1)[axis]
            outer_area_sign = None
            for (wire, entries, polygon), role in zip(wire_data, roles):
                expected_sign = h * outward_sign * (1 if role == 'outer' else -1)
                entries, polygon = _canonicalize_entries(entries, polygon, expected_sign)
                if role == 'outer':
                    outer_area_sign = 1 if _signed_area(polygon) > 0 else -1
                wire_id = graph.add_node('Wire', {'role': role})
                graph.add_relation(face_id, wire_id, 'contains')
                use_ids = []
                for entry_index, (edge, start_point_2d) in enumerate(entries):
                    edge_slot = _shape_slot(edges, edge)
                    edge_id = None
                    for node_id, node in graph.nodes.items():
                        if node.kind == 'Edge' and node.attrs['_slot'] == edge_slot:
                            edge_id = node_id
                            break
                    curve = BRepAdaptor_Curve(edge)
                    if curve.GetType() != GeomAbs_Line:
                        raise ContractError('unsupported_observable_type', 'Only straight edges are supported')
                    line = curve.Line()
                    normalized_line = normalize_line(
                        _vector_tuple(line.Direction()), _point_tuple(line.Location()), config
                    )
                    edge_vertex_points = []
                    edge_vertex_ids = []
                    vertex_explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
                    while vertex_explorer.More():
                        vertex = TopoDS.Vertex(vertex_explorer.Current())
                        vertex_slot = _shape_slot(vertices, vertex)
                        point = _point_tuple(BRep_Tool.Pnt_s(vertex))
                        edge_vertex_points.append(point)
                        vertex_id = None
                        for candidate_id, node in graph.nodes.items():
                            if node.kind == 'Vertex' and node.attrs['_slot'] == vertex_slot:
                                vertex_id = candidate_id
                                break
                        if vertex_id is None:
                            vertex_id = graph.add_node('Vertex', {'point': point, '_slot': vertex_slot})
                        edge_vertex_ids.append(vertex_id)
                        vertex_explorer.Next()
                    if edge_id is None:
                        length, edge_centroid = _properties(edge, 'linear')
                        edge_id = graph.add_node('Edge', {
                            'line': normalized_line,
                            'length': length,
                            'centroid': edge_centroid,
                            'endpoints': tuple(sorted(edge_vertex_points)),
                            '_slot': edge_slot,
                        })
                        _add_edge_connections(graph, edge_id, edge_vertex_ids)
                    next_point_2d = polygon[(entry_index + 1) % len(polygon)]
                    direction_sign = 1 if next_point_2d > start_point_2d else -1
                    use_id = graph.add_node('EdgeUse', {'direction': direction_sign})
                    graph.add_relation(wire_id, use_id, 'contains')
                    graph.add_relation(use_id, edge_id, 'references')
                    use_ids.append(use_id)
                for index, use_id in enumerate(use_ids):
                    graph.add_relation(use_id, use_ids[(index + 1) % len(use_ids)], 'next')
            graph.nodes[face_id].attrs['outer_wire_area_sign'] = outer_area_sign
            face_records.append((face_id, cells))
            shell_rectangles.extend(cells)
            vertex_explorer = TopExp_Explorer(face, TopAbs_VERTEX)
            while vertex_explorer.More():
                shell_vertices.append(_point_tuple(BRep_Tool.Pnt_s(TopoDS.Vertex(vertex_explorer.Current()))))
                vertex_explorer.Next()
            face_explorer.Next()
        shell_records.append((shell_index, shell_id, shell_rectangles, tuple(sorted(set(shell_vertices))), _bbox(shell)))
        shell_explorer.Next()

    _validate_shell_separation(shells)

    depths = []
    for shell_index, _, _, shell_vertices, _ in shell_records:
        if not shell_vertices:
            raise ContractError('comparison_indeterminate', 'Shell has no vertices')
        point = shell_vertices[0]
        depth = 0
        for other_index, _, rectangles, _, bbox in shell_records:
            if other_index == shell_index:
                continue
            depth += _shell_contains(point, rectangles, bbox, config)
        if depth > 1:
            raise ContractError('comparison_indeterminate', 'Shell nesting deeper than one')
        depths.append(depth)
    component_count = depths.count(0)
    if component_count != 1:
        raise ContractError('comparison_indeterminate', 'No unique outer shell')
    for depth, (_, shell_id, _, _, _) in zip(depths, shell_records):
        graph.nodes[shell_id].attrs['role'] = 'outer' if depth == 0 else 'cavity'
    for node in graph.nodes.values():
        node.attrs.pop('_slot', None)
    rectangles = tuple(cell for _, cells in face_records for cell in cells)
    edge_segments = tuple(
        node.attrs['endpoints'] for node in graph.nodes.values() if node.kind == 'Edge'
    )
    shell_roles = tuple(sorted('outer' if depth == 0 else 'cavity' for depth in depths))
    return graph, rectangles, edge_segments, shell_roles, component_count


def _numeric_tolerance(path, config):
    leaf = path[-1] if path else ''
    if 'volume' in leaf:
        return config['tolerances']['volume_mm3']
    if 'area' in leaf:
        return config['tolerances']['parameter_area_mm2']
    if leaf in ('normal', 'direction'):
        return config['tolerances']['parameter_angle_rad']
    return config['tolerances']['parameter_length_mm']


def _attributes_equal(first, second, config, path=()):
    if type(first) is not type(second) and not (
        isinstance(first, (int, float)) and isinstance(second, (int, float))
    ):
        return False
    if isinstance(first, dict):
        return first.keys() == second.keys() and all(
            _attributes_equal(first[key], second[key], config, path + (key,)) for key in first
        )
    if isinstance(first, (tuple, list)):
        return len(first) == len(second) and all(
            _attributes_equal(a, b, config, path) for a, b in zip(first, second)
        )
    if isinstance(first, bool) or isinstance(second, bool):
        return first is second
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        return abs(float(first) - float(second)) <= _numeric_tolerance(path, config)
    return first == second


def _graph_indexes(graph):
    inbound = {node_id: {} for node_id in graph.nodes}
    outbound = {node_id: {} for node_id in graph.nodes}
    pairs = {}
    for relation in graph.relations:
        if relation.source not in graph.nodes or relation.target not in graph.nodes:
            raise KeyError('Relation references missing node')
        out_key = (relation.kind, graph.nodes[relation.target].kind)
        in_key = (relation.kind, graph.nodes[relation.source].kind)
        outbound[relation.source][out_key] = outbound[relation.source].get(out_key, 0) + 1
        inbound[relation.target][in_key] = inbound[relation.target].get(in_key, 0) + 1
        pairs.setdefault((relation.source, relation.target), []).append(relation)
    degrees = {
        node_id: (tuple(sorted(inbound[node_id].items())), tuple(sorted(outbound[node_id].items())))
        for node_id in graph.nodes
    }
    return degrees, pairs


def _relation_lists_equal(first, second, config):
    if len(first) != len(second):
        return False
    used = set()
    for relation in first:
        match = None
        for index, candidate in enumerate(second):
            if index in used:
                continue
            if relation.kind == candidate.kind and _attributes_equal(
                relation.attrs, candidate.attrs, config
            ):
                match = index
                break
        if match is None:
            return False
        used.add(match)
    return True


def _compare_graphs_unbound(graph_a, graph_b, config):
    """Full attributed directed-multigraph isomorphism with a hard search cap."""
    max_nodes = config['graph']['max_nodes']
    max_states = config['graph']['max_search_states']
    if len(graph_a.nodes) > max_nodes or len(graph_b.nodes) > max_nodes:
        return GraphComparison(False, True, 0, 'node_limit')
    if max_states <= 0:
        return GraphComparison(False, True, 0, 'search_limit')
    if len(graph_a.nodes) != len(graph_b.nodes) or len(graph_a.relations) != len(graph_b.relations):
        return GraphComparison(False, False, 0, 'count_mismatch')

    try:
        degrees_a, pairs_a = _graph_indexes(graph_a)
        degrees_b, pairs_b = _graph_indexes(graph_b)
        buckets_b = {}
        for node_b, value_b in graph_b.nodes.items():
            buckets_b.setdefault((value_b.kind, degrees_b[node_b]), []).append(node_b)
        candidates = {}
        for node_a, value_a in graph_a.nodes.items():
            bucket = buckets_b.get((value_a.kind, degrees_a[node_a]), ())
            candidates[node_a] = [
                node_b for node_b in bucket
                if _attributes_equal(value_a.attrs, graph_b.nodes[node_b].attrs, config)
            ]
            if not candidates[node_a]:
                return GraphComparison(False, False, 0, 'attribute_or_degree_mismatch')
    except (MemoryError, RecursionError, KeyError):
        return GraphComparison(False, True, 0, 'preprocessing_resource_failure')

    try:
        order = sorted(
            graph_a.nodes,
            key=lambda node: (len(candidates[node]), graph_a.nodes[node].kind, node),
        )
        mapping = {}
        used = set()
        next_candidate = [0] * len(order)
        chosen = [None] * len(order)
    except (MemoryError, RecursionError):
        return GraphComparison(False, True, 0, 'preprocessing_resource_failure')
    states = 0

    def consistent(node_a, node_b):
        if not _relation_lists_equal(
            pairs_a.get((node_a, node_a), ()), pairs_b.get((node_b, node_b), ()), config
        ):
            return False
        for mapped_a, mapped_b in mapping.items():
            if not _relation_lists_equal(
                pairs_a.get((node_a, mapped_a), ()),
                pairs_b.get((node_b, mapped_b), ()),
                config,
            ):
                return False
            if not _relation_lists_equal(
                pairs_a.get((mapped_a, node_a), ()),
                pairs_b.get((mapped_b, node_b), ()),
                config,
            ):
                return False
        return True

    position = 0
    try:
        while position >= 0:
            if position == len(order):
                return GraphComparison(True, False, states)
            node_a = order[position]
            advanced = False
            while next_candidate[position] < len(candidates[node_a]):
                node_b = candidates[node_a][next_candidate[position]]
                next_candidate[position] += 1
                states += 1
                if states > max_states:
                    return GraphComparison(False, True, states, 'search_limit')
                if node_b in used or not consistent(node_a, node_b):
                    continue
                mapping[node_a] = node_b
                used.add(node_b)
                chosen[position] = node_b
                position += 1
                if position < len(order):
                    next_candidate[position] = 0
                    chosen[position] = None
                advanced = True
                break
            if advanced:
                continue
            next_candidate[position] = 0
            position -= 1
            if position < 0:
                break
            previous_a = order[position]
            previous_b = chosen[position]
            if previous_b is not None:
                used.remove(previous_b)
                del mapping[previous_a]
                chosen[position] = None
    except (MemoryError, RecursionError):
        return GraphComparison(False, True, states, 'search_resource_failure')
    return GraphComparison(False, False, states, 'no_isomorphism')


def compare_graphs(graph_a, graph_b, config):
    validate_contract(config)
    return _compare_graphs_unbound(graph_a, graph_b, config)


def _shape_volume(shape):
    if shape.IsNull():
        return 0.0
    if not BRepCheck_Analyzer(shape).IsValid():
        raise ContractError('comparison_indeterminate', 'Boolean measurement produced invalid shape')
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def symmetric_difference_volume(shape_a, shape_b):
    """Measure A\\B plus B\\A; any boolean uncertainty fails closed."""
    if shape_a.IsNull() or shape_b.IsNull():
        raise ContractError('comparison_indeterminate', 'Cannot boolean a null shape')
    try:
        first = BRepAlgoAPI_Cut(shape_a, shape_b)
        second = BRepAlgoAPI_Cut(shape_b, shape_a)
        if not first.IsDone() or not second.IsDone():
            raise ContractError('comparison_indeterminate', 'Symmetric-difference boolean did not finish')
        return _shape_volume(first.Shape()) + _shape_volume(second.Shape())
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError('comparison_indeterminate', f'Symmetric-difference boolean failed: {exc}') from exc


def _rectangle_point(cell, u, v):
    if cell.axis == 0:
        return (cell.coordinate, u, v)
    if cell.axis == 1:
        return (u, cell.coordinate, v)
    return (u, v, cell.coordinate)


def _surface_samples(inspection, config):
    grid = config['sampling']['grid_per_cell_axis']
    points = set()
    for rectangle in inspection.rectangles:
        du = (rectangle.maximum[0] - rectangle.minimum[0]) / grid
        dv = (rectangle.maximum[1] - rectangle.minimum[1]) / grid
        for i in range(grid):
            u = rectangle.minimum[0] + (i + 0.5) * du
            for j in range(grid):
                v = rectangle.minimum[1] + (j + 0.5) * dv
                points.add(_rectangle_point(rectangle, u, v))
    for endpoints in inspection.edge_segments:
        if len(endpoints) != 2:
            raise ContractError('comparison_indeterminate', 'Edge does not have two endpoints')
        start, end = endpoints
        for fraction in config['sampling']['edge_points']:
            points.add(tuple(start[index] + fraction * (end[index] - start[index]) for index in range(3)))
    if not points:
        raise ContractError('comparison_indeterminate', 'Surface sampling produced no points')
    return tuple(sorted(points))


def _point_rectangle_distance(point, rectangle):
    if rectangle.axis == 0:
        normal, u, v = point[0] - rectangle.coordinate, point[1], point[2]
    elif rectangle.axis == 1:
        normal, u, v = point[1] - rectangle.coordinate, point[0], point[2]
    else:
        normal, u, v = point[2] - rectangle.coordinate, point[0], point[1]
    du = max(rectangle.minimum[0] - u, 0.0, u - rectangle.maximum[0])
    dv = max(rectangle.minimum[1] - v, 0.0, v - rectangle.maximum[1])
    return math.sqrt(normal * normal + du * du + dv * dv)


def _directional_surface_distance(points, rectangles):
    if not rectangles:
        raise ContractError('comparison_indeterminate', 'Target has no surface rectangles')
    maximum = 0.0
    for point in points:
        nearest = min(_point_rectangle_distance(point, rectangle) for rectangle in rectangles)
        maximum = max(maximum, nearest)
    return maximum


def compare_steps(path_a, path_b, config):
    """Compare authoritative, exported/reimported STEP artifacts."""
    validate_contract(config)
    first = inspect_step(path_a, config)
    second = inspect_step(path_b, config)
    volume_difference = abs(first.volume - second.volume)
    symmetric_difference = symmetric_difference_volume(first.shape, second.shape)
    samples_a = _surface_samples(first, config)
    samples_b = _surface_samples(second, config)
    surface_distance = max(
        _directional_surface_distance(samples_a, second.rectangles),
        _directional_surface_distance(samples_b, first.rectangles),
    )
    graph = compare_graphs(first.graph, second.graph, config)
    if graph.indeterminate:
        raise ContractError('comparison_indeterminate', f'Graph comparison failed: {graph.reason}')
    geometry_equivalent = (
        volume_difference <= config['tolerances']['volume_mm3']
        and symmetric_difference <= config['tolerances']['volume_mm3']
        and surface_distance <= config['tolerances']['surface_mm']
        and first.solid_count == second.solid_count
        and first.component_count == second.component_count
    )
    return StepComparison(
        equivalent=geometry_equivalent and graph.equivalent,
        geometry_equivalent=geometry_equivalent,
        graph_equivalent=graph.equivalent,
        indeterminate=False,
        volume_difference=volume_difference,
        symmetric_difference_volume=symmetric_difference,
        surface_distance=surface_distance,
        sample_count_a=len(samples_a),
        sample_count_b=len(samples_b),
        graph_search_states=graph.search_states,
    )


def inspect_step(path, config):
    """Read STEP directly with OCP defaults and reject anything but one valid solid."""
    validate_contract(config)
    reader = STEPControl_Reader()
    settings = {
        name: {'type': value_type, 'value': reader_function(name)}
        for name, (value_type, reader_function) in _READER_SETTING_TYPES.items()
    }
    if any(
        setting['type'] == 'string' and setting['value'] == ''
        for setting in settings.values()
    ):
        raise ContractError('comparison_indeterminate', 'STEP reader string setting is empty')
    if settings != _EXPECTED_READER_SETTINGS:
        raise ContractError('environment_mismatch', f'STEP reader policy differs: {settings!r}')
    try:
        status = reader.ReadFile(str(Path(path)))
    except Exception as exc:
        raise ContractError('invalid_result_solid', f'STEP read failed: {exc}') from exc
    if status != IFSelect_RetDone:
        raise ContractError('invalid_result_solid', f'STEP reader status: {status}')
    try:
        transferred = reader.TransferRoots()
        shape = reader.OneShape()
    except Exception as exc:
        raise ContractError('invalid_result_solid', f'STEP transfer failed: {exc}') from exc
    if transferred <= 0 or shape.IsNull():
        raise ContractError('invalid_result_solid', 'STEP contains no transferable shape')
    solid_count = _count(shape, TopAbs_SOLID)
    solid = _validate_root_topology(shape)
    valid = bool(BRepCheck_Analyzer(solid).IsValid())
    if not valid:
        raise ContractError(
            'invalid_result_solid',
            f'Expected one valid solid, got solid_count={solid_count}, valid={valid}',
        )
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    graph, rectangles, edge_segments, shell_roles, component_count = _extract_observables(solid, config)
    return StepInspection(
        shape=solid,
        volume=float(props.Mass()),
        solid_count=solid_count,
        component_count=component_count,
        valid=valid,
        reader_settings=settings,
        graph=graph,
        rectangles=rectangles,
        edge_segments=edge_segments,
        shell_roles=shell_roles,
    )
