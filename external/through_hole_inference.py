"""Gate 3 fact analysis for one coupled base-extrusion and through-hole hypothesis."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


LINEAR_TOLERANCE_MM = 1e-6
ANGULAR_TOLERANCE = 1e-8
SUPPORTED_END_FACE_ORIENTATIONS = {"forward", "reversed"}


class ThroughHoleInferenceError(ValueError):
    """Raised when Gate 3 fact inputs violate the frozen interface contract."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def load_gate3_development_cases(project_root):
    """Derive D-H01 through D-H05 without exposing labels or geometry."""

    project_root = Path(project_root)
    matrix = json.loads(
        (project_root / "benchmarks" / "case_matrix.json").read_text(encoding="utf-8")
    )
    selected = []
    for case in matrix.get("cases", []):
        case_id = case.get("case_id")
        if (
            case.get("split") == "development"
            and case.get("family") == "through_hole"
            and isinstance(case_id, str)
            and re.fullmatch(r"D-H0[1-5]", case_id)
        ):
            selected.append(
                {
                    "case_id": case_id,
                    "split": case.get("split"),
                    "family": case.get("family"),
                    "output_step": case.get("output_step"),
                    "source": case.get("source"),
                    "units": matrix.get("units"),
                }
            )
    selected.sort(key=lambda item: item["case_id"])
    if [item["case_id"] for item in selected] != [f"D-H{i:02d}" for i in range(1, 6)]:
        raise ThroughHoleInferenceError("gate3_case_selection_mismatch")
    return selected


def validate_gate3_development_input(project_root, case_id, input_path):
    """Guard the development-only Gate 3 entry point before STEP inspection."""

    project_root = Path(project_root).resolve()
    input_path = Path(input_path).resolve()
    held_out = (project_root / "benchmarks" / "inputs" / "held_out").resolve()
    if input_path.is_relative_to(held_out):
        raise ThroughHoleInferenceError("held_out_input_forbidden")
    cases = load_gate3_development_cases(project_root)
    frozen_paths = {
        (project_root / case["output_step"]).resolve()
        for case in cases
    }
    if input_path not in frozen_paths:
        raise ThroughHoleInferenceError("input_not_frozen_development")
    case_by_id = {case["case_id"]: case for case in cases}
    selected = case_by_id.get(case_id)
    if selected is None or input_path != (project_root / selected["output_step"]).resolve():
        raise ThroughHoleInferenceError("case_id_path_mismatch")
    return input_path


def _subtract(left, right):
    return [left[index] - right[index] for index in range(3)]


def _add(left, right):
    return [left[index] + right[index] for index in range(3)]


def _scale(vector, factor):
    values = [component * factor for component in vector]
    return [0.0 if value == 0.0 else value for value in values]


def _dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def _cross(left, right):
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _norm(vector):
    return math.sqrt(_dot(vector, vector))


def _normalize(vector):
    length = _norm(vector)
    return [component / length for component in vector]


def _distance(left, right):
    return _norm(_subtract(left, right))


def _check(name, measurement, passed, failure_reason):
    return {
        "name": name,
        "measurement": measurement,
        "passed": bool(passed),
        "reason": None if passed else failure_reason,
    }


def _wire_kind(wire, edge_by_id):
    uses = wire["edge_uses"]
    edge_ids = [use["edge_id"] for use in uses]
    edges = [edge_by_id[edge_id] for edge_id in edge_ids]
    unique_edge_ids = set(edge_ids)
    if (
        wire.get("is_closed") is True
        and 3 <= len(unique_edge_ids) <= 8
        and len(unique_edge_ids) == len(edge_ids)
        and all(edge["curve_type"] == "line" for edge in edges)
    ):
        return "line_only"
    if (
        wire.get("is_closed") is True
        and len(uses) == 1
        and edges[0]["curve_type"] == "circle"
        and edges[0].get("circle_form") == "full_circle"
    ):
        return "full_circle"
    return "unresolved"


