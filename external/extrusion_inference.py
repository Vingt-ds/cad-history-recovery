"""Fact-only pre-validation hypotheses for canonical single extrusions."""

from __future__ import annotations

import itertools
import math
from pathlib import Path

import brep_inspection
import topology_adjacency


LINEAR_TOLERANCE_MM = 1e-6
ANGULAR_DOT_TOLERANCE = 1e-9
AREA_RELATIVE_TOLERANCE = 1e-9
canonical_json_bytes = brep_inspection.canonical_json_bytes


def _subtract(left, right):
    return tuple(float(a) - float(b) for a, b in zip(left, right))


def _add(left, right):
    return tuple(float(a) + float(b) for a, b in zip(left, right))


def _scale(vector, factor):
    return tuple(float(value) * float(factor) for value in vector)


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _norm(vector):
    return math.sqrt(_dot(vector, vector))


def _normalize(vector):
    length = _norm(vector)
    if length <= LINEAR_TOLERANCE_MM:
        return None
    return tuple(value / length for value in vector)


def _distance(left, right):
    return _norm(_subtract(left, right))


def _plane_outward_normal(face):
    normal = tuple(face["surface_parameters"]["normal"])
    if face["orientation"] == "reversed":
        normal = _scale(normal, -1.0)
    elif face["orientation"] != "forward":
        return None
    return _normalize(normal)


def _face_edges(face, wires):
    edge_ids = []
    for wire_use in face["wire_uses"]:
        for edge_use in wires[wire_use["wire_id"]]["edge_uses"]:
            if edge_use["edge_id"] not in edge_ids:
                edge_ids.append(edge_use["edge_id"])
    return edge_ids


def _points_match_translated(edge_1, edge_2, vertices, translation):
    points_1 = [tuple(vertices[item]["point_mm"]) for item in edge_1["vertex_ids"]]
    points_2 = [tuple(vertices[item]["point_mm"]) for item in edge_2["vertex_ids"]]
    if len(points_1) != 2 or len(points_2) != 2:
        return False
    translated = [_add(point, translation) for point in points_1]
    direct = _distance(translated[0], points_2[0]) <= LINEAR_TOLERANCE_MM and _distance(
        translated[1], points_2[1]
    ) <= LINEAR_TOLERANCE_MM
    reverse = _distance(translated[0], points_2[1]) <= LINEAR_TOLERANCE_MM and _distance(
        translated[1], points_2[0]
    ) <= LINEAR_TOLERANCE_MM
    return direct or reverse


def _circles_match_translated(edge_1, edge_2, translation):
    if edge_1.get("circle_form") != "full_circle" or edge_2.get("circle_form") != "full_circle":
        return False
    first = edge_1["curve_parameters"]
    second = edge_2["curve_parameters"]
    centers_match = _distance(_add(first["center_mm"], translation), second["center_mm"]) <= LINEAR_TOLERANCE_MM
    axes_match = abs(_dot(first["axis_direction"], second["axis_direction"])) >= 1.0 - ANGULAR_DOT_TOLERANCE
    radii_match = abs(float(first["radius_mm"]) - float(second["radius_mm"])) <= LINEAR_TOLERANCE_MM
    return centers_match and axes_match and radii_match


def _boundary_match(face_1, face_2, wires, edges, vertices, translation):
    edge_ids_1 = _face_edges(face_1, wires)
    edge_ids_2 = _face_edges(face_2, wires)
    if len(edge_ids_1) != len(edge_ids_2):
        return False, "edge_count_mismatch", []

    edge_types = {edges[item]["curve_type"] for item in edge_ids_1 + edge_ids_2}
    if edge_types == {"line"}:
        kind = "translated_lines"
        matcher = lambda first, second: _points_match_translated(first, second, vertices, translation)
    elif len(edge_ids_1) == 1 and len(edge_ids_2) == 1 and edge_types == {"circle"}:
        kind = "translated_full_circle"
        matcher = lambda first, second: _circles_match_translated(first, second, translation)
    else:
        return False, "unsupported_boundary_curves", []

    unmatched = set(edge_ids_2)
    matches = []
    for edge_id_1 in sorted(edge_ids_1):
        matching = [edge_id_2 for edge_id_2 in sorted(unmatched) if matcher(edges[edge_id_1], edges[edge_id_2])]
        if len(matching) != 1:
            return False, kind, matches
        edge_id_2 = matching[0]
        unmatched.remove(edge_id_2)
        matches.append((edge_id_1, edge_id_2))
    return not unmatched, kind, matches


def _neighbor_for_edge(adjacency, edge_id, face_id):
    neighbors = []
    for relation in adjacency["relations"]:
        if relation["shared_edge_id"] != edge_id:
            continue
        if relation["face_1_id"] == face_id:
            neighbors.append(relation["face_2_id"])
        elif relation["face_2_id"] == face_id:
            neighbors.append(relation["face_1_id"])
    return sorted(set(neighbors))


