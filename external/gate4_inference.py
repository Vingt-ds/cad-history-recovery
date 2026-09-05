"""Content-driven Gate 4 semantic inference entry point."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import brep_inspection
import candidate_validation
import gate3_pipeline
import through_hole_inference
import through_hole_reconstruction
import topology_adjacency


class Gate4InferenceError(ValueError):
    pass


def classify_route(summary, hole_facts):
    """Choose a semantic route from B-rep facts, never from case metadata."""

    if summary.get("brep_summary_schema") != "brep-summary-0.1":
        raise Gate4InferenceError("brep_summary_schema_mismatch")
    if (
        hole_facts.get("through_hole_facts_schema") != "through-hole-facts-0.1"
        or hole_facts.get("source_step_sha256") != summary.get("source_step_sha256")
        or hole_facts.get("model_id") != summary.get("model_id")
    ):
        raise Gate4InferenceError("through_hole_facts_mismatch")

    groups = hole_facts.get("hole_fact_groups", [])
    supported = [group for group in groups if group.get("status") == "accepted"]
    role_inner_opening = any(
        role.get("inner_circle_wire_ids")
        for role in hole_facts.get("planar_wire_roles", [])
        if isinstance(role, dict)
    )
    faces = summary["solids"][0]["faces"]
    edges = summary["solids"][0]["edges"]
    cylinder_count = sum(face.get("surface_type") == "cylinder" for face in faces)
    full_circle_count = sum(
        edge.get("curve_type") == "circle"
        and edge.get("circle_form") == "full_circle"
        for edge in edges
    )
    multiple_openings = cylinder_count >= 2 and full_circle_count >= 4
    inner_opening = bool(role_inner_opening or multiple_openings)
    cylindrical_boundary = bool(
        any(
        isinstance(group, dict)
        and group.get("cylinder_face_id")
        and group.get("circle_edge_ids")
        for group in groups
        )
        or multiple_openings
    )

    if len(supported) == 1 and len(groups) == 1:
        route = "gate3"
        reason = "one_supported_inner_opening_and_cylindrical_void"
    elif inner_opening and cylindrical_boundary:
        route = "unsupported"
        reason = "hole_like_geometry_outside_frozen_gate3_scope"
    else:
        route = "gate2"
        reason = "no_inner_circular_opening_and_cylindrical_void_pair"

    return {
        "routing_schema": "gate4-content-route-0.1",
        "route": route,
        "reason": reason,
        "inner_circular_opening_evidence": bool(inner_opening),
        "cylindrical_boundary_evidence": bool(cylindrical_boundary),
        "supported_hole_group_count": len(supported),
        "hole_fact_group_count": len(groups),
        "cylinder_face_count": cylinder_count,
        "full_circle_edge_count": full_circle_count,
    }


def inspect_and_infer_step(
    step_path,
    source_sha256,
    work_dir,
    gate2_protocol,
    gate3_protocol,
):
    path = Path(step_path)
    if not isinstance(source_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", source_sha256
    ) is None:
        raise Gate4InferenceError("invalid_source_sha256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != source_sha256:
        raise Gate4InferenceError("source_sha256_mismatch")

    internal_model_id = "shape-" + source_sha256[:16]
    summary, context = brep_inspection.inspect_step_with_context(
        path, internal_model_id
    )
    adjacency = topology_adjacency.build_adjacency(summary, context)
    hole_facts = through_hole_inference.analyze_through_hole_facts(
        summary, adjacency
    )
    route = classify_route(summary, hole_facts)
    result = {
        "semantic_inference_schema": "gate4-semantic-inference-0.1",
        "source_step_sha256": source_sha256,
        "brep_summary": summary,
        "route": route,
        "semantic_outcome": "unsupported"
        if route["route"] == "unsupported"
        else None,
        "ambiguous": False,
        "candidate_generation_entered": False,
        "candidate_set": [],
        "selected_candidate_id": None,
        "selected_sequence": None,
    }
    if route["route"] == "unsupported":
        result["failure_code"] = "NO_SUPPORTED_HYPOTHESIS"
        result["unsupported_rule"] = route["reason"]
        return result
    if route["route"] == "gate2":
        result["candidate_generation_entered"] = True
        validated = candidate_validation.validate_inferred_facts(
            path,
            summary,
            context,
            Path(work_dir) / "candidate_rebuilds",
            gate2_protocol,
        )
        ranking = validated["ranking"]
        selected_id = ranking["selected_candidate_id"]
        result["candidate_set"] = validated["inference"]["candidates"]
        result["ambiguous"] = bool(ranking["ambiguous"])
        if selected_id is None:
            result["semantic_outcome"] = "unsupported"
            result["failure_code"] = "NO_SUPPORTED_HYPOTHESIS"
            result["unsupported_rule"] = "no_gate2_candidate_passed_frozen_protocol"
            return result
        selected_validation = next(
            item["validation"]
            for item in ranking["candidates"]
            if item["candidate_id"] == selected_id
        )
        result.update(
            {
                "semantic_outcome": "candidate_selected",
                "selected_candidate_id": selected_id,
                "selected_sequence": validated["sequences"][selected_id],
                "validation": {
                    key: value
                    for key, value in selected_validation.items()
                    if key not in {"reference_sha256", "rebuild_sha256"}
                },
            }
        )
        return result

    result["candidate_generation_entered"] = True
    coupled = through_hole_inference.generate_coupled_candidates(
        summary, adjacency, hole_facts
    )
    accepted = [
        candidate
        for candidate in coupled.get("candidates", [])
        if candidate.get("status") == "accepted"
    ]
    if len(accepted) != 1:
        raise Gate4InferenceError("accepted_candidate_count_mismatch")
    selected = accepted[0]
    sequence = through_hole_reconstruction.sequence_from_summary(summary, selected)
    output = Path(work_dir) / "candidate.step"
    through_hole_reconstruction.rebuild_sequence_step(sequence, output)
    validation = gate3_pipeline.validate_gate3_replay(
        path, output, internal_model_id, gate3_protocol
    )
    if not validation.get("geometry_pass"):
        result["semantic_outcome"] = "no_valid_candidate"
        return result

    result.update(
        {
            "semantic_outcome": "candidate_selected",
            "candidate_set": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "status": candidate["status"],
                    "checks": candidate["checks"],
                    "rejection_reasons": candidate["rejection_reasons"],
                }
                for candidate in coupled["candidates"]
            ],
            "selected_candidate_id": selected["candidate_id"],
            "selected_sequence": sequence,
            "validation": {
                "valid_single_solid": validation["valid_single_solid"],
                "volume_error_mm3": validation["volume_error_mm3"],
                "bbox_coordinate_errors_mm": validation[
                    "bbox_coordinate_errors_mm"
                ],
                "surface_sort_value": validation["surface_sort_value"],
                "base_geometry_pass": validation["base_geometry_pass"],
                "feature_match": validation["feature_match"],
                "feature_checks": validation["feature_checks"],
                "feature_match_pass": validation["feature_match_pass"],
                "geometry_pass": validation["geometry_pass"],
            },
        }
    )
    return result
