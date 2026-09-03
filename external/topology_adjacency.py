"""Minimal deterministic face adjacency derived from canonical shared edges."""

from __future__ import annotations

import math
from pathlib import Path

import cadquery as cq
from OCP.BRepTools import BRepTools_WireExplorer

import brep_inspection


ANGLE_TOLERANCE_RAD = 1e-8


class AdjacencyMeasurementError(RuntimeError):
    """Raised when a kernel normal or tangent cannot be evaluated reliably."""


def _same_record(shape, records):
    for record in records:
        if shape.IsSame(record["_wrapped"]):
            return record
    raise brep_inspection.BRepInspectionError("topology_reference_unresolved")


def _tuple(vector):
    return tuple(float(value) for value in vector.toTuple())


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _negate(vector):
    return tuple(-value for value in vector)


def _edge_uses_by_face(context):
    uses = {}
    for face_record in context["faces"]:
        face = cq.Face(face_record["_wrapped"])
        face_id = face_record["face_id"]
        for wire in face.Wires():
            explorer = BRepTools_WireExplorer(wire.wrapped, face.wrapped)
            while explorer.More():
                edge_use = explorer.Current()
                edge_record = _same_record(edge_use, context["edges"])
                uses.setdefault(edge_record["edge_id"], []).append(
                    {
                        "face_id": face_id,
                        "orientation": brep_inspection._orientation(edge_use),
                    }
                )
                explorer.Next()
    return uses


def _measure_relation(edge_record, face_1, face_2, face_1_use):
    try:
        edge = cq.Edge(edge_record["_wrapped"])
        point = edge.positionAt(0.5)
        normal_1 = _tuple(cq.Face(face_1["_wrapped"]).normalAt(point))
        normal_2 = _tuple(cq.Face(face_2["_wrapped"]).normalAt(point))
        tangent = _tuple(edge.tangentAt(0.5))
    except Exception as exc:
        raise AdjacencyMeasurementError("kernel_local_evaluation_failed") from exc
    if face_1_use["orientation"] == "reversed":
        tangent = _negate(tangent)
    elif face_1_use["orientation"] != "forward":
        raise AdjacencyMeasurementError("unsupported_edge_use_orientation")

    signed = math.atan2(_dot(tangent, _cross(normal_1, normal_2)), _dot(normal_1, normal_2))
    if signed > ANGLE_TOLERANCE_RAD:
        classification = "convex"
    elif signed < -ANGLE_TOLERANCE_RAD:
        classification = "concave"
    else:
        classification = "smooth"
    return {
        "signed_angle_rad": brep_inspection._q(signed, 12),
        "dihedral_angle_rad": brep_inspection._q(signed, 12),
        "interior_dihedral_angle_rad": brep_inspection._q(math.pi - signed, 12),
        "classification": classification,
        "normal_evaluation": "shared_edge_midpoint",
        "sample_point_mm": [brep_inspection._q(value) for value in point.toTuple()],
    }


def inspect_adjacency(path, model_id):
    """Return face adjacency for one STEP without a second geometry import."""
    summary, context = brep_inspection.inspect_step_with_context(Path(path), model_id)
    uses_by_edge = _edge_uses_by_face(context)
    face_by_id = {record["face_id"]: record for record in context["faces"]}
    relations = []

    for edge_id in sorted(uses_by_edge):
        uses = uses_by_edge[edge_id]
        distinct_face_ids = sorted({item["face_id"] for item in uses})
        if len(distinct_face_ids) < 2:
            continue
        edge_record = next(record for record in context["edges"] if record["edge_id"] == edge_id)
        for left_index, face_1_id in enumerate(distinct_face_ids[:-1]):
            for face_2_id in distinct_face_ids[left_index + 1 :]:
                face_1 = face_by_id[face_1_id]
                face_2 = face_by_id[face_2_id]
                face_1_use = next(item for item in uses if item["face_id"] == face_1_id)
                relation = {
                    "relation_id": f"relation-{len(relations):03d}",
                    "face_1_id": face_1_id,
                    "face_2_id": face_2_id,
                    "shared_edge_id": edge_id,
                    "edge_type": edge_record["curve_type"],
                }
                try:
                    relation.update(_measure_relation(edge_record, face_1, face_2, face_1_use))
                except AdjacencyMeasurementError:
                    relation.update(
                        {
                            "signed_angle_rad": None,
                            "dihedral_angle_rad": None,
                            "interior_dihedral_angle_rad": None,
                            "classification": "unknown",
                            "normal_evaluation": "failed",
                            "measurement_error": "normal_or_tangent_evaluation_failed",
                        }
                    )
                relations.append(relation)

    faces = {face_id: [] for face_id in sorted(face_by_id)}
    for relation in relations:
        faces[relation["face_1_id"]].append(
            {
                "neighbor_face_id": relation["face_2_id"],
                "relation_id": relation["relation_id"],
            }
        )
        faces[relation["face_2_id"]].append(
            {
                "neighbor_face_id": relation["face_1_id"],
                "relation_id": relation["relation_id"],
            }
        )

    return {
        "adjacency_schema": "face-adjacency-0.1",
        "model_id": str(model_id),
        "source_step_sha256": summary["source_step_sha256"],
        "angle_convention": {
            "face_1": "lower_canonical_face_id",
            "tangent": "shared_edge_tangent_adjusted_by_face_1_edge_use_orientation",
            "positive": "convex",
            "negative": "concave",
        },
        "faces": faces,
        "relations": relations,
    }
