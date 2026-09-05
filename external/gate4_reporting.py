"""Post-seal Gate 4 label release and descriptive statistics."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

import gate4_pipeline


class Gate4ReportingError(ValueError):
    pass


def load_expected_labels_after_seal(project_root, development_run, held_out_run):
    if not gate4_pipeline.verify_seal(development_run).get("valid"):
        raise Gate4ReportingError("development_run_not_sealed")
    if not gate4_pipeline.verify_seal(held_out_run).get("valid"):
        raise Gate4ReportingError("held_out_run_not_sealed")
    development_manifest = json.loads(
        (Path(development_run) / "manifest.json").read_text(encoding="utf-8")
    )
    held_out_manifest = json.loads(
        (Path(held_out_run) / "manifest.json").read_text(encoding="utf-8")
    )
    if (
        development_manifest.get("manifest_schema") != "gate4-run-manifest-0.1"
        or held_out_manifest.get("manifest_schema") != "gate4-run-manifest-0.1"
        or development_manifest.get("evaluation_split") != "development"
        or held_out_manifest.get("evaluation_split") != "held_out"
    ):
        raise Gate4ReportingError("sealed_run_roles_invalid")
    if development_manifest.get("git_commit") != held_out_manifest.get("git_commit"):
        raise Gate4ReportingError("sealed_run_commit_mismatch")
    matrix = json.loads(
        (Path(project_root) / "benchmarks" / "case_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        case["case_id"]: {
            "split": case["split"],
            "family": case["family"],
            "expected_scope": case["expected_scope"],
            "expected_behavior": case["expected_behavior"],
        }
        for case in matrix.get("cases", [])
    }


def _count_total(count, total):
    return {"count": count, "total": total}


def _summary(records):
    supported = [record for record in records if record["expected_scope"] == "supported"]
    unsupported = [record for record in records if record["expected_scope"] == "unsupported"]
    replayed = [record for record in records if record.get("fusion_attempted")]
    validated = [record for record in records if record.get("geometry_validated")]
    iou_values = [
        float(record["volume_iou"])
        for record in records
        if record.get("volume_iou") is not None
    ]
    processing = [float(record["automatic_processing_seconds"]) for record in records]
    corrections = [int(record["manual_correction_count"]) for record in records]
    failures = Counter(
        (record.get("failure_stage"), record.get("failure_code"))
        for record in records
        if record.get("failure_code")
    )
    return {
        "case_count": len(records),
        "package_complete": _count_total(
            sum(bool(record.get("package_complete")) for record in records),
            len(records),
        ),
        "supported_automatic_success": _count_total(
            sum(record["terminal_status"] == "automatic_success" for record in supported),
            len(supported),
        ),
        "supported_after_manual_success": _count_total(
            sum(
                record["terminal_status"] in {"automatic_success", "manual_success"}
                for record in supported
            ),
            len(supported),
        ),
        "unsupported_correct_rejection": _count_total(
            sum(record["terminal_status"] == "unsupported" for record in unsupported),
            len(unsupported),
        ),
        "ambiguous_case_count": sum(bool(record.get("ambiguous")) for record in records),
        "fusion_replay_failure": _count_total(
            sum(bool(record.get("fusion_failed")) for record in replayed),
            len(replayed),
        ),
        "geometry_pass": _count_total(
            sum(record.get("geometry_pass") is True for record in validated),
            len(validated),
        ),
        "volume_iou": {
            "count": len(iou_values),
            "mean": statistics.fmean(iou_values) if iou_values else None,
            "median": statistics.median(iou_values) if iou_values else None,
            "min": min(iou_values) if iou_values else None,
            "max": max(iou_values) if iou_values else None,
        },
        "surface_only_count": sum(
            record.get("geometry_validated")
            and record.get("validation_mode") == "surface_only"
            for record in records
        ),
        "average_automatic_processing_seconds": statistics.fmean(processing)
        if processing
        else None,
        "average_manual_correction_count": statistics.fmean(corrections)
        if corrections
        else None,
        "failure_counts": {
            f"{stage}:{code}": count
            for (stage, code), count in sorted(failures.items())
        },
    }


def compute_statistics(records):
    records = [dict(record) for record in records]
    return {
        "statistics_schema": "gate4-statistics-0.1",
        "overall": _summary(records),
        "by_split": {
            split: _summary([record for record in records if record["split"] == split])
            for split in ("development", "held_out")
        },
    }
