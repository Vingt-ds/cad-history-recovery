"""Deterministic STEP geometry summaries and bidirectional surface distances."""

from __future__ import annotations

import hashlib
from pathlib import Path


class GeometryValidationError(ValueError):
    """Raised when a STEP file cannot satisfy the Gate 1 validation contract."""


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_single_valid_solid(path):
    import cadquery as cq

    solids = cq.importers.importStep(str(path)).solids().vals()
    if len(solids) != 1:
        raise GeometryValidationError(f"expected one solid, found {len(solids)}: {path}")
    if not solids[0].isValid():
        raise GeometryValidationError(f"invalid solid: {path}")
    return solids[0]


def inspect_step(path):
    path = Path(path)
    solid = _load_single_valid_solid(path)
    box = solid.BoundingBox()
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "solid_count": 1,
        "is_valid": True,
        "volume_mm3": float(solid.Volume()),
        "surface_area_mm2": float(solid.Area()),
        "bbox_mm": {
            "xmin": float(box.xmin),
            "xmax": float(box.xmax),
            "ymin": float(box.ymin),
            "ymax": float(box.ymax),
            "zmin": float(box.zmin),
            "zmax": float(box.zmax),
        },
    }


def allocate_face_samples(areas, total_budget=4096, minimum_per_face=32):
    if not areas:
        raise GeometryValidationError("solid has no faces")
    if any(float(area) <= 0.0 for area in areas):
        raise GeometryValidationError("face areas must be positive")
    total = max(int(total_budget), len(areas) * int(minimum_per_face))
    counts = [int(minimum_per_face)] * len(areas)
    remaining = total - sum(counts)
    area_total = sum(float(area) for area in areas)
    shares = [remaining * float(area) / area_total for area in areas]
    floors = [int(share) for share in shares]
    counts = [count + floor for count, floor in zip(counts, floors)]
    leftovers = total - sum(counts)
    order = sorted(
        range(len(areas)),
        key=lambda index: (-(shares[index] - floors[index]), index),
    )
    for index in order[:leftovers]:
        counts[index] += 1
    return counts


def _sample_face(face, count, rng, chord_tolerance_mm):
    import numpy as np

    vertices, triangle_indices = face.tessellate(float(chord_tolerance_mm))
    if not triangle_indices:
        raise GeometryValidationError("face tessellation produced no triangles")
    vertex_array = np.asarray([vertex.toTuple() for vertex in vertices], dtype=float)
    triangles = vertex_array[np.asarray(triangle_indices, dtype=int)]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    areas = np.linalg.norm(cross, axis=1) * 0.5
    keep = areas > 0.0
    triangles = triangles[keep]
    areas = areas[keep]
    if not len(triangles):
        raise GeometryValidationError("face tessellation contains only degenerate triangles")
    chosen = rng.choice(len(triangles), size=int(count), p=areas / areas.sum())
    selected = triangles[chosen]
    root = np.sqrt(rng.random(int(count)))
    second = rng.random(int(count))
    return (
        (1.0 - root)[:, None] * selected[:, 0]
        + (root * (1.0 - second))[:, None] * selected[:, 1]
        + (root * second)[:, None] * selected[:, 2]
    )


def sample_step_surface(
    path,
    total_budget=4096,
    minimum_per_face=32,
    chord_tolerance_mm=0.05,
    seed_sha256=None,
):
    import numpy as np

    path = Path(path)
    file_digest = hashlib.sha256(path.read_bytes()).digest()
    sha256 = file_digest.hex()
    digest = file_digest if seed_sha256 is None else bytes.fromhex(seed_sha256)
    if len(digest) != 32:
        raise GeometryValidationError("seed_sha256 must contain 32 bytes")
    seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
    rng = np.random.default_rng(seed)
    faces = _load_single_valid_solid(path).Faces()
    face_areas = [float(face.Area()) for face in faces]
    counts = allocate_face_samples(
        face_areas,
        total_budget=total_budget,
        minimum_per_face=minimum_per_face,
    )
    point_blocks = []
    face_slices = []
    start = 0
    for face, count in zip(faces, counts):
        points = _sample_face(face, count, rng, chord_tolerance_mm)
        point_blocks.append(points)
        stop = start + len(points)
        face_slices.append((start, stop))
        start = stop
    return {
        "sha256": sha256,
        "seed": seed,
        "points": np.concatenate(point_blocks, axis=0),
        "face_slices": face_slices,
        "face_sample_counts": counts,
        "face_areas_mm2": face_areas,
    }


