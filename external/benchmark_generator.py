"""Generate the fixed Gate 1 benchmark from ``benchmarks/case_matrix.json``."""

from __future__ import annotations

import json
import hashlib
import math
import shutil
from collections import Counter
from pathlib import Path


class MatrixError(ValueError):
    """Raised when the benchmark matrix violates its frozen contract."""


def _is_unit(vector, tolerance=1e-9):
    return abs(math.sqrt(sum(float(value) ** 2 for value in vector)) - 1.0) <= tolerance


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _add(*vectors):
    return tuple(sum(float(vector[index]) for vector in vectors) for index in range(3))


def _scale(vector, factor):
    return tuple(float(value) * float(factor) for value in vector)


def _cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _profile_area(profile):
    profile_type = profile["type"]
    if profile_type == "rectangle":
        return profile["width"] * profile["height"]
    if profile_type == "circle":
        return math.pi * profile["radius_mm"] ** 2
    if profile_type == "polygon":
        points = profile["points"]
        twice_area = sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        return abs(twice_area) / 2.0
    raise MatrixError(f"unsupported profile area type: {profile_type}")


def _expected_volume(case):
    geometry = case["geometry"]
    kind = geometry["kind"]
    if kind in {"profile_extrusion", "profile_extrusion_with_hole"}:
        volume = _profile_area(geometry["profile"]) * geometry["distance_mm"]
        if kind == "profile_extrusion_with_hole":
            volume -= (
                math.pi
                * geometry["hole"]["radius_mm"] ** 2
                * geometry["distance_mm"]
            )
        return volume
    if kind == "box":
        return math.prod(geometry["size"])
    return None


def _add_volume_audit(record, case):
    expected = _expected_volume(case)
    if expected is not None:
        record["expected_volume_mm3"] = expected
        record["volume_relative_error"] = abs(record["volume_mm3"] - expected) / expected
    return record


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
    kind = geometry.get("kind")
    if kind in {"profile_extrusion", "profile_extrusion_with_hole"}:
        solid = _profile_workplane(case, frames).extrude(
            geometry["direction_sign"] * geometry["distance_mm"]
        )
        if kind == "profile_extrusion_with_hole":
            frame = frames[geometry["frame_id"]]
            normal = tuple(frame["normal"])
            x_axis = tuple(frame["x_axis"])
            y_axis = _cross(normal, x_axis)
            direction = _scale(normal, geometry["direction_sign"])
            hole = geometry["hole"]
            center = _add(
                geometry["origin"],
                _scale(x_axis, hole["center"][0]),
                _scale(y_axis, hole["center"][1]),
            )
            tool_start = _add(center, _scale(direction, -1.0))
            tool = cq.Solid.makeCylinder(
                hole["radius_mm"],
                geometry["distance_mm"] + 2.0,
                cq.Vector(*tool_start),
                cq.Vector(*direction),
            )
            solid = solid.val().cut(tool)
    elif kind == "box":
        solid = cq.Workplane("XY", origin=tuple(geometry["origin"])).box(
            *geometry["size"], centered=(False, False, False)
        )
    elif kind == "filleted_box":
        solid = (
            cq.Workplane("XY", origin=tuple(geometry["origin"]))
            .box(*geometry["size"], centered=(False, False, False))
            .edges()
            .fillet(geometry["fillet_radius_mm"])
        )
    else:
        raise MatrixError(f"generation for {kind} is not implemented")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solid, str(output))

    imported = cq.importers.importStep(str(output))
    solids = imported.solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise MatrixError(f"{case.get('case_id')} did not produce one valid solid")
    record = {
        "case_id": case["case_id"],
        "status": "generated",
        "output_step": str(output),
        "solid_count": 1,
        "face_count": len(solids[0].Faces()),
        "edge_count": len(solids[0].Edges()),
        "volume_mm3": solids[0].Volume(),
    }
    return _add_volume_audit(record, case)