def _side_coverage(matches, adjacency, face_1_id, face_2_id):
    if not matches:
        return 0.0
    covered = 0
    for edge_1_id, edge_2_id in matches:
        side_1 = _neighbor_for_edge(adjacency, edge_1_id, face_1_id)
        side_2 = _neighbor_for_edge(adjacency, edge_2_id, face_2_id)
        if len(side_1) == 1 and side_1 == side_2:
            covered += 1
    return covered / len(matches)


def _check(passed, measured, tolerance=None):
    record = {"pass": bool(passed), "measured": measured}
    if tolerance is not None:
        record["tolerance"] = tolerance
    return record


def generate_candidates(summary, adjacency):
    solid = summary["solids"][0]
    faces = [item for item in solid["faces"] if item["surface_type"] == "plane"]
    wires = {item["wire_id"]: item for item in solid["wires"]}
    edges = {item["edge_id"]: item for item in solid["edges"]}
    vertices = {item["vertex_id"]: item for item in solid["vertices"]}
    candidates = []

    for face_1, face_2 in itertools.combinations(sorted(faces, key=lambda item: item["face_id"]), 2):
        normal_1 = _plane_outward_normal(face_1)
        normal_2 = _plane_outward_normal(face_2)
        translation = _subtract(face_2["centroid_mm"], face_1["centroid_mm"])
        distance = _norm(translation)
        direction = _normalize(translation)

        normal_dot = None if normal_1 is None or normal_2 is None else _dot(normal_1, normal_2)
        opposite_normals = normal_dot is not None and normal_dot <= -1.0 + ANGULAR_DOT_TOLERANCE
        positive_separation = distance > LINEAR_TOLERANCE_MM
        centroid_residual = None
        if normal_1 is not None and positive_separation:
            centroid_residual = abs(abs(_dot(translation, normal_1)) - distance)
        centroid_alignment = centroid_residual is not None and centroid_residual <= LINEAR_TOLERANCE_MM
        area_scale = max(abs(float(face_1["area_mm2"])), abs(float(face_2["area_mm2"])), 1.0)
        area_relative_error = abs(float(face_1["area_mm2"]) - float(face_2["area_mm2"])) / area_scale
        area_match = area_relative_error <= AREA_RELATIVE_TOLERANCE
        boundary_match, boundary_kind, matches = _boundary_match(
            face_1, face_2, wires, edges, vertices, translation
        )
        coverage = _side_coverage(matches, adjacency, face_1["face_id"], face_2["face_id"])
        side_coverage = boundary_match and coverage >= 1.0 - 1e-12

        checks = {
            "opposite_normals": _check(opposite_normals, normal_dot, ANGULAR_DOT_TOLERANCE),
            "positive_separation": _check(positive_separation, distance, LINEAR_TOLERANCE_MM),
            "centroid_alignment": _check(centroid_alignment, centroid_residual, LINEAR_TOLERANCE_MM),
            "area_match": _check(area_match, area_relative_error, AREA_RELATIVE_TOLERANCE),
            "boundary_translation_match": _check(
                boundary_match,
                {"kind": boundary_kind, "matched_edges": len(matches)},
                LINEAR_TOLERANCE_MM,
            ),
            "side_connection_coverage": _check(side_coverage, coverage, 1.0),
        }
        rejection_reasons = [name for name, check in checks.items() if not check["pass"]]
        candidates.append(
            {
                "candidate_id": f"extrusion-{face_1['face_id']}-{face_2['face_id']}",
                "base_face_id": face_1["face_id"],
                "opposite_face_id": face_2["face_id"],
                "source_face_outward_normal": None
                if normal_1 is None
                else [brep_inspection._q(value, 12) for value in normal_1],
                "extrusion_direction": None
                if direction is None
                else [brep_inspection._q(value, 12) for value in direction],
                "distance_mm": brep_inspection._q(distance),
                "boundary_match_kind": boundary_kind,
                "checks": checks,
                "score_components": {
                    "passed_hard_checks": sum(check["pass"] for check in checks.values()),
                    "total_hard_checks": len(checks),
                },
                "status": "accepted" if not rejection_reasons else "rejected",
                "rejection_reasons": rejection_reasons,
            }
        )

    candidates.sort(
        key=lambda item: (-item["score_components"]["passed_hard_checks"], item["candidate_id"])
    )
    return {
        "candidates_schema": "extrusion-candidates-0.1",
        "model_id": summary["model_id"],
        "source_step_sha256": summary["source_step_sha256"],
        "ordering": "passed_hard_checks_desc_then_candidate_id",
        "candidates": candidates,
    }


def infer_extrusions(path, model_id):
    """Inspect one STEP once, then derive adjacency and all planar-pair hypotheses."""
    summary, context = brep_inspection.inspect_step_with_context(Path(path), model_id)
    adjacency = topology_adjacency.build_adjacency(summary, context)
    return generate_candidates(summary, adjacency)


def write_candidates(result, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(result))
    return output
