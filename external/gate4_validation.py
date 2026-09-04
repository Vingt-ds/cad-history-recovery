"""Gate 4 volume-overlap metrics without changing frozen geometry PASS rules."""

from __future__ import annotations

import math

import geometry_validation


def _boolean_volumes(reference_solid, replay_solid):
    intersection = reference_solid.intersect(replay_solid)
    union = reference_solid.fuse(replay_solid)
    return float(intersection.Volume()), float(union.Volume())


def calculate_volume_iou(reference_path, replay_path):
    """Return IoU evidence; boolean failure is explicit and never becomes a PASS."""

    reference = geometry_validation._load_single_valid_solid(reference_path)
    replay = geometry_validation._load_single_valid_solid(replay_path)
    try:
        intersection_volume, union_volume = _boolean_volumes(reference, replay)
        if (
            not math.isfinite(intersection_volume)
            or not math.isfinite(union_volume)
            or intersection_volume < 0.0
            or union_volume <= 0.0
        ):
            raise ValueError("invalid_boolean_volume")
        ratio = intersection_volume / union_volume
        if ratio < -1e-12 or ratio > 1.0 + 1e-12:
            raise ValueError("volume_iou_out_of_range")
        ratio = min(1.0, max(0.0, ratio))
        return {
            "volume_overlap_schema": "gate4-volume-overlap-0.1",
            "intersection_volume_mm3": intersection_volume,
            "union_volume_mm3": union_volume,
            "volume_iou": ratio,
            "symmetric_difference_ratio": 1.0 - ratio,
            "boolean_validation_failed": False,
            "validation_mode": "volume_iou",
        }
    except Exception as exc:
        return {
            "volume_overlap_schema": "gate4-volume-overlap-0.1",
            "intersection_volume_mm3": None,
            "union_volume_mm3": None,
            "volume_iou": None,
            "symmetric_difference_ratio": None,
            "boolean_validation_failed": True,
            "validation_mode": "surface_only",
            "boolean_error_summary": str(exc),
        }
