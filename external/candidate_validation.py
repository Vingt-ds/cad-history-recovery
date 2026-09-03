"""CadQuery candidate reconstruction, independent geometry checks, and final ranking."""

from __future__ import annotations

import math
from pathlib import Path

import geometry_validation
import brep_inspection
import extrusion_inference
import profile_reconstruction
import topology_adjacency


class CandidateValidationError(ValueError):
    pass


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _bbox_diagonal(summary):
    box = summary["bbox_mm"]
    return math.sqrt(
        (box["xmax"] - box["xmin"]) ** 2
        + (box["ymax"] - box["ymin"]) ** 2
        + (box["zmax"] - box["zmin"]) ** 2
    )


def rebuild_sequence_step(sequence, output_path):
    import cadquery as cq

    operations = sequence.get("operations", [])
    if len(operations) != 2:
        raise CandidateValidationError("expected_sketch_then_new_extrude")
    sketch, extrude = operations
    if sketch.get("operation_type") != "sketch" or extrude.get("operation_type") != "extrude":
        raise CandidateValidationError("expected_sketch_then_new_extrude")
    if extrude.get("boolean_type") != "new" or extrude.get("extent", {}).get("type") != "distance":
        raise CandidateValidationError("unsupported_candidate_operation")

    frame = sketch["sketch_plane"]["frame"]
    plane = cq.Plane(
        origin=tuple(frame["origin"]),
        xDir=tuple(frame["x_axis"]),
        normal=tuple(frame["normal"]),
    )
    loop = sketch["loops"][0]
    primitives = loop["primitives"]
    workplane = cq.Workplane(plane)
    if all(item.get("type") == "line" for item in primitives):
        points = [tuple(item["start"]) for item in primitives]
        workplane = workplane.polyline(points).close()
    elif len(primitives) == 1 and primitives[0].get("type") == "circle":
        circle = primitives[0]
        workplane = workplane.center(*circle["center"]).circle(circle["radius_mm"])
    else:
        raise CandidateValidationError("unsupported_candidate_profile")

    normal = frame["normal"]
    direction = extrude["direction"]
    sign = 1.0 if _dot(normal, direction) >= 0.0 else -1.0
    distance = float(extrude["extent"]["distance_mm"])
    rebuilt = workplane.extrude(sign * distance, combine=False)
    solids = rebuilt.solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise CandidateValidationError("rebuild_not_single_valid_solid")
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite candidate STEP: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solids[0], str(output))
    geometry_validation._load_single_valid_solid(output)
    return output


