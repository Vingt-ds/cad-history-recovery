"""Supported planar-profile reconstruction and canonical cadseq-0.2 emission."""

from __future__ import annotations

import math
from pathlib import Path

import brep_inspection
import extrusion_inference
import topology_adjacency


LINEAR_TOLERANCE_MM = 1e-6
ANGULAR_TOLERANCE_RAD = 1e-8
NAMED_PLANES = {
    "XY": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "XZ": ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
    "YZ": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}
canonical_json_bytes = brep_inspection.canonical_json_bytes


class ProfileReconstructionError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _add(left, right):
    return tuple(float(a) + float(b) for a, b in zip(left, right))


def _subtract(left, right):
    return tuple(float(a) - float(b) for a, b in zip(left, right))


def _scale(vector, factor):
    return tuple(float(value) * float(factor) for value in vector)


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm(vector):
    return math.sqrt(_dot(vector, vector))


def _normalize(vector):
    length = _norm(vector)
    if length <= LINEAR_TOLERANCE_MM:
        raise ProfileReconstructionError("degenerate_frame_axis")
    return tuple(value / length for value in vector)


def _q_vector(vector, digits=9):
    return [brep_inspection._q(value, digits) for value in vector]


def _orientation_area_twice(points):
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _orientation(left, right, point):
    return (right[0] - left[0]) * (point[1] - left[1]) - (
        right[1] - left[1]
    ) * (point[0] - left[0])


def _segments_intersect(a, b, c, d):
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    return first * second < 0.0 and third * fourth < 0.0


