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


def _optional_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def collect_case_records(development_run, held_out_run, labels):
    records = []
    for run_dir in (Path(development_run), Path(held_out_run)):
        manifest = _optional_json(run_dir / "manifest.json")
        for case_id in manifest.get("case_ids", []):
            case_dir = run_dir / "cases" / case_id
            label = labels[case_id]
            status = _optional_json(case_dir / "final_status.json")
            inference = _optional_json(case_dir / "analysis" / "inference_log.json")
            replay = _optional_json(case_dir / "replay" / "replay_log.json")
            metrics = _optional_json(
                case_dir / "validation" / "validation_metrics.json"
            )
            correction = _optional_json(
                case_dir / "sequence" / "manual_correction.json"
            )
            audit = gate4_pipeline.audit_gate4_case_package(case_dir)
            records.append(
                {
                    "case_id": case_id,
                    "run_id": manifest.get("run_id"),
                    **label,
                    "terminal_status": status.get("terminal_status"),
                    "ambiguous": bool(status.get("ambiguous")),
                    "package_complete": bool(audit.get("complete")),
                    "package_issues": audit.get("issues", []),
                    "route": (inference.get("route") or {}).get("route"),
                    "fusion_attempted": replay is not None,
                    "fusion_failed": replay is not None
                    and replay.get("status") != "success",
                    "geometry_validated": metrics is not None,
                    "geometry_pass": metrics.get("geometry_pass")
                    if metrics is not None
                    else None,
                    "volume_iou": metrics.get("volume_iou")
                    if metrics is not None
                    else None,
                    "symmetric_difference_ratio": metrics.get(
                        "symmetric_difference_ratio"
                    )
                    if metrics is not None
                    else None,
                    "validation_mode": metrics.get("validation_mode")
                    if metrics is not None
                    else None,
                    "boolean_validation_failed": metrics.get(
                        "boolean_validation_failed"
                    )
                    if metrics is not None
                    else None,
                    "automatic_processing_seconds": inference.get(
                        "automatic_processing_seconds", 0.0
                    ),
                    "manual_correction_count": correction.get(
                        "correction_count", 0
                    )
                    if correction is not None
                    else 0,
                    "failure_stage": status.get("failure_stage"),
                    "failure_code": status.get("failure_code"),
                }
            )
    return records


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