def _planar_wire_roles(solid, wire_by_id, edge_by_id):
    roles = []
    for face in sorted(solid["faces"], key=lambda item: item["face_id"]):
        if face["surface_type"] != "plane":
            continue
        classified = []
        for use in face["wire_uses"]:
            wire = wire_by_id[use["wire_id"]]
            classified.append((use["wire_id"], _wire_kind(wire, edge_by_id)))
        line_wires = sorted(wire_id for wire_id, kind in classified if kind == "line_only")
        circle_wires = sorted(wire_id for wire_id, kind in classified if kind == "full_circle")
        checks = [
            _check(
                "exactly_two_face_wires",
                {"wire_ids": sorted(wire_id for wire_id, _ in classified)},
                len(classified) == 2,
                "planar_face_does_not_have_exactly_two_wires",
            ),
            _check(
                "one_line_outer_wire",
                {"wire_ids": line_wires},
                len(line_wires) == 1,
                "line_outer_wire_not_unique",
            ),
            _check(
                "one_full_circle_inner_wire",
                {"wire_ids": circle_wires},
                len(circle_wires) == 1,
                "circular_inner_wire_not_unique",
            ),
        ]
        if not all(check["passed"] for check in checks):
            continue
        circle_wire = wire_by_id[circle_wires[0]]
        roles.append(
            {
                "face_id": face["face_id"],
                "outer_wire_id": line_wires[0],
                "outer_wire_kind": "line_only",
                "inner_circle_wire_ids": circle_wires,
                "inner_circle_edge_ids": [circle_wire["edge_uses"][0]["edge_id"]],
                "checks": checks,
            }
        )
    return roles


def _cylinder_circle_edges(face, wire_by_id, edge_by_id):
    edge_ids = set()
    for wire_use in face["wire_uses"]:
        for edge_use in wire_by_id[wire_use["wire_id"]]["edge_uses"]:
            edge = edge_by_id[edge_use["edge_id"]]
            if edge["curve_type"] == "circle" and edge.get("circle_form") == "full_circle":
                edge_ids.add(edge["edge_id"])
    return sorted(edge_ids)


def _diagnostic_adjacency(adjacency, cylinder_face_id, circle_edge_ids):
    diagnostics = []
    circle_ids = set(circle_edge_ids)
    for relation in adjacency["relations"]:
        faces = {relation["face_1_id"], relation["face_2_id"]}
        if cylinder_face_id not in faces or relation["shared_edge_id"] not in circle_ids:
            continue
        diagnostics.append(
            {
                "relation_id": relation["relation_id"],
                "shared_edge_id": relation["shared_edge_id"],
                "classification": relation["classification"],
                "signed_angle_rad": relation["signed_angle_rad"],
            }
        )
    return sorted(diagnostics, key=lambda item: item["relation_id"])


