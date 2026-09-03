"""Gate 3 fact analysis for one coupled base-extrusion and through-hole hypothesis."""

from __future__ import annotations

import math


LINEAR_TOLERANCE_MM = 1e-6
ANGULAR_TOLERANCE = 1e-8


class ThroughHoleInferenceError(ValueError):
    """Raised when Gate 3 fact inputs violate the frozen interface contract."""


def _subtract(left, right):
    return [left[index] - right[index] for index in range(3)]


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
        "rejection_reasons": [check["name"] for check in checks if not check["passed"]],
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
