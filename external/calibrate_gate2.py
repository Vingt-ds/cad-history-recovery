"""Independent Gate 2 STEP round-trip and controlled-perturbation calibration."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import geometry_validation
import result_package


TOTAL_SAMPLE_BUDGET = 4096
MINIMUM_PER_FACE = 32
CONTROLLED_TRANSLATION_MM = 5.0
PERTURBATION_CASE_IDS = {"D-S01", "D-S04", "D-S07", "D-S09"}


def derive_surface_protocol(records):
    roundtrip = [item for item in records if item["kind"] == "roundtrip"]
    perturbation = [item for item in records if item["kind"] == "perturbation"]
    if not roundtrip or not perturbation:
        return {"mode": "diagnostic_only", "reason": "insufficient_calibration_groups"}

    keys = ("symmetric_p95_ratio", "max_face_p95_ratio")
    intervals = {}
    separated = True
    for key in keys:
        roundtrip_interval = [min(item[key] for item in roundtrip), max(item[key] for item in roundtrip)]
        perturbation_interval = [
            min(item[key] for item in perturbation),
            max(item[key] for item in perturbation),
        ]
        intervals[key] = {
            "roundtrip": roundtrip_interval,
            "perturbation": perturbation_interval,
        }
        separated = separated and roundtrip_interval[1] < perturbation_interval[0]
    if not separated:
        return {"mode": "diagnostic_only", "reason": "normalized_intervals_overlap"}
    return {
        "mode": "threshold",
        "normalization": "reference_bbox_diagonal_mm",
        "intervals": intervals,
        "symmetric_p95_ratio_threshold": (
            intervals["symmetric_p95_ratio"]["roundtrip"][1]
            + intervals["symmetric_p95_ratio"]["perturbation"][0]
        )
        / 2.0,
        "max_face_p95_ratio_threshold": (
            intervals["max_face_p95_ratio"]["roundtrip"][1]
            + intervals["max_face_p95_ratio"]["perturbation"][0]
        )
        / 2.0,
    }


def write_controlled_translation(source_path, output_path, offset_mm=CONTROLLED_TRANSLATION_MM):
    import cadquery as cq

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    solid = geometry_validation._load_single_valid_solid(source_path)
    translated = solid.translate((float(offset_mm), 0.0, 0.0))
    cq.exporters.export(translated, str(output))
    geometry_validation._load_single_valid_solid(output)
    return output


def _bbox_diagonal(summary):
    box = summary["bbox_mm"]
    return math.sqrt(
        (box["xmax"] - box["xmin"]) ** 2
        + (box["ymax"] - box["ymin"]) ** 2
        + (box["zmax"] - box["zmin"]) ** 2
    )


def _record(case_id, kind, reference_path, comparison_path):
    shared_seed_sha256 = geometry_validation._sha256(reference_path)
    first = geometry_validation.compare_step_files(
        reference_path,
        comparison_path,
        total_budget=TOTAL_SAMPLE_BUDGET,
        minimum_per_face=MINIMUM_PER_FACE,
        shared_seed_sha256=shared_seed_sha256,
    )
    second = geometry_validation.compare_step_files(
        reference_path,
        comparison_path,
        total_budget=TOTAL_SAMPLE_BUDGET,
        minimum_per_face=MINIMUM_PER_FACE,
        shared_seed_sha256=shared_seed_sha256,
    )
    distances = first["surface_distance_mm"]
    diagonal = _bbox_diagonal(first["a"])
    return {
        "case_id": case_id,
        "kind": kind,
        "reference_sha256": first["a"]["sha256"],
        "comparison_sha256": first["b"]["sha256"],
        "bbox_diagonal_mm": diagonal,
        "symmetric_p95_mm": distances["symmetric_p95_mm"],
        "max_face_p95_mm": distances["max_face_p95_mm"],
        "symmetric_p95_ratio": distances["symmetric_p95_mm"] / diagonal,
        "max_face_p95_ratio": distances["max_face_p95_mm"] / diagonal,
        "numeric_repeatable": first["surface_distance_mm"] == second["surface_distance_mm"],
    }


def build_protocol(project_root, artifact_root):
    project_root = Path(project_root)
    artifact_root = Path(artifact_root)
    records = []
    selected = result_package.load_gate2_cases(project_root)
    for case in selected:
        case_id = case["case_id"]
        source = result_package.validate_development_input(
            project_root, project_root / case["output_step"]
        )
        roundtrip = artifact_root / "roundtrip" / f"{case_id}.step"
        geometry_validation.roundtrip_step(source, roundtrip)
        records.append(_record(case_id, "roundtrip", source, roundtrip))
        if case_id in PERTURBATION_CASE_IDS:
            perturbed = artifact_root / "controlled_perturbation" / f"{case_id}.step"
            write_controlled_translation(source, perturbed)
            records.append(_record(case_id, "perturbation", source, perturbed))

    return {
        "protocol_schema": "gate2-validation-0.1",
        "frozen": True,
        "selection_rule": "frozen matrix development single_extrusion D-S01..D-S10",
        "calibration_records": records,
        "controlled_perturbation": {
            "case_ids": sorted(PERTURBATION_CASE_IDS),
            "translation_mm": [CONTROLLED_TRANSLATION_MM, 0.0, 0.0],
            "benchmark_member": False,
        },
        "sampling": {
            "total_budget": TOTAL_SAMPLE_BUDGET,
            "minimum_per_face": MINIMUM_PER_FACE,
            "seed_policy": "first_8_bytes_of_reference_step_sha256_shared_by_comparison_pair",
            "numeric_repeatability_required": True,
        },
        "hard_conditions": {
            "single_valid_solid": True,
            "volume_absolute_tolerance_mm3": 1e-6,
            "volume_relative_tolerance": 1e-9,
            "bbox_coordinate_tolerance_mm": 1e-6,
        },
        "surface": derive_surface_protocol(records),
    }


def _canonical_bytes(data):
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_frozen_protocol(protocol, output_path):
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite frozen protocol: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(protocol)
    output.write_bytes(payload)
    digest_path = output.with_suffix(output.suffix + ".sha256")
    digest_path.write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
    return output


def main():
    project_root = Path(__file__).resolve().parents[1]
    artifact_root = project_root / "logs" / "gate2" / "calibration"
    protocol = build_protocol(project_root, artifact_root)
    output = project_root / "config" / "gate2_validation_protocol.json"
    write_frozen_protocol(protocol, output)
    print(output)


if __name__ == "__main__":
    main()