def _hole_fact_group(face, cylinder_count, roles, wire_by_id, edge_by_id, adjacency):
    circle_edge_ids = _cylinder_circle_edges(face, wire_by_id, edge_by_id)
    role_by_circle = {}
    for role in roles:
        for edge_id in role["inner_circle_edge_ids"]:
            role_by_circle.setdefault(edge_id, []).append(role)
    matched_roles = []
    if len(circle_edge_ids) == 2:
        for edge_id in circle_edge_ids:
            matches = role_by_circle.get(edge_id, [])
            if len(matches) == 1:
                matched_roles.append(matches[0])

    parameters = face["surface_parameters"]
    axis_origin = parameters["axis_origin_mm"]
    axis = _normalize(parameters["axis_direction"])
    cylinder_radius = parameters["radius_mm"]
    circle_edges = [edge_by_id[edge_id] for edge_id in circle_edge_ids]
    radii = [edge["curve_parameters"]["radius_mm"] for edge in circle_edges]
    centers = [edge["curve_parameters"]["center_mm"] for edge in circle_edges]

    radius_error = None
    cylinder_radius_error = None
    axis_residual = None
    separation = None
    direction_residual = None
    if len(circle_edges) == 2:
        radius_error = abs(radii[0] - radii[1])
        cylinder_radius_error = max(abs(radius - cylinder_radius) for radius in radii)
        axis_residual = max(
            _norm(_cross(_subtract(center, axis_origin), axis)) for center in centers
        )
        delta = _subtract(centers[1], centers[0])
        separation = _norm(delta)
        if separation > LINEAR_TOLERANCE_MM:
            direction_residual = _norm(_cross(_normalize(delta), axis))

    planar_face_ids = [role["face_id"] for role in matched_roles]
    inner_wire_ids = [role["inner_circle_wire_ids"][0] for role in matched_roles]
    checks = [
        _check(
            "single_cylindrical_face",
            {"count": cylinder_count},
            cylinder_count == 1,
            "cylindrical_face_not_unique",
        ),
        _check(
            "two_full_circle_boundaries",
            {"circle_edge_ids": circle_edge_ids},
            len(circle_edge_ids) == 2,
            "cylinder_does_not_have_two_full_circle_boundaries",
        ),
        _check(
            "circles_on_two_planar_inner_wires",
            {
                "planar_face_ids": sorted(planar_face_ids),
                "inner_wire_ids": sorted(inner_wire_ids),
            },
            len(matched_roles) == 2
            and len(set(planar_face_ids)) == 2
            and len(set(inner_wire_ids)) == 2,
            "circle_boundaries_are_not_inner_wires_on_two_planar_faces",
        ),
        _check(
            "circle_radii_match_cylinder",
            {
                "circle_radii_mm": radii,
                "cylinder_radius_mm": cylinder_radius,
                "circle_radius_error_mm": radius_error,
                "cylinder_radius_error_mm": cylinder_radius_error,
                "tolerance_mm": LINEAR_TOLERANCE_MM,
            },
            len(radii) == 2
            and radius_error <= LINEAR_TOLERANCE_MM
            and cylinder_radius_error <= LINEAR_TOLERANCE_MM,
            "circle_or_cylinder_radius_mismatch",
        ),
        _check(
            "circle_centres_on_cylinder_axis",
            {
                "max_axis_residual_mm": axis_residual,
                "tolerance_mm": LINEAR_TOLERANCE_MM,
            },
            axis_residual is not None and axis_residual <= LINEAR_TOLERANCE_MM,
            "circle_centre_not_on_cylinder_axis",
        ),
        _check(
            "positive_coaxial_circle_separation",
            {
                "separation_mm": separation,
                "direction_residual": direction_residual,
                "linear_tolerance_mm": LINEAR_TOLERANCE_MM,
                "angular_tolerance": ANGULAR_TOLERANCE,
            },
            separation is not None
            and separation > LINEAR_TOLERANCE_MM
            and direction_residual <= ANGULAR_TOLERANCE,
            "circle_centres_do_not_define_positive_cylinder_span",
        ),
    ]
    accepted = all(check["passed"] for check in checks)
    return {
        "cylinder_face_id": face["face_id"],
        "circle_edge_ids": circle_edge_ids,
        "inner_wire_ids": sorted(inner_wire_ids),
        "planar_face_ids": sorted(planar_face_ids),
        "measured_axis": axis,
        "measured_radius_mm": cylinder_radius,
        "diagnostic_adjacency": _diagnostic_adjacency(
            adjacency,
            face["face_id"],
            circle_edge_ids,
        ),
        "checks": checks,
        "status": "accepted" if accepted else "rejected",
        "rejection_reasons": [check["reason"] for check in checks if not check["passed"]],
    }


