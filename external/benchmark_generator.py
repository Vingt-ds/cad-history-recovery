"""Generate the fixed Gate 1 benchmark from ``benchmarks/case_matrix.json``."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path


class MatrixError(ValueError):
    """Raised when the benchmark matrix violates its frozen contract."""


def _is_unit(vector, tolerance=1e-9):
    return abs(math.sqrt(sum(float(value) ** 2 for value in vector)) - 1.0) <= tolerance


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def load_and_validate_matrix(matrix_path):
    path = Path(matrix_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("units") != "mm":
        raise MatrixError("units must be mm")

    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != 30:
        raise MatrixError("case matrix must contain exactly 30 cases")

    case_ids = [case.get("case_id") for case in cases]
    output_paths = [case.get("output_step") for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise MatrixError("case_id values must be unique")
    if len(set(output_paths)) != len(output_paths):
        raise MatrixError("output_step values must be unique")
    if Counter(case.get("split") for case in cases) != {"development": 15, "held_out": 15}:
        raise MatrixError("split must contain 15 development and 15 held_out cases")
    if Counter(case.get("source") for case in cases) != {"cadquery": 27, "fusion_manual": 3}:
        raise MatrixError("source must contain 27 cadquery and 3 fusion_manual cases")

    frames = data.get("frames", {})
    if set(frames) != {"XY", "XZ", "YZ", "RX30", "RY45"}:
        raise MatrixError("frame catalog must contain XY, XZ, YZ, RX30, and RY45")
    for frame_id, frame in frames.items():
        normal = frame.get("normal", [])
        x_axis = frame.get("x_axis", [])
        if len(normal) != 3 or len(x_axis) != 3:
            raise MatrixError(f"{frame_id} frame vectors must have three components")
        if not _is_unit(normal) or not _is_unit(x_axis):
            raise MatrixError(f"{frame_id} frame vectors must already be unit vectors")
        if abs(_dot(normal, x_axis)) > 1e-9:
            raise MatrixError(f"{frame_id} normal and x_axis must be orthogonal")

    return data


def _profile_workplane(case, frames):
    import cadquery as cq

    geometry = case["geometry"]
    frame = frames[geometry["frame_id"]]
    plane = cq.Plane(
        origin=cq.Vector(*geometry["origin"]),
        xDir=cq.Vector(*frame["x_axis"]),
        normal=cq.Vector(*frame["normal"]),
    )
    workplane = cq.Workplane(plane)
    profile = geometry["profile"]
    if profile["type"] == "rectangle":
        return workplane.rect(profile["width"], profile["height"], centered=False)
    if profile["type"] == "polygon":
        return workplane.polyline(profile["points"]).close()
    if profile["type"] == "circle":
        return workplane.center(*profile["center"]).circle(profile["radius_mm"])
    raise MatrixError(f"unsupported generated profile type: {profile.get('type')}")


def generate_case(case, frames, output_path):
    import cadquery as cq

    geometry = case["geometry"]
    if case.get("source") != "cadquery":
        raise MatrixError(f"{case.get('case_id')} is a manual Fusion case")
    if geometry.get("kind") != "profile_extrusion":
        raise MatrixError(f"generation for {geometry.get('kind')} is not implemented yet")

    solid = _profile_workplane(case, frames).extrude(
        geometry["direction_sign"] * geometry["distance_mm"]
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solid, str(output))

    imported = cq.importers.importStep(str(output))
    solids = imported.solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise MatrixError(f"{case.get('case_id')} did not produce one valid solid")
    return {
        "case_id": case["case_id"],
        "status": "generated",
        "output_step": str(output),
        "solid_count": 1,
        "face_count": len(solids[0].Faces()),
        "edge_count": len(solids[0].Edges()),
    }
