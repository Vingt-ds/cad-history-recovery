"""Deterministic Gate 2 B-rep fact extraction from one imported STEP shape."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class BRepInspectionError(ValueError):
    """Raised when a STEP file cannot produce a canonical fact summary."""


ORIENTATIONS = {0: "forward", 1: "reversed", 2: "internal", 3: "external"}


def _q(value, digits=9):
    value = float(value)
    if not math.isfinite(value):
        raise BRepInspectionError("non_finite_geometry")
    result = round(value, digits)
    return 0.0 if result == 0.0 else result


def _point(point, digits=9):
    values = point.Coord() if hasattr(point, "Coord") else point.toTuple()
    return [_q(value, digits) for value in values]


def _orientation(shape):
    return ORIENTATIONS.get(int(shape.Orientation()), "unknown")


def _bbox(shape):
    box = shape.BoundingBox()
    return {
        "xmin": _q(box.xmin),
        "xmax": _q(box.xmax),
        "ymin": _q(box.ymin),
        "ymax": _q(box.ymax),
        "zmin": _q(box.zmin),
        "zmax": _q(box.zmax),
    }


def _signature(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def assign_canonical_ids(entity_type, records):
    """Sort records by signatures and reject unresolved distinct-identity collisions."""
    ordered = sorted(records, key=lambda item: _signature(item["_signature"]))
    previous = None
    for record in ordered:
        key = _signature(record["_signature"])
        if previous is not None and key == previous[0] and record["_identity"] != previous[1]:
            raise BRepInspectionError(f"topology_id_collision:{entity_type}:{key}")
        previous = (key, record["_identity"])
    id_key = f"{entity_type}_id"
    for index, record in enumerate(ordered):
        record[id_key] = f"{entity_type}-{index:03d}"
    return ordered


def _find_same(wrapped, records):
    for record in records:
        if wrapped.IsSame(record["_wrapped"]):
            return record
    raise BRepInspectionError("topology_reference_unresolved")


def _surface_facts(face):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    surface_type = adaptor.GetType()
    if surface_type == GeomAbs_SurfaceType.GeomAbs_Plane:
        plane = adaptor.Plane()
        parameters = {
            "origin_mm": _point(plane.Location()),
            "normal": _point(plane.Axis().Direction(), 12),
            "x_direction": _point(plane.XAxis().Direction(), 12),
        }
        name = "plane"
    elif surface_type == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        parameters = {
            "axis_origin_mm": _point(cylinder.Location()),
            "axis_direction": _point(cylinder.Axis().Direction(), 12),
            "x_direction": _point(cylinder.XAxis().Direction(), 12),
            "radius_mm": _q(cylinder.Radius()),
        }
        name = "cylinder"
    elif surface_type == GeomAbs_SurfaceType.GeomAbs_Cone:
        cone = adaptor.Cone()
        parameters = {
            "axis_origin_mm": _point(cone.Location()),
            "axis_direction": _point(cone.Axis().Direction(), 12),
            "x_direction": _point(cone.XAxis().Direction(), 12),
            "reference_radius_mm": _q(cone.RefRadius()),
            "semi_angle_rad": _q(cone.SemiAngle(), 12),
        }
        name = "cone"
    elif surface_type == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        parameters = {
            "center_mm": _point(sphere.Location()),
            "axis_direction": _point(sphere.Position().Direction(), 12),
            "x_direction": _point(sphere.XAxis().Direction(), 12),
            "radius_mm": _q(sphere.Radius()),
        }
        name = "sphere"
    else:
        parameters = {"ocp_surface_type": str(surface_type).split(".")[-1]}
        name = "other"
    bounds = face.uvBounds()
    return name, parameters, {
        "u_min": _q(bounds[0], 12),
        "u_max": _q(bounds[1], 12),
        "v_min": _q(bounds[2], 12),
        "v_max": _q(bounds[3], 12),
    }


def _curve_facts(edge):
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    if BRep_Tool.Degenerated_s(edge.wrapped):
        return (
            "other",
            {"ocp_curve_type": "degenerate"},
            [0.0, 0.0],
            {"is_degenerate": True},
        )
    adaptor = BRepAdaptor_Curve(edge.wrapped)
    curve_type = adaptor.GetType()
    first = _q(adaptor.FirstParameter(), 12)
    last = _q(adaptor.LastParameter(), 12)
    extra = {}
    if curve_type == GeomAbs_CurveType.GeomAbs_Line:
        line = adaptor.Line()
        name = "line"
        parameters = {
            "origin_mm": _point(line.Location()),
            "direction": _point(line.Direction(), 12),
        }
    elif curve_type == GeomAbs_CurveType.GeomAbs_Circle:
        circle = adaptor.Circle()
        name = "circle"
        parameters = {
            "center_mm": _point(circle.Location()),
            "axis_direction": _point(circle.Axis().Direction(), 12),
            "x_direction": _point(circle.XAxis().Direction(), 12),
            "radius_mm": _q(circle.Radius()),
        }
        full = bool(edge.Closed()) or abs((last - first) - 2.0 * math.pi) <= 1e-9
        extra["circle_form"] = "full_circle" if full else "circular_arc"
    elif curve_type == GeomAbs_CurveType.GeomAbs_BSplineCurve:
        spline = adaptor.BSpline()
        name = "bspline"
        parameters = {
            "degree": int(spline.Degree()),
            "pole_count": int(spline.NbPoles()),
            "knot_count": int(spline.NbKnots()),
            "is_periodic": bool(spline.IsPeriodic()),
        }
    else:
        name = "other"
        parameters = {"ocp_curve_type": str(curve_type).split(".")[-1]}
    return name, parameters, [first, last], extra


def _canonical_cycle(uses):
    if not uses:
        return []
    rotations = [uses[index:] + uses[:index] for index in range(len(uses))]
    return min(rotations, key=lambda value: _signature(value))


def _unique_wrappers(shapes):
    unique = []
    for shape in shapes:
        if not any(shape.wrapped.IsSame(item.wrapped) for item in unique):
            unique.append(shape)
    return unique


def _all_unique_edges(solid):
    import cadquery as cq
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    wrapped = []
    explorer = TopExp_Explorer(solid.wrapped, TopAbs_EDGE)
    while explorer.More():
        current = explorer.Current()
        if not any(current.IsSame(item) for item in wrapped):
            wrapped.append(current)
        explorer.Next()
    return [cq.Shape.cast(item) for item in wrapped]


def inspect_step(path, model_id):
    summary, _ = inspect_step_with_context(path, model_id)
    return summary


def inspect_step_with_context(path, model_id):
    """Inspect once and return canonical facts plus private topology wrappers."""
    import cadquery as cq
    from OCP.BRepTools import BRepTools_WireExplorer

    path = Path(path)
    if not path.is_file():
        raise BRepInspectionError("step_not_found")
    try:
        imported = cq.importers.importStep(str(path))
        solids = imported.solids().vals()
    except Exception as exc:
        raise BRepInspectionError(f"step_import_failed:{exc}") from exc
    if not solids:
        raise BRepInspectionError("zero_solid")
    if len(solids) != 1:
        raise BRepInspectionError(f"multiple_solids:{len(solids)}")
    solid = solids[0]
    if not solid.isValid():
        raise BRepInspectionError("invalid_solid")

    vertex_records = []
    for index, vertex in enumerate(_unique_wrappers(solid.Vertices())):
        point = _point(vertex.Center())
        vertex_records.append(
            {"_identity": index, "_signature": point, "_wrapped": vertex.wrapped, "point_mm": point}
        )
    vertex_records = assign_canonical_ids("vertex", vertex_records)

    edge_records = []
    for index, edge in enumerate(_all_unique_edges(solid)):
        curve_type, parameters, parameter_range, extra = _curve_facts(edge)
        vertex_ids = sorted(_find_same(v.wrapped, vertex_records)["vertex_id"] for v in edge.Vertices())
        public = {
            "curve_type": curve_type,
            "length_mm": _q(edge.Length()),
            "centroid_mm": _point(edge.Center()),
            "bbox_mm": _bbox(edge),
            "parameter_range": parameter_range,
            "is_closed": bool(edge.Closed()),
            "curve_parameters": parameters,
            "vertex_ids": vertex_ids,
            **extra,
        }
        edge_records.append(
            {
                "_identity": index,
                "_signature": public,
                "_wrapped": edge.wrapped,
                **public,
            }
        )
    edge_records = assign_canonical_ids("edge", edge_records)

    face_wrappers = _unique_wrappers(solid.Faces())
    wire_records = []
    for index, wire in enumerate(_unique_wrappers(solid.Wires())):
        containing_face = next(
            (face for face in face_wrappers if any(wire.wrapped.IsSame(w.wrapped) for w in face.Wires())),
            None,
        )
        if containing_face is None:
            raise BRepInspectionError("wire_parent_face_unresolved")
        explorer = BRepTools_WireExplorer(wire.wrapped, containing_face.wrapped)
        uses = []
        while explorer.More():
            current = explorer.Current()
            edge_record = _find_same(current, edge_records)
            uses.append({"edge_id": edge_record["edge_id"], "orientation": _orientation(current)})
            explorer.Next()
        uses = _canonical_cycle(uses)
        public = {"is_closed": bool(wire.Closed()), "edge_uses": uses}
        wire_records.append(
            {"_identity": index, "_signature": public, "_wrapped": wire.wrapped, **public}
        )
    wire_records = assign_canonical_ids("wire", wire_records)

    face_records = []
    for index, face in enumerate(face_wrappers):
        surface_type, parameters, parameter_bounds = _surface_facts(face)
        wire_uses = sorted(
            (
                {
                    "wire_id": _find_same(wire.wrapped, wire_records)["wire_id"],
                    "orientation": _orientation(wire.wrapped),
                }
                for wire in face.Wires()
            ),
            key=lambda item: (item["wire_id"], item["orientation"]),
        )
        public = {
            "orientation": _orientation(face.wrapped),
            "surface_type": surface_type,
            "area_mm2": _q(face.Area()),
            "centroid_mm": _point(face.Center()),
            "bbox_mm": _bbox(face),
            "parameter_bounds": parameter_bounds,
            "surface_parameters": parameters,
            "wire_uses": wire_uses,
        }
        face_records.append(
            {"_identity": index, "_signature": public, "_wrapped": face.wrapped, **public}
        )
    face_records = assign_canonical_ids("face", face_records)

    public_vertices = [_public(record) for record in vertex_records]
    public_edges = [_public(record) for record in edge_records]
    public_wires = [_public(record) for record in wire_records]
    public_faces = [_public(record) for record in face_records]
    solid_record = {
        "solid_id": "solid-000",
        "is_valid": True,
        "volume_mm3": _q(solid.Volume()),
        "surface_area_mm2": _q(solid.Area()),
        "centroid_mm": _point(solid.Center()),
        "bbox_mm": _bbox(solid),
        "face_ids": [face["face_id"] for face in public_faces],
        "faces": public_faces,
        "wires": public_wires,
        "edges": public_edges,
        "vertices": public_vertices,
    }
    summary = {
        "brep_summary_schema": "brep-summary-0.1",
        "model_id": str(model_id),
        "source_step_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "units": "mm",
        "canonicalization": {
            "linear_decimals": 9,
            "direction_decimals": 12,
            "parameter_decimals": 12,
            "negative_zero_normalized": True,
            "wire_cycle_start": "lexicographically_minimal_rotation_without_reversal",
        },
        "solid_count": 1,
        "topology_counts": {
            "faces": len(public_faces),
            "wires": len(public_wires),
            "edges": len(public_edges),
            "vertices": len(public_vertices),
        },
        "solids": [solid_record],
    }
    context = {
        "solid": solid,
        "vertices": vertex_records,
        "edges": edge_records,
        "wires": wire_records,
        "faces": face_records,
    }
    return summary, context


def _public(record):
    return {key: value for key, value in record.items() if not key.startswith("_")}


def canonical_json_bytes(summary):
    return (
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def write_summary(summary, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(summary))
    return output