def analyze_through_hole_facts(summary, adjacency):
    """Return the narrow Gate 3 topology evidence derived from canonical facts."""

    if (
        summary.get("brep_summary_schema") != "brep-summary-0.1"
        or adjacency.get("adjacency_schema") != "face-adjacency-0.1"
    ):
        raise ThroughHoleInferenceError(
            "unsupported_fact_schema: expected brep-summary-0.1 and face-adjacency-0.1"
        )
    if (
        summary.get("model_id") != adjacency.get("model_id")
        or summary.get("source_step_sha256") != adjacency.get("source_step_sha256")
    ):
        raise ThroughHoleInferenceError(
            "summary_adjacency_mismatch: model_id and source_step_sha256 must match"
        )
    solid = summary["solids"][0]
    wire_by_id = {wire["wire_id"]: wire for wire in solid["wires"]}
    edge_by_id = {edge["edge_id"]: edge for edge in solid["edges"]}
    roles = _planar_wire_roles(solid, wire_by_id, edge_by_id)
    cylinders = sorted(
        (face for face in solid["faces"] if face["surface_type"] == "cylinder"),
        key=lambda item: item["face_id"],
    )
    groups = [
        _hole_fact_group(
            face,
            len(cylinders),
            roles,
            wire_by_id,
            edge_by_id,
            adjacency,
        )
        for face in cylinders
    ]
    rejection_reasons = []
    if not cylinders:
        rejection_reasons.append("no_cylindrical_face")
    elif not any(group["status"] == "accepted" for group in groups):
        rejection_reasons.append("no_accepted_hole_fact_group")
    return {
        "through_hole_facts_schema": "through-hole-facts-0.1",
        "model_id": summary["model_id"],
        "source_step_sha256": summary["source_step_sha256"],
        "tolerances": {
            "linear_mm": LINEAR_TOLERANCE_MM,
            "angular": ANGULAR_TOLERANCE,
        },
        "planar_wire_roles": roles,
        "hole_fact_groups": groups,
        "rejection_reasons": rejection_reasons,
    }


def _plane_outward_normal(face):
    if face.get("orientation") not in SUPPORTED_END_FACE_ORIENTATIONS:
        return [0.0, 0.0, 0.0]
    normal = list(face["surface_parameters"]["normal"])
    if face["orientation"] == "reversed":
        normal = _scale(normal, -1.0)
    return _normalize(normal)


def _line_edges_match(first, second, vertex_by_id, translation):
    first_points = [vertex_by_id[item]["point_mm"] for item in first["vertex_ids"]]
    second_points = [vertex_by_id[item]["point_mm"] for item in second["vertex_ids"]]
    if len(first_points) != 2 or len(second_points) != 2:
        return False
    translated = [_add(point, translation) for point in first_points]
    return (
        _distance(translated[0], second_points[0]) <= LINEAR_TOLERANCE_MM
        and _distance(translated[1], second_points[1]) <= LINEAR_TOLERANCE_MM
    ) or (
        _distance(translated[0], second_points[1]) <= LINEAR_TOLERANCE_MM
        and _distance(translated[1], second_points[0]) <= LINEAR_TOLERANCE_MM
    )


def _match_outer_wires(first_wire, second_wire, edge_by_id, vertex_by_id, translation):
    first_ids = sorted(use["edge_id"] for use in first_wire["edge_uses"])
    unmatched = set(use["edge_id"] for use in second_wire["edge_uses"])
    matches = []
    if len(first_ids) != len(unmatched):
        return []
    for first_id in first_ids:
        choices = [
            second_id
            for second_id in sorted(unmatched)
            if _line_edges_match(
                edge_by_id[first_id],
                edge_by_id[second_id],
                vertex_by_id,
                translation,
            )
        ]
        if len(choices) != 1:
            return []
        second_id = choices[0]
        unmatched.remove(second_id)
        matches.append([first_id, second_id])
    return matches if not unmatched else []


def _neighbors_for_edge(adjacency, edge_id, face_id):
    neighbors = []
    for relation in adjacency["relations"]:
        if relation["shared_edge_id"] != edge_id:
            continue
        if relation["face_1_id"] == face_id:
            neighbors.append(relation["face_2_id"])
        elif relation["face_2_id"] == face_id:
            neighbors.append(relation["face_1_id"])
    return sorted(set(neighbors))


def _outer_side_coverage(matches, adjacency, first_face_id, second_face_id):
    if not matches:
        return 0.0
    covered = 0
    for first_edge_id, second_edge_id in matches:
        first_neighbors = _neighbors_for_edge(adjacency, first_edge_id, first_face_id)
        second_neighbors = _neighbors_for_edge(adjacency, second_edge_id, second_face_id)
        if len(first_neighbors) == 1 and first_neighbors == second_neighbors:
            covered += 1
    return covered / len(matches)