def generate_all(matrix_path, project_root, overwrite=False):
    root = Path(project_root)
    lock_path = root / "benchmarks" / "freeze.lock.json"
    if lock_path.exists():
        raise MatrixError(f"benchmark lock exists: {lock_path}")

    import cadquery as cq

    data = load_and_validate_matrix(matrix_path)
    records = []
    thumbnail_root = root / "benchmarks" / "thumbnails"
    thumbnail_root.mkdir(parents=True, exist_ok=True)

    for case in data["cases"]:
        output = root / case["output_step"]
        if case["source"] == "cadquery":
            if output.exists() and not overwrite:
                record = _inspect_step(output, case["case_id"], "existing_valid")
            else:
                record = generate_case(case, data["frames"], output)
        elif case["geometry"]["kind"] == "manual_existing":
            source = root / case["source_step"]
            if not source.is_file():
                raise MatrixError(f"manual source is missing: {case['source_step']}")
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and not overwrite:
                record = _inspect_step(output, case["case_id"], "existing_manual")
            else:
                shutil.copy2(source, output)
                record = _inspect_step(output, case["case_id"], "copied_manual")
        elif output.is_file():
            record = _inspect_step(output, case["case_id"], "existing_manual")
        else:
            records.append(
                {
                    "case_id": case["case_id"],
                    "status": "pending_manual",
                    "output_step": case["output_step"],
                    "expected_scope": case["expected_scope"],
                    "expected_behavior": case["expected_behavior"],
                }
            )
            continue

        record["output_step"] = case["output_step"]
        record["expected_scope"] = case["expected_scope"]
        record["expected_behavior"] = case["expected_behavior"]
        _add_volume_audit(record, case)
        record["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        thumbnail = thumbnail_root / f"{case['case_id']}.svg"
        shape = cq.importers.importStep(str(output)).solids().val()
        thumbnail.write_text(
            cq.exporters.getSVG(
                shape,
                opts={"width": 240, "height": 180, "showAxes": False, "projectionDir": (1, -1, 1)},
            ),
            encoding="utf-8",
        )
        record["thumbnail"] = str(thumbnail.relative_to(root)).replace("\\", "/")
        records.append(record)

    report_path = root / "benchmarks" / "generation_report.json"
    report_path.write_text(
        json.dumps(
            {
                "matrix_version": data["matrix_version"],
                "units": data["units"],
                "case_count": len(records),
                "records": records,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_contact_sheet(root, records)
    return records


def _inspect_step(path, case_id, status):
    import cadquery as cq

    imported = cq.importers.importStep(str(path))
    solids = imported.solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise MatrixError(f"{case_id} is not one valid solid")
    return {
        "case_id": case_id,
        "status": status,
        "output_step": str(path),
        "solid_count": 1,
        "face_count": len(solids[0].Faces()),
        "edge_count": len(solids[0].Edges()),
        "volume_mm3": solids[0].Volume(),
    }


def _write_contact_sheet(root, records):
    cards = []
    for record in records:
        case_id = record["case_id"]
        if record["status"] == "pending_manual":
            visual = "<div class=\"pending\">PENDING MANUAL FUSION MODEL</div>"
        else:
            visual = f'<object data="thumbnails/{case_id}.svg" type="image/svg+xml"></object>'
        cards.append(
            f"<figure>{visual}<figcaption>{case_id} | {record['status']}</figcaption></figure>"
        )
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Gate 1 benchmark contact sheet</title>
<style>body{font-family:sans-serif}main{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}figure{margin:0;border:1px solid #999;padding:4px}object,.pending{width:240px;height:180px}.pending{display:grid;place-items:center;background:#eee}figcaption{font-size:12px}</style>
</head><body><h1>Gate 1 benchmark contact sheet</h1><main>""" + "".join(cards) + "</main></body></html>\n"
    (root / "benchmarks" / "contact_sheet.html").write_text(html, encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    records = generate_all(root / "benchmarks" / "case_matrix.json", root)
    counts = Counter(record["status"] for record in records)
    summary = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(f"GATE1_BENCHMARK {summary}")


if __name__ == "__main__":
    main()