def validate_simple_polygon(points):
    if not 3 <= len(points) <= 8:
        raise ProfileReconstructionError("unsupported_profile_edge_count")
    normalized = [tuple(float(value) for value in point) for point in points]
    for index, point in enumerate(normalized):
        if math.dist(point, normalized[(index + 1) % len(normalized)]) <= LINEAR_TOLERANCE_MM:
            raise ProfileReconstructionError("degenerate_profile_edge")
    count = len(normalized)
    for first in range(count):
        a = normalized[first]
        b = normalized[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count == first:
                continue
            c = normalized[second]
            d = normalized[(second + 1) % count]
            if _segments_intersect(a, b, c, d):
                raise ProfileReconstructionError("self_intersecting_profile")
    if abs(_orientation_area_twice(normalized)) <= LINEAR_TOLERANCE_MM**2:
        raise ProfileReconstructionError("degenerate_profile_area")
    return normalized


def _frame_for_candidate(summary, candidate, base_face):
    direction = tuple(candidate["extrusion_direction"])
    base_centroid = tuple(base_face["centroid_mm"])
    for role, (normal, x_axis) in NAMED_PLANES.items():
        if (
            abs(abs(_dot(direction, normal)) - 1.0) <= ANGULAR_TOLERANCE_RAD
            and abs(_dot(base_centroid, normal)) <= LINEAR_TOLERANCE_MM
        ):
            return {
                "semantic_reference": {"type": "origin_plane", "role": role},
                "frame_source": "origin_named",
                "frame": {
                    "origin": [0.0, 0.0, 0.0],
                    "normal": list(normal),
                    "x_axis": list(x_axis),
                },
            }

    normal = _normalize(direction)
    global_axis = (1.0, 0.0, 0.0)
    projected = _subtract(global_axis, _scale(normal, _dot(global_axis, normal)))
    if _norm(projected) <= ANGULAR_TOLERANCE_RAD:
        global_axis = (0.0, 1.0, 0.0)
        projected = _subtract(global_axis, _scale(normal, _dot(global_axis, normal)))
    x_axis = _normalize(projected)
    return {
        "semantic_reference": {"type": "absolute_frame"},
        "frame_source": "inferred_brep",
        "frame_provenance": {
            "source_step_sha256": summary["source_step_sha256"],
            "base_face_id": candidate["base_face_id"],
            "source_face_outward_normal": candidate["source_face_outward_normal"],
        },
        "frame": {
            "origin": _q_vector(base_centroid),
            "normal": _q_vector(normal, 12),
            "x_axis": _q_vector(x_axis, 12),
        },
    }


def _project(point, frame):
    origin = tuple(frame["origin"])
    normal = tuple(frame["normal"])
    x_axis = tuple(frame["x_axis"])
    y_axis = _cross(normal, x_axis)
    relative = _subtract(point, origin)
    return (brep_inspection._q(_dot(relative, x_axis)), brep_inspection._q(_dot(relative, y_axis)))


def _line_points(edge, orientation):
    parameters = edge["curve_parameters"]
    origin = tuple(parameters["origin_mm"])
    direction = tuple(parameters["direction"])
    first, last = edge["parameter_range"]
    start = _add(origin, _scale(direction, first))
    end = _add(origin, _scale(direction, last))
    if orientation == "reversed":
        return end, start
    if orientation != "forward":
        raise ProfileReconstructionError("unsupported_edge_use_orientation")
    return start, end


def reconstruct_profile(summary, candidate):
    if candidate.get("status") != "accepted":
        raise ProfileReconstructionError("candidate_not_accepted")
    solid = summary["solids"][0]
    faces = {item["face_id"]: item for item in solid["faces"]}
    wires = {item["wire_id"]: item for item in solid["wires"]}
    edges = {item["edge_id"]: item for item in solid["edges"]}
    base_face = faces[candidate["base_face_id"]]
    if len(base_face["wire_uses"]) != 1:
        raise ProfileReconstructionError("multiple_profile_loops")
    wire = wires[base_face["wire_uses"][0]["wire_id"]]
    edge_uses = wire["edge_uses"]
    edge_types = {edges[item["edge_id"]]["curve_type"] for item in edge_uses}
    plane = _frame_for_candidate(summary, candidate, base_face)
    frame = plane["frame"]

    if edge_types == {"line"}:
        if not 3 <= len(edge_uses) <= 8:
            raise ProfileReconstructionError("unsupported_profile_edge_count")
        points = []
        previous_end = None
        for edge_use in edge_uses:
            start_3d, end_3d = _line_points(edges[edge_use["edge_id"]], edge_use["orientation"])
            start = _project(start_3d, frame)
            end = _project(end_3d, frame)
            if previous_end is not None and math.dist(previous_end, start) > LINEAR_TOLERANCE_MM:
                raise ProfileReconstructionError("open_profile_loop")
            points.append(start)
            previous_end = end
        if math.dist(previous_end, points[0]) > LINEAR_TOLERANCE_MM:
            raise ProfileReconstructionError("open_profile_loop")
        points = validate_simple_polygon(points)
        if _orientation_area_twice(points) < 0.0:
            points = list(reversed(points))
        primitives = [
            {
                "primitive_id": f"line_{index + 1}",
                "type": "line",
                "start": list(point),
                "end": list(points[(index + 1) % len(points)]),
            }
            for index, point in enumerate(points)
        ]
    elif edge_types == {"circle"} and len(edge_uses) == 1:
        edge = edges[edge_uses[0]["edge_id"]]
        if edge.get("circle_form") != "full_circle":
            raise ProfileReconstructionError("unsupported_circular_arc")
        center = _project(edge["curve_parameters"]["center_mm"], frame)
        primitives = [
            {
                "primitive_id": "circle_1",
                "type": "circle",
                "center": list(center),
                "radius_mm": edge["curve_parameters"]["radius_mm"],
            }
        ]
    elif "circle" in edge_types and len(edge_types) > 1:
        raise ProfileReconstructionError("mixed_profile_curves")
    elif "bspline" in edge_types:
        raise ProfileReconstructionError("unsupported_spline_profile")
    else:
        raise ProfileReconstructionError("unsupported_profile_curves")

    return {
        "sketch_plane": plane,
        "loop": {
            "loop_id": "base_outer",
            "loop_type": "outer",
            "primitives": primitives,
        },
    }


def _select_candidate(candidates, candidate_id):
    accepted = [item for item in candidates if item["status"] == "accepted"]
    if candidate_id is None:
        if len(accepted) != 1:
            raise ProfileReconstructionError("ambiguous_prevalidation_candidates")
        return accepted[0]
    selected = [item for item in accepted if item["candidate_id"] == candidate_id]
    if len(selected) != 1:
        raise ProfileReconstructionError("candidate_not_found_or_rejected")
    return selected[0]


def recover_sequence(path, model_id, candidate_id=None):
    path = Path(path)
    summary, context = brep_inspection.inspect_step_with_context(path, model_id)
    adjacency = topology_adjacency.build_adjacency(summary, context)
    candidates = extrusion_inference.generate_candidates(summary, adjacency)["candidates"]
    candidate = _select_candidate(candidates, candidate_id)
    return sequence_from_summary(summary, candidate)


def sequence_from_summary(summary, candidate):
    reconstructed = reconstruct_profile(summary, candidate)
    plane = reconstructed["sketch_plane"]
    return {
        "schema_version": "cadseq-0.2",
        "model_id": summary["model_id"],
        "source_step_sha256": summary["source_step_sha256"],
        "units": "mm",
        "tolerance": {
            "length_mm": LINEAR_TOLERANCE_MM,
            "angular_rad": ANGULAR_TOLERANCE_RAD,
        },
        "replay_status": "pending",
        "replay_mode": "automatic",
        "corrections": [],
        "operations": [
            {
                "operation_id": "sketch_base",
                "operation_type": "sketch",
                "dependencies": [],
                "replay_status": "pending",
                "sketch_plane": plane,
                "loops": [reconstructed["loop"]],
            },
            {
                "operation_id": "extrude_base",
                "operation_type": "extrude",
                "dependencies": ["sketch_base"],
                "replay_status": "pending",
                "profile": {
                    "sketch_id": "sketch_base",
                    "outer_loop_id": "base_outer",
                    "inner_loop_ids": [],
                },
                "direction": candidate["extrusion_direction"],
                "extent": {"type": "distance", "distance_mm": candidate["distance_mm"]},
                "boolean_type": "new",
            },
        ],
    }


def write_sequence(sequence, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(sequence))
    return output