def _coupled_candidate(summary, adjacency, hole_group, role_by_face):
    solid = summary["solids"][0]
    face_by_id = {face["face_id"]: face for face in solid["faces"]}
    wire_by_id = {wire["wire_id"]: wire for wire in solid["wires"]}
    edge_by_id = {edge["edge_id"]: edge for edge in solid["edges"]}
    vertex_by_id = {vertex["vertex_id"]: vertex for vertex in solid["vertices"]}
    end_face_ids = sorted(hole_group["planar_face_ids"])
    first_face = face_by_id[end_face_ids[0]]
    second_face = face_by_id[end_face_ids[1]]
    first_role = role_by_face[first_face["face_id"]]
    second_role = role_by_face[second_face["face_id"]]
    first_outer = wire_by_id[first_role["outer_wire_id"]]
    second_outer = wire_by_id[second_role["outer_wire_id"]]
    orientation_records = [
        {"face_id": face["face_id"], "orientation": face.get("orientation")}
        for face in (first_face, second_face)
    ]
    orientations_supported = all(
        item["orientation"] in SUPPORTED_END_FACE_ORIENTATIONS
        for item in orientation_records
    )

    translation = _subtract(second_face["centroid_mm"], first_face["centroid_mm"])
    distance = _norm(translation)
    direction = _normalize(translation) if distance > LINEAR_TOLERANCE_MM else [0.0] * 3
    first_normal = _plane_outward_normal(first_face)
    second_normal = _plane_outward_normal(second_face)
    cut_direction = _scale(direction, -1.0)
    support_normal_dot_cut = _dot(second_normal, cut_direction)
    normal_dot = _dot(first_normal, second_normal)
    centroid_residual = abs(abs(_dot(translation, first_normal)) - distance)
    matches = _match_outer_wires(
        first_outer,
        second_outer,
        edge_by_id,
        vertex_by_id,
        translation,
    )
    outer_coverage = _outer_side_coverage(
        matches,
        adjacency,
        first_face["face_id"],
        second_face["face_id"],
    )
    axis_alignment = abs(_dot(direction, hole_group["measured_axis"]))
    circle_centres = [
        edge_by_id[edge_id]["curve_parameters"]["center_mm"]
        for edge_id in hole_group["circle_edge_ids"]
    ]
    cylinder_span = _distance(circle_centres[0], circle_centres[1])
    span_error = abs(cylinder_span - distance)

    checks = [
        _check(
            "accepted_hole_fact_group",
            {"status": hole_group["status"]},
            hole_group["status"] == "accepted",
            "hole_fact_group_not_accepted",
        ),
        _check(
            "supported_end_face_orientations",
            {
                "end_faces": orientation_records,
                "supported_orientations": sorted(SUPPORTED_END_FACE_ORIENTATIONS),
            },
            orientations_supported,
            "unsupported_end_face_orientation",
        ),
        _check(
            "opposite_end_face_normals",
            {"normal_dot": normal_dot, "tolerance": ANGULAR_TOLERANCE},
            normal_dot <= -1.0 + ANGULAR_TOLERANCE,
            "end_face_normals_not_opposite",
        ),
        _check(
            "positive_base_distance",
            {"distance_mm": distance, "tolerance_mm": LINEAR_TOLERANCE_MM},
            distance > LINEAR_TOLERANCE_MM,
            "base_distance_not_positive",
        ),
        _check(
            "cut_direction_into_material_from_support_face",
            {
                "support_face_id": second_face["face_id"],
                "support_face_outward_normal": second_normal,
                "cut_direction": cut_direction,
                "normal_dot_cut_direction": support_normal_dot_cut,
                "tolerance": ANGULAR_TOLERANCE,
            },
            abs(support_normal_dot_cut + 1.0) <= ANGULAR_TOLERANCE,
            "cut_direction_not_into_material",
        ),
        _check(
            "end_face_centroid_alignment",
            {"residual_mm": centroid_residual, "tolerance_mm": LINEAR_TOLERANCE_MM},
            centroid_residual <= LINEAR_TOLERANCE_MM,
            "end_face_centroids_not_axis_aligned",
        ),
        _check(
            "outer_wire_translation",
            {
                "matched_edge_pairs": matches,
                "expected_edge_count": len(first_outer["edge_uses"]),
                "tolerance_mm": LINEAR_TOLERANCE_MM,
            },
            len(matches) == len(first_outer["edge_uses"]) == len(second_outer["edge_uses"]),
            "outer_wires_do_not_match_by_translation",
        ),
        _check(
            "outer_side_connection_coverage",
            {"coverage": outer_coverage, "required": 1.0},
            outer_coverage >= 1.0 - 1e-12,
            "outer_edges_do_not_share_corresponding_side_faces",
        ),
        _check(
            "hole_axis_parallel_to_base",
            {"absolute_dot": axis_alignment, "tolerance": ANGULAR_TOLERANCE},
            axis_alignment >= 1.0 - ANGULAR_TOLERANCE,
            "hole_axis_not_parallel_to_base_extrusion",
        ),
        _check(
            "cylinder_span_matches_base_distance",
            {
                "cylinder_span_mm": cylinder_span,
                "base_distance_mm": distance,
                "error_mm": span_error,
                "tolerance_mm": LINEAR_TOLERANCE_MM,
            },
            span_error <= LINEAR_TOLERANCE_MM,
            "cylinder_span_does_not_match_base_distance",
        ),
    ]
    accepted = all(check["passed"] for check in checks)
    return {
        "candidate_id": (
            f"coupled-{first_face['face_id']}-{second_face['face_id']}-"
            f"{hole_group['cylinder_face_id']}"
        ),
        "base": {
            "base_face_id": first_face["face_id"],
            "opposite_face_id": second_face["face_id"],
            "end_face_ids": end_face_ids,
            "outer_wire_ids": [first_role["outer_wire_id"], second_role["outer_wire_id"]],
            "matched_outer_edge_pairs": matches,
            "source_face_outward_normal": first_normal,
            "extrusion_direction": direction,
            "distance_mm": distance,
        },
        "hole": {
            "cylinder_face_id": hole_group["cylinder_face_id"],
            "circle_edge_ids": hole_group["circle_edge_ids"],
            "inner_wire_ids": hole_group["inner_wire_ids"],
            "planar_face_ids": hole_group["planar_face_ids"],
            "axis": hole_group["measured_axis"],
            "radius_mm": hole_group["measured_radius_mm"],
        },
        "semantic_replay": {
            "operation_cap": {
                "type": "operation_cap",
                "operation_id": "extrude_base",
                "role": "positive_end_cap",
                "offset_mm": 0.0,
            },
            "support_face_id": second_face["face_id"],
            "cut_direction": cut_direction,
        },
        "checks": checks,
        "status": "accepted" if accepted else "rejected",
        "rejection_reasons": [check["reason"] for check in checks if not check["passed"]],
    }