def _direction_metrics(source, target):
    import numpy as np
    from scipy.spatial import cKDTree

    distances = cKDTree(target["points"]).query(source["points"], k=1)[0]
    face_distances = [distances[start:stop] for start, stop in source["face_slices"]]
    face_means = [float(np.mean(values)) for values in face_distances]
    face_p95 = [float(np.percentile(values, 95)) for values in face_distances]
    return {
        "mean": float(np.average(face_means, weights=source["face_areas_mm2"])),
        "p95": float(np.percentile(distances, 95)),
        "face_p95": face_p95,
    }


def compare_step_files(
    path_a,
    path_b,
    total_budget=4096,
    minimum_per_face=32,
    shared_seed_sha256=None,
):
    sample_a = sample_step_surface(
        path_a, total_budget, minimum_per_face, seed_sha256=shared_seed_sha256
    )
    sample_b = sample_step_surface(
        path_b, total_budget, minimum_per_face, seed_sha256=shared_seed_sha256
    )
    a_to_b = _direction_metrics(sample_a, sample_b)
    b_to_a = _direction_metrics(sample_b, sample_a)
    distances = {
        "a_to_b_mean_mm": a_to_b["mean"],
        "a_to_b_p95_mm": a_to_b["p95"],
        "b_to_a_mean_mm": b_to_a["mean"],
        "b_to_a_p95_mm": b_to_a["p95"],
        "symmetric_mean_mm": (a_to_b["mean"] + b_to_a["mean"]) / 2.0,
        "symmetric_p95_mm": max(a_to_b["p95"], b_to_a["p95"]),
        "max_face_p95_mm": max(a_to_b["face_p95"] + b_to_a["face_p95"]),
    }
    return {
        "sampling": {
            "minimum_per_face": int(minimum_per_face),
            "requested_total_budget": int(total_budget),
            "seed_source": "first_8_bytes_of_shared_sha256"
            if shared_seed_sha256 is not None
            else "first_8_bytes_of_file_sha256",
            "global_mean_weighting": "source_face_area",
        },
        "a": inspect_step(path_a),
        "b": inspect_step(path_b),
        "surface_distance_mm": distances,
    }


def roundtrip_step(source_path, output_path):
    import cadquery as cq

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(_load_single_valid_solid(source_path), str(output_path))
    _load_single_valid_solid(output_path)
    return output_path


def calibrate_baseline(reference_path, roundtrip_path, total_budget=4096):
    roundtrip_path = Path(roundtrip_path)
    if roundtrip_path.exists():
        _load_single_valid_solid(roundtrip_path)
    else:
        roundtrip_step(reference_path, roundtrip_path)
    same_first = compare_step_files(reference_path, reference_path, total_budget)
    same_second = compare_step_files(reference_path, reference_path, total_budget)
    roundtrip_first = compare_step_files(reference_path, roundtrip_path, total_budget)
    roundtrip_second = compare_step_files(reference_path, roundtrip_path, total_budget)
    return {
        "calibration_version": "gate1-0.1",
        "contract": "calibration_only_no_general_acceptance_threshold",
        "same_file": same_first,
        "roundtrip": roundtrip_first,
        "repeatability": {
            "same_file_exact": same_first["surface_distance_mm"]
            == same_second["surface_distance_mm"],
            "roundtrip_exact": roundtrip_first["surface_distance_mm"]
            == roundtrip_second["surface_distance_mm"],
        },
    }