def validate_sequence_candidate(reference_path, sequence, output_path, protocol):
    output = rebuild_sequence_step(sequence, output_path)
    sampling = protocol["sampling"]
    comparison = geometry_validation.compare_step_files(
        reference_path,
        output,
        total_budget=int(sampling["total_budget"]),
        minimum_per_face=int(sampling["minimum_per_face"]),
        shared_seed_sha256=geometry_validation._sha256(reference_path),
    )
    reference = comparison["a"]
    rebuilt = comparison["b"]
    hard = protocol["hard_conditions"]

    volume_error = abs(rebuilt["volume_mm3"] - reference["volume_mm3"])
    volume_limit = float(hard["volume_absolute_tolerance_mm3"]) + float(
        hard["volume_relative_tolerance"]
    ) * abs(reference["volume_mm3"])
    volume_pass = volume_error <= volume_limit
    bbox_errors = {
        key: abs(rebuilt["bbox_mm"][key] - reference["bbox_mm"][key])
        for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")
    }
    bbox_max_error = max(bbox_errors.values())
    bbox_pass = bbox_max_error <= float(hard["bbox_coordinate_tolerance_mm"])

    distances = comparison["surface_distance_mm"]
    diagonal = _bbox_diagonal(reference)
    symmetric_ratio = distances["symmetric_p95_mm"] / diagonal
    max_face_ratio = distances["max_face_p95_mm"] / diagonal
    surface = protocol["surface"]
    if surface["mode"] == "threshold":
        surface_pass = (
            symmetric_ratio <= float(surface["symmetric_p95_ratio_threshold"])
            and max_face_ratio <= float(surface["max_face_p95_ratio_threshold"])
        )
    elif surface["mode"] == "diagnostic_only":
        surface_pass = None
    else:
        raise CandidateValidationError("invalid_surface_protocol_mode")

    valid_single_solid = rebuilt["solid_count"] == 1 and rebuilt["is_valid"] is True
    geometry_pass = valid_single_solid and volume_pass and bbox_pass
    if surface_pass is not None:
        geometry_pass = geometry_pass and surface_pass
    return {
        "validation_schema": "gate2-candidate-validation-0.1",
        "reference_sha256": reference["sha256"],
        "rebuild_sha256": rebuilt["sha256"],
        "valid_single_solid": valid_single_solid,
        "volume_error_mm3": volume_error,
        "volume_limit_mm3": volume_limit,
        "volume_pass": volume_pass,
        "bbox_coordinate_errors_mm": bbox_errors,
        "bbox_max_coordinate_error_mm": bbox_max_error,
        "bbox_pass": bbox_pass,
        "surface_mode": surface["mode"],
        "symmetric_p95_mm": distances["symmetric_p95_mm"],
        "max_face_p95_mm": distances["max_face_p95_mm"],
        "symmetric_p95_ratio": symmetric_ratio,
        "max_face_p95_ratio": max_face_ratio,
        "surface_sort_value": max(symmetric_ratio, max_face_ratio),
        "surface_pass": surface_pass,
        "geometry_pass": geometry_pass,
    }


def rank_validated_candidates(candidates):
    def key(candidate):
        validation = candidate["validation"]
        return (
            not bool(validation["geometry_pass"]),
            float(validation["volume_error_mm3"]),
            float(validation["bbox_max_coordinate_error_mm"]),
            float(validation["surface_sort_value"]),
            int(candidate["primitive_count"]),
            float(candidate["distance_mm"]),
            candidate["candidate_id"],
        )

    ordered = sorted(candidates, key=key)
    qualified = [item for item in ordered if item["validation"]["geometry_pass"]]
    return {
        "ranking_schema": "gate2-final-ranking-0.1",
        "ambiguous": len(qualified) >= 2,
        "qualified_candidate_count": len(qualified),
        "selected_candidate_id": qualified[0]["candidate_id"] if qualified else None,
        "candidates": ordered,
    }


def validate_inferred_candidates(reference_path, model_id, output_dir, protocol):
    """Rebuild and validate every fact-accepted candidate from one STEP import."""
    summary, context = brep_inspection.inspect_step_with_context(reference_path, model_id)
    adjacency = topology_adjacency.build_adjacency(summary, context)
    inference = extrusion_inference.generate_candidates(summary, adjacency)
    output_dir = Path(output_dir)
    validated = []
    sequences = {}
    for candidate in inference["candidates"]:
        if candidate["status"] != "accepted":
            continue
        sequence = profile_reconstruction.sequence_from_summary(summary, candidate)
        primitives = sequence["operations"][0]["loops"][0]["primitives"]
        validation = validate_sequence_candidate(
            reference_path,
            sequence,
            output_dir / f"{candidate['candidate_id']}.step",
            protocol,
        )
        validated.append(
            {
                "candidate_id": candidate["candidate_id"],
                "distance_mm": candidate["distance_mm"],
                "primitive_count": len(primitives),
                "validation": validation,
            }
        )
        sequences[candidate["candidate_id"]] = sequence
    return {
        "model_id": str(model_id),
        "source_step_sha256": summary["source_step_sha256"],
        "inference": inference,
        "ranking": rank_validated_candidates(validated),
        "sequences": sequences,
    }