def _validated_candidate_fact_structure(summary, hole_facts):
    def malformed():
        raise ThroughHoleInferenceError("malformed_candidate_facts")

    def canonical_map(items, id_field):
        if not isinstance(items, list):
            malformed()
        mapped = {}
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get(id_field), str)
                or item[id_field] in mapped
            ):
                malformed()
            mapped[item[id_field]] = item
        return mapped

    def wire_edge_ids(wire, edge_by_id):
        uses = wire.get("edge_uses")
        if not isinstance(uses, list) or not uses:
            malformed()
        edge_ids = []
        for use in uses:
            if (
                not isinstance(use, dict)
                or not isinstance(use.get("edge_id"), str)
                or use["edge_id"] not in edge_by_id
            ):
                malformed()
            edge_ids.append(use["edge_id"])
        return edge_ids

    def face_wire_ids(face, wire_by_id):
        uses = face.get("wire_uses")
        if not isinstance(uses, list) or not uses:
            malformed()
        wire_ids = []
        for use in uses:
            if (
                not isinstance(use, dict)
                or not isinstance(use.get("wire_id"), str)
                or use["wire_id"] not in wire_by_id
            ):
                malformed()
            wire_ids.append(use["wire_id"])
        return wire_ids

    solids = summary.get("solids")
    if not isinstance(solids, list) or len(solids) != 1 or not isinstance(solids[0], dict):
        malformed()
    solid = solids[0]
    face_by_id = canonical_map(solid.get("faces"), "face_id")
    wire_by_id = canonical_map(solid.get("wires"), "wire_id")
    edge_by_id = canonical_map(solid.get("edges"), "edge_id")

    groups = hole_facts.get("hole_fact_groups")
    roles = hole_facts.get("planar_wire_roles")
    if not isinstance(groups, list) or not isinstance(roles, list):
        malformed()

    accepted_groups = []
    for group in groups:
        if not isinstance(group, dict):
            malformed()
        if group.get("status") != "accepted":
            continue
        planar_face_ids = group.get("planar_face_ids")
        circle_edge_ids = group.get("circle_edge_ids")
        inner_wire_ids = group.get("inner_wire_ids")
        measured_axis = group.get("measured_axis")
        measured_radius = group.get("measured_radius_mm")
        if (
            not isinstance(group.get("cylinder_face_id"), str)
            or not isinstance(planar_face_ids, list)
            or len(planar_face_ids) != 2
            or not all(isinstance(face_id, str) for face_id in planar_face_ids)
            or len(set(planar_face_ids)) != 2
            or not isinstance(circle_edge_ids, list)
            or len(circle_edge_ids) != 2
            or not all(isinstance(edge_id, str) for edge_id in circle_edge_ids)
            or len(set(circle_edge_ids)) != 2
            or not isinstance(inner_wire_ids, list)
            or len(inner_wire_ids) != 2
            or not all(isinstance(wire_id, str) for wire_id in inner_wire_ids)
            or len(set(inner_wire_ids)) != 2
            or not isinstance(measured_axis, list)
            or len(measured_axis) != 3
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in measured_axis
            )
            or _norm(measured_axis) == 0.0
            or not isinstance(measured_radius, (int, float))
            or isinstance(measured_radius, bool)
            or not math.isfinite(measured_radius)
            or measured_radius <= 0.0
        ):
            malformed()

        cylinder_face = face_by_id.get(group["cylinder_face_id"])
        planar_faces = [face_by_id.get(face_id) for face_id in planar_face_ids]
        circle_edges = [edge_by_id.get(edge_id) for edge_id in circle_edge_ids]
        inner_wires = [wire_by_id.get(wire_id) for wire_id in inner_wire_ids]
        if (
            cylinder_face is None
            or cylinder_face.get("surface_type") != "cylinder"
            or group["cylinder_face_id"] in planar_face_ids
            or any(face is None or face.get("surface_type") != "plane" for face in planar_faces)
            or any(
                edge is None
                or edge.get("curve_type") != "circle"
                or edge.get("circle_form") != "full_circle"
                for edge in circle_edges
            )
            or any(wire is None or wire.get("is_closed") is not True for wire in inner_wires)
        ):
            malformed()

        cylinder_edge_ids = set()
        for wire_id in face_wire_ids(cylinder_face, wire_by_id):
            cylinder_edge_ids.update(wire_edge_ids(wire_by_id[wire_id], edge_by_id))
        if not set(circle_edge_ids).issubset(cylinder_edge_ids):
            malformed()
        inner_edge_ids = []
        for wire in inner_wires:
            ids = wire_edge_ids(wire, edge_by_id)
            if len(ids) != 1:
                malformed()
            inner_edge_ids.extend(ids)
        if set(inner_edge_ids) != set(circle_edge_ids):
            malformed()
        accepted_groups.append(group)

    role_by_face = {}
    for role in roles:
        if (
            not isinstance(role, dict)
            or not isinstance(role.get("face_id"), str)
            or not isinstance(role.get("outer_wire_id"), str)
            or role["face_id"] in role_by_face
        ):
            malformed()
        role_by_face[role["face_id"]] = role

    for group in accepted_groups:
        group_inner_wire_ids = set(group["inner_wire_ids"])
        group_circle_edge_ids = set(group["circle_edge_ids"])
        role_inner_wire_ids = set()
        role_circle_edge_ids = set()
        for face_id in group["planar_face_ids"]:
            role = role_by_face.get(face_id)
            if role is None:
                malformed()
            outer_wire_id = role["outer_wire_id"]
            inner_ids = role.get("inner_circle_wire_ids")
            circle_ids = role.get("inner_circle_edge_ids")
            if (
                role.get("outer_wire_kind") != "line_only"
                or not isinstance(inner_ids, list)
                or len(inner_ids) != 1
                or not isinstance(inner_ids[0], str)
                or not isinstance(circle_ids, list)
                or len(circle_ids) != 1
                or not isinstance(circle_ids[0], str)
                or outer_wire_id not in wire_by_id
                or inner_ids[0] not in wire_by_id
                or circle_ids[0] not in edge_by_id
            ):
                malformed()
            face = face_by_id[face_id]
            incident_wire_ids = set(face_wire_ids(face, wire_by_id))
            if outer_wire_id not in incident_wire_ids or inner_ids[0] not in incident_wire_ids:
                malformed()
            outer_wire = wire_by_id[outer_wire_id]
            outer_edge_ids = wire_edge_ids(outer_wire, edge_by_id)
            if (
                outer_wire.get("is_closed") is not True
                or not 3 <= len(set(outer_edge_ids)) <= 8
                or len(outer_edge_ids) != len(set(outer_edge_ids))
                or any(edge_by_id[edge_id].get("curve_type") != "line" for edge_id in outer_edge_ids)
            ):
                malformed()
            inner_wire = wire_by_id[inner_ids[0]]
            if wire_edge_ids(inner_wire, edge_by_id) != circle_ids:
                malformed()
            role_inner_wire_ids.add(inner_ids[0])
            role_circle_edge_ids.add(circle_ids[0])
        if (
            role_inner_wire_ids != group_inner_wire_ids
            or role_circle_edge_ids != group_circle_edge_ids
        ):
            malformed()
    return accepted_groups, role_by_face


