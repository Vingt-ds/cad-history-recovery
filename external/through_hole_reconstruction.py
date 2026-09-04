"""Gate 3 four-operation through-hole sequence reconstruction."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import brep_inspection
import candidate_validation
import profile_reconstruction
import through_hole_inference
import topology_adjacency


LINEAR_TOLERANCE_MM = 1e-6
ANGULAR_TOLERANCE_RAD = 1e-8


class ThroughHoleReconstructionError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def sequence_from_summary(summary, candidate):
    if not isinstance(candidate, dict):
        raise ThroughHoleReconstructionError("malformed_candidate")
    if candidate.get("status") != "accepted":
        raise ThroughHoleReconstructionError("candidate_not_accepted")
    if (
        not isinstance(summary, dict)
        or summary.get("brep_summary_schema") != "brep-summary-0.1"
        or not isinstance(summary.get("model_id"), str)
        or not isinstance(summary.get("source_step_sha256"), str)
    ):
        raise ThroughHoleReconstructionError("summary_schema_mismatch")

    solids = summary.get("solids")
    if not isinstance(solids, list) or len(solids) != 1:
        raise ThroughHoleReconstructionError("malformed_candidate")
    solid = solids[0]
    try:
        face_by_id = _canonical_map(solid["faces"], "face_id")
        wire_by_id = _canonical_map(solid["wires"], "wire_id")
        edge_by_id = _canonical_map(solid["edges"], "edge_id")
        base = candidate["base"]
        hole = candidate["hole"]
        semantic = candidate["semantic_replay"]
        base_face_id = base["base_face_id"]
        opposite_face_id = base["opposite_face_id"]
        support_face_id = semantic["support_face_id"]
        direction = _unit_vector(base["extrusion_direction"])
        source_outward = _unit_vector(base["source_face_outward_normal"])
        distance = _positive_number(base["distance_mm"])
        cut_direction = _unit_vector(semantic["cut_direction"])
        radius = _positive_number(hole["radius_mm"])
        outer_wire_ids = _string_set(base["outer_wire_ids"])
        inner_wire_ids = _string_set(hole["inner_wire_ids"])
        circle_edge_ids = _string_set(hole["circle_edge_ids"])
        operation_cap = semantic["operation_cap"]
    except (KeyError, TypeError, ValueError):
        raise ThroughHoleReconstructionError("malformed_candidate") from None

    if (
        base_face_id not in face_by_id
        or opposite_face_id not in face_by_id
        or support_face_id != opposite_face_id
        or len(outer_wire_ids) != 2
        or len(inner_wire_ids) != 2
        or len(circle_edge_ids) != 2
        or _dot(source_outward, direction) > -1.0 + ANGULAR_TOLERANCE_RAD
        or _dot(direction, cut_direction) > -1.0 + ANGULAR_TOLERANCE_RAD
        or operation_cap
        != {
            "type": "operation_cap",
            "operation_id": "extrude_base",
            "role": "positive_end_cap",
            "offset_mm": 0.0,
        }
    ):
        raise ThroughHoleReconstructionError("malformed_candidate")

    base_face = face_by_id[base_face_id]
    base_incident = _face_wire_ids(base_face)
    selected_outer = sorted(base_incident & outer_wire_ids)
    if len(selected_outer) != 1:
        raise ThroughHoleReconstructionError("malformed_candidate_outer_wire")
    outer_wire = wire_by_id.get(selected_outer[0])
    if outer_wire is None or not _is_line_only_wire(outer_wire, edge_by_id):
        raise ThroughHoleReconstructionError("malformed_candidate_outer_wire")

    profile_candidate = {
        "status": "accepted",
        "base_face_id": base_face_id,
        "extrusion_direction": direction,
        "source_face_outward_normal": source_outward,
    }
    try:
        reconstructed = profile_reconstruction.reconstruct_profile(
            summary, profile_candidate, outer_wire_id=selected_outer[0]
        )
    except profile_reconstruction.ProfileReconstructionError as exc:
        raise ThroughHoleReconstructionError(
            f"malformed_candidate_profile:{exc.code}"
        ) from exc

    support_face = face_by_id[support_face_id]
    support_inner = sorted(_face_wire_ids(support_face) & inner_wire_ids)
    if len(support_inner) != 1:
        raise ThroughHoleReconstructionError("malformed_candidate_support_circle")
    support_wire = wire_by_id.get(support_inner[0])
    if support_wire is None:
        raise ThroughHoleReconstructionError("malformed_candidate_support_circle")
    incident_candidate_edges = [
        use.get("edge_id")
        for use in support_wire.get("edge_uses", [])
        if use.get("edge_id") in circle_edge_ids
    ]
    if len(incident_candidate_edges) != 1:
        raise ThroughHoleReconstructionError("malformed_candidate_support_circle")
    circle_edge = edge_by_id.get(incident_candidate_edges[0])
    if (
        circle_edge is None
        or circle_edge.get("curve_type") != "circle"
        or circle_edge.get("circle_form") != "full_circle"
    ):
        raise ThroughHoleReconstructionError("malformed_candidate_support_circle")
    edge_radius = circle_edge.get("curve_parameters", {}).get("radius_mm")
    if not _is_number(edge_radius) or abs(float(edge_radius) - radius) > LINEAR_TOLERANCE_MM:
        raise ThroughHoleReconstructionError("malformed_candidate_support_circle")

    base_plane = reconstructed["sketch_plane"]
    base_frame = base_plane["frame"]
    cap_origin = [
        brep_inspection._q(origin + component * distance)
        for origin, component in zip(base_frame["origin"], direction)
    ]
    hole_frame = {
        "origin": cap_origin,
        "normal": [brep_inspection._q(component, 12) for component in direction],
        "x_axis": list(base_frame["x_axis"]),
    }
    center_3d = circle_edge["curve_parameters"]["center_mm"]
    plane_residual = abs(_dot(_subtract(center_3d, cap_origin), direction))
    if plane_residual > LINEAR_TOLERANCE_MM:
        raise ThroughHoleReconstructionError("support_circle_not_on_positive_cap")
    center_2d = profile_reconstruction._project(center_3d, hole_frame)

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
                "sketch_plane": base_plane,
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
                "direction": direction,
                "extent": {"type": "distance", "distance_mm": distance},
                "boolean_type": "new",
            },
            {
                "operation_id": "sketch_hole",
                "operation_type": "sketch",
                "dependencies": ["extrude_base"],
                "replay_status": "pending",
                "sketch_plane": {
                    "semantic_reference": dict(operation_cap),
                    "frame": hole_frame,
                },
                "loops": [
                    {
                        "loop_id": "hole_profile",
                        "loop_type": "outer",
                        "primitives": [
                            {
                                "primitive_id": "circle_1",
                                "type": "circle",
                                "center": list(center_2d),
                                "radius_mm": radius,
                            }
                        ],
                    }
                ],
            },
            {
                "operation_id": "cut_hole",
                "operation_type": "extrude",
                "dependencies": ["extrude_base", "sketch_hole"],
                "replay_status": "pending",
                "profile": {
                    "sketch_id": "sketch_hole",
                    "outer_loop_id": "hole_profile",
                    "inner_loop_ids": [],
                },
                "direction": cut_direction,
                "extent": {"type": "through_all"},
                "boolean_type": "cut",
            },
        ],
    }


def recover_development_sequence(project_root, case_id, input_path):
    try:
        guarded_path = through_hole_inference.validate_gate3_development_input(
            project_root, case_id, input_path
        )
    except through_hole_inference.ThroughHoleInferenceError as exc:
        raise ThroughHoleReconstructionError(exc.code) from exc
    summary, context = brep_inspection.inspect_step_with_context(guarded_path, case_id)
    adjacency = topology_adjacency.build_adjacency(summary, context)
    hole_facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
    coupled = through_hole_inference.generate_coupled_candidates(
        summary, adjacency, hole_facts
    )
    accepted = [
        candidate
        for candidate in coupled.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("status") == "accepted"
    ]
    if len(accepted) != 1:
        raise ThroughHoleReconstructionError("accepted_candidate_count_mismatch")
    selected = accepted[0]
    return {
        "evidence": {
            "brep_summary": summary,
            "adjacency": adjacency,
            "hole_facts": hole_facts,
            "coupled_candidates": coupled,
            "selected_candidate": selected,
        },
        "sequence": sequence_from_summary(summary, selected),
    }


def rebuild_sequence_step(sequence, output_path):
    import cadquery as cq

    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite reconstruction STEP: {output}")
    validation = _load_sequence_validator().validate_sequence(sequence)
    if not validation["valid"]:
        code = validation["errors"][0]["code"]
        raise ThroughHoleReconstructionError(f"sequence_validation_failed:{code}")
    operations = sequence["operations"]
    if (
        len(operations) != 4
        or [operation["operation_type"] for operation in operations]
        != ["sketch", "extrude", "sketch", "extrude"]
        or operations[1]["boolean_type"] != "new"
        or operations[3]["boolean_type"] != "cut"
        or operations[3]["extent"] != {"type": "through_all"}
    ):
        raise ThroughHoleReconstructionError("expected_four_operation_through_hole")

    base_sketch, base_extrude, hole_sketch, cut_extrude = operations
    cap_reference = hole_sketch["sketch_plane"]["semantic_reference"]
    if (
        base_extrude["operation_id"] != "extrude_base"
        or cap_reference.get("type") != "operation_cap"
        or cap_reference.get("operation_id") != "extrude_base"
    ):
        raise ThroughHoleReconstructionError("unsupported_operation_cap_reference")
    if cap_reference.get("role") != "positive_end_cap":
        raise ThroughHoleReconstructionError("unsupported_operation_cap_role")
    base_plane = _cadquery_plane(base_sketch)
    base_loop = _profile_loop(base_sketch, base_extrude)
    base_primitives = base_loop["primitives"]
    if not 3 <= len(base_primitives) <= 8 or not all(
        primitive.get("type") == "line" for primitive in base_primitives
    ):
        raise ThroughHoleReconstructionError("unsupported_base_profile")
    base_workplane = cq.Workplane(base_plane).polyline(
        [tuple(primitive["start"]) for primitive in base_primitives]
    ).close()
    base_sign = 1.0 if _dot(
        base_sketch["sketch_plane"]["frame"]["normal"], base_extrude["direction"]
    ) >= 0.0 else -1.0
    base_result = base_workplane.extrude(
        base_sign * float(base_extrude["extent"]["distance_mm"]), combine=False
    )
    base_solids = base_result.solids().vals()
    if len(base_solids) != 1 or not base_solids[0].isValid():
        raise ThroughHoleReconstructionError("base_rebuild_not_single_valid_solid")

    hole_loop = _profile_loop(hole_sketch, operations[3])
    hole_primitives = hole_loop["primitives"]
    if len(hole_primitives) != 1 or hole_primitives[0].get("type") != "circle":
        raise ThroughHoleReconstructionError("unsupported_hole_profile")
    circle = hole_primitives[0]
    hole_frame = hole_sketch["sketch_plane"]["frame"]
    hole_sign = 1.0 if _dot(hole_frame["normal"], cut_extrude["direction"]) >= 0.0 else -1.0
    cutting_tool = (
        cq.Workplane(_cadquery_plane(hole_sketch))
        .center(*circle["center"])
        .circle(float(circle["radius_mm"]))
        .extrude(
            hole_sign * 2.0 * float(base_extrude["extent"]["distance_mm"]),
            combine=False,
        )
    )
    tool_solids = cutting_tool.solids().vals()
    if len(tool_solids) != 1 or not tool_solids[0].isValid():
        raise ThroughHoleReconstructionError("cutting_tool_not_single_valid_solid")
    rebuilt = base_solids[0].cut(tool_solids[0])
    volume_reduction = base_solids[0].Volume() - rebuilt.Volume()
    reduction_tolerance = max(1e-9, 1e-12 * base_solids[0].Volume())
    if volume_reduction <= reduction_tolerance:
        raise ThroughHoleReconstructionError("boolean_no_intersection")
    solids = rebuilt.Solids()
    if len(solids) != 1 or not solids[0].isValid():
        raise ThroughHoleReconstructionError("rebuild_not_single_valid_solid")
    output.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solids[0], str(output))
    candidate_validation.geometry_validation._load_single_valid_solid(output)
    return output


def validate_reconstruction(reference_path, sequence, output_path, protocol=None):
    protocol = checkpoint3_validation_protocol() if protocol is None else protocol
    if protocol.get("surface", {}).get("mode") != "diagnostic_only":
        raise ThroughHoleReconstructionError("checkpoint3_surface_must_be_diagnostic_only")
    rebuilt = rebuild_sequence_step(sequence, output_path)
    return candidate_validation.validate_replay_step(reference_path, rebuilt, protocol)


def write_sequence(sequence, path):
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite sequence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(brep_inspection.canonical_json_bytes(sequence))
    return output


def checkpoint3_validation_protocol():
    return {
        "protocol_schema": "gate3-checkpoint3-validation-0.1",
        "frozen": False,
        "selection_rule": "development through_hole D-H01..D-H05 checkpoint 3",
        "sampling": {
            "total_budget": 4096,
            "minimum_per_face": 32,
            "seed_policy": "reference_step_sha256_shared_by_comparison_pair",
        },
        "hard_conditions": {
            "single_valid_solid": True,
            "volume_absolute_tolerance_mm3": 1e-6,
            "volume_relative_tolerance": 1e-9,
            "bbox_coordinate_tolerance_mm": 1e-6,
        },
        "surface": {
            "mode": "diagnostic_only",
            "reason": "Gate 3 final surface thresholds are not frozen at checkpoint 3",
        },
    }


def _load_sequence_validator():
    path = Path(__file__).resolve().parents[1] / "shared" / "sequence_validator.py"
    spec = importlib.util.spec_from_file_location("sequence_validator_gate3_checkpoint3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cadquery_plane(sketch):
    import cadquery as cq

    frame = sketch["sketch_plane"]["frame"]
    return cq.Plane(
        origin=tuple(frame["origin"]),
        xDir=tuple(frame["x_axis"]),
        normal=tuple(frame["normal"]),
    )


def _profile_loop(sketch, extrude):
    loop_id = extrude["profile"]["outer_loop_id"]
    matches = [loop for loop in sketch["loops"] if loop.get("loop_id") == loop_id]
    if len(matches) != 1:
        raise ThroughHoleReconstructionError("profile_loop_not_unique")
    return matches[0]


def _canonical_map(items, id_field):
    if not isinstance(items, list):
        raise ValueError
    result = {}
    for item in items:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get(id_field), str)
            or item[id_field] in result
        ):
            raise ValueError
        result[item[id_field]] = item
    return result


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _positive_number(value):
    if not _is_number(value) or value <= 0.0:
        raise ValueError
    return float(value)


def _unit_vector(value):
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(_is_number(component) for component in value)
    ):
        raise ValueError
    length = math.sqrt(sum(float(component) ** 2 for component in value))
    if length <= 0.0:
        raise ValueError
    return [brep_inspection._q(float(component) / length, 12) for component in value]


def _string_set(value):
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError
    return set(value)


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _subtract(left, right):
    return [float(a) - float(b) for a, b in zip(left, right)]


def _face_wire_ids(face):
    uses = face.get("wire_uses")
    if not isinstance(uses, list):
        raise ThroughHoleReconstructionError("malformed_candidate")
    ids = {use.get("wire_id") for use in uses if isinstance(use, dict)}
    if None in ids or len(ids) != len(uses):
        raise ThroughHoleReconstructionError("malformed_candidate")
    return ids


def _is_line_only_wire(wire, edge_by_id):
    uses = wire.get("edge_uses")
    if not isinstance(uses, list) or not 3 <= len(uses) <= 8:
        return False
    edge_ids = [use.get("edge_id") for use in uses if isinstance(use, dict)]
    return (
        wire.get("is_closed") is True
        and len(edge_ids) == len(uses) == len(set(edge_ids))
        and all(
            edge_id in edge_by_id and edge_by_id[edge_id].get("curve_type") == "line"
            for edge_id in edge_ids
        )
    )
