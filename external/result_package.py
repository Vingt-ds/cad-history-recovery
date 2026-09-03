"""Gate 2 benchmark selection and auditable result-package contracts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


TERMINAL_STATUSES = {"automatic_success", "manual_success", "unsupported", "failed"}
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class ResultPackageError(ValueError):
    """Raised when a Gate 2 selection or result package violates its contract."""


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path, data):
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    Path(path).write_bytes(text.encode("utf-8"))


def load_gate2_cases(project_root):
    """Derive D-S01 through D-S10 without exposing expected labels to inference."""
    project_root = Path(project_root)
    matrix_path = project_root / "benchmarks" / "case_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    selected = []
    for case in matrix.get("cases", []):
        case_id = case.get("case_id")
        if (
            case.get("split") == "development"
            and case.get("family") == "single_extrusion"
            and isinstance(case_id, str)
            and re.fullmatch(r"D-S(?:0[1-9]|10)", case_id)
        ):
            selected.append(
                {
                    "case_id": case_id,
                    "split": "development",
                    "family": "single_extrusion",
                    "source": case.get("source"),
                    "units": matrix.get("units"),
                    "output_step": case.get("output_step"),
                }
            )
    selected.sort(key=lambda item: item["case_id"])
    expected = [f"D-S{index:02d}" for index in range(1, 11)]
    if [item["case_id"] for item in selected] != expected:
        raise ResultPackageError("gate2_case_selection_mismatch")
    return selected


def validate_development_input(project_root, input_path):
    project_root = Path(project_root).resolve()
    input_path = Path(input_path).resolve()
    development = (project_root / "benchmarks" / "inputs" / "development").resolve()
    held_out = (project_root / "benchmarks" / "inputs" / "held_out").resolve()
    if input_path.is_relative_to(held_out):
        raise ResultPackageError("held_out_input_forbidden")
    if not input_path.is_relative_to(development):
        raise ResultPackageError("input_path_outside_benchmark")
    if not input_path.is_file():
        raise ResultPackageError("input_step_not_found")
    return input_path


def create_run(
    project_root,
    run_id,
    git_commit,
    git_dirty_at_start,
    matrix_sha256,
    benchmark_manifest_sha256,
    case_ids,
    environment,
    validation_protocol_sha256=None,
):
    """Create immutable run metadata; an existing run directory is never reused."""
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ResultPackageError("invalid_run_id")
    run_dir = Path(project_root) / "benchmark_results" / run_id
    if run_dir.exists():
        raise ResultPackageError("run_exists")
    run_dir.mkdir(parents=True)
    manifest = {
        "manifest_schema": "gate2-run-manifest-0.1",
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": str(git_commit),
        "git_dirty_at_start": bool(git_dirty_at_start),
        "matrix_sha256": matrix_sha256,
        "benchmark_manifest_sha256": benchmark_manifest_sha256,
        "selection_rule": "development && single_extrusion && case_id in D-S01..D-S10",
        "case_ids": list(case_ids),
        "schema_versions": {"brep_summary": "brep-summary-0.1", "sequence": "cadseq-0.2"},
        "validation_protocol_ref": "../../config/gate2_validation_protocol.json",
        "validation_protocol_sha256": validation_protocol_sha256,
        "seed_policy": "first_8_bytes_of_reference_step_sha256_shared_by_comparison_pair",
        "environment_ref": "environment.json",
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "environment.json", environment)
    return run_dir


def audit_case_package(case_dir):
    """Audit required and status-conditional artifacts without inferring success."""
    case_dir = Path(case_dir)
    missing = []
    invalid = []

    def require(relative):
        if not (case_dir / relative).is_file():
            missing.append(relative)

    for relative in (
        "metadata/input_metadata.json",
        "analysis/inference_log.json",
        "final_status.json",
    ):
        require(relative)

    status_path = case_dir / "final_status.json"
    if not status_path.is_file():
        return {"complete": False, "missing": missing, "invalid": invalid}
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        invalid.append("final_status.invalid_json")
        return {"complete": False, "missing": missing, "invalid": invalid}

    terminal = status.get("terminal_status")
    if terminal not in TERMINAL_STATUSES:
        invalid.append("final_status.terminal_status")
    metadata_path = case_dir / "metadata" / "input_metadata.json"
    valid_step = True
    if metadata_path.is_file():
        try:
            valid_step = json.loads(metadata_path.read_text(encoding="utf-8")).get("valid_step", True)
        except (OSError, json.JSONDecodeError):
            invalid.append("input_metadata.invalid_json")
    if valid_step:
        require("analysis/brep_summary.json")

    if terminal in {"automatic_success", "manual_success"}:
        for relative in (
            "analysis/candidates.json",
            "sequence/inferred_sequence.json",
            "replay/replay_log.json",
            "replay/replay.f3d",
            "replay/replay.step",
            "validation/validation_metrics.json",
        ):
            require(relative)
        if terminal == "manual_success":
            require("sequence/manual_correction.json")
    elif terminal == "failed":
        for field in ("failure_stage", "failure_code", "error_summary"):
            if not isinstance(status.get(field), str) or not status[field]:
                invalid.append(f"final_status.{field}")
        if not (case_dir / "validation" / "validation_metrics.json").is_file():
            if not isinstance(status.get("not_applicable_reason"), str) or not status[
                "not_applicable_reason"
            ]:
                invalid.append("final_status.not_applicable_reason")
    elif terminal == "unsupported":
        for field in ("scope_rule", "not_applicable_reason"):
            if not isinstance(status.get(field), str) or not status[field]:
                invalid.append(f"final_status.{field}")

    return {"complete": not missing and not invalid, "missing": missing, "invalid": invalid}


def frozen_input_hashes(project_root):
    root = Path(project_root)
    return {
        "matrix_sha256": _sha256(root / "benchmarks" / "case_matrix.json"),
        "benchmark_manifest_sha256": _sha256(root / "benchmarks" / "manifest.json"),
    }