def generate_coupled_candidates(summary, adjacency, hole_facts):
    """Return coupled base-extrusion and through-hole pre-validation candidates."""

    if (
        summary.get("brep_summary_schema") != "brep-summary-0.1"
        or adjacency.get("adjacency_schema") != "face-adjacency-0.1"
    ):
        raise ThroughHoleInferenceError("candidate_input_schema_mismatch")
    if (
        hole_facts.get("through_hole_facts_schema") != "through-hole-facts-0.1"
        or hole_facts.get("model_id") != summary.get("model_id")
        or hole_facts.get("source_step_sha256") != summary.get("source_step_sha256")
        or adjacency.get("model_id") != summary.get("model_id")
        or adjacency.get("source_step_sha256") != summary.get("source_step_sha256")
    ):
        raise ThroughHoleInferenceError(
            "hole_facts_mismatch: schema, model_id, and source_step_sha256 must match"
        )
    accepted_groups, role_by_face = _validated_candidate_fact_structure(summary, hole_facts)
    candidates = [
        _coupled_candidate(summary, adjacency, group, role_by_face)
        for group in accepted_groups
    ]
    candidates.sort(key=lambda item: item["candidate_id"])
    rejection_reasons = []
    if not accepted_groups:
        rejection_reasons.append("no_accepted_hole_fact_group")
    return {
        "coupled_candidates_schema": "coupled-through-hole-candidates-0.1",
        "model_id": summary["model_id"],
        "source_step_sha256": summary["source_step_sha256"],
        "ordering": "candidate_id",
        "candidates": candidates,
        "rejection_reasons": rejection_reasons,
    }
