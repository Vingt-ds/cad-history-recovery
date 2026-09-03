"""Gate 2 analysis pipeline with immutable debug runs and case-level failure isolation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

import brep_inspection
import candidate_validation
import profile_reconstruction
import result_package


EXPECTED_CASE_IDS = [f"D-S{index:02d}" for index in range(1, 11)]


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result_package._write_json(path, data)


def capture_environment():
    import cadquery
    import numpy
    import OCP
    import scipy

    ocp_version = getattr(OCP, "__version__", None)
    if not ocp_version:
        for distribution in ("cadquery-ocp", "OCP"):
            try:
                ocp_version = importlib.metadata.version(distribution)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    return {
        "environment_schema": "gate2-environment-0.1",
        "platform": platform.platform(),
        "external_python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "packages": {
            "cadquery": cadquery.__version__,
            "ocp": ocp_version,
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
        },
        "fusion": {"status": "pending_runtime_capture"},
    }


def create_debug_run(project_root, run_id, case_ids):
    if not isinstance(run_id, str) or result_package.RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise result_package.ResultPackageError("invalid_run_id")
    run_dir = Path(project_root) / "logs" / "gate2" / "debug_runs" / run_id
    if run_dir.exists():
        raise result_package.ResultPackageError("run_exists")
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_schema": "gate2-debug-manifest-0.1",
            "run_id": run_id,
            "run_kind": "debug",
            "case_ids": list(case_ids),
            "terminal_gate_claim": False,
        },
    )
    return run_dir


def create_formal_run(
    project_root,
    run_id,
    git_commit,
    git_dirty_at_start,
    environment,
):
    project_root = Path(project_root)
    if git_dirty_at_start:
        raise result_package.ResultPackageError("formal_run_requires_clean_git")
    if not isinstance(git_commit, str) or re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise result_package.ResultPackageError("invalid_git_commit")

    protocol_path = project_root / "config" / "gate2_validation_protocol.json"
    protocol_bytes = protocol_path.read_bytes()
    protocol_sha256 = hashlib.sha256(protocol_bytes).hexdigest()
    expected_sha256 = (
        project_root / "config" / "gate2_validation_protocol.json.sha256"
    ).read_text(encoding="ascii").strip()
    if protocol_sha256 != expected_sha256:
        raise result_package.ResultPackageError("validation_protocol_hash_mismatch")
    protocol = json.loads(protocol_bytes)
    if protocol.get("frozen") is not True:
        raise result_package.ResultPackageError("validation_protocol_not_frozen")

    cases = result_package.load_gate2_cases(project_root)
    hashes = result_package.frozen_input_hashes(project_root)
    run_dir = result_package.create_run(
        project_root,
        run_id=run_id,
        git_commit=git_commit,
        git_dirty_at_start=False,
        matrix_sha256=hashes["matrix_sha256"],
        benchmark_manifest_sha256=hashes["benchmark_manifest_sha256"],
        case_ids=[case["case_id"] for case in cases],
        environment=environment,
        validation_protocol_sha256=protocol_sha256,
    )
    return run_dir, cases, protocol


def write_replay_request(project_root, run_dir, run_id, case_ids, output_path):
    project_root = Path(project_root).resolve()
    run_dir = Path(run_dir).resolve()
    output_path = Path(output_path).resolve()
    if not run_dir.is_relative_to(project_root) or not output_path.is_relative_to(project_root):
        raise result_package.ResultPackageError("path_outside_project")
    if sorted(case_ids) != EXPECTED_CASE_IDS or len(set(case_ids)) != 10:
        raise result_package.ResultPackageError("gate2_case_selection_mismatch")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite replay request: {output_path}")
    ordered = ["D-S04"] + [case_id for case_id in EXPECTED_CASE_IDS if case_id != "D-S04"]
    _write_json(
        output_path,
        {
            "request_version": "gate2-replay-0.1",
            "run_id": run_id,
            "run_relative_path": run_dir.relative_to(project_root).as_posix(),
            "case_ids": ordered,
        },
    )
    return output_path


def _metadata(run_id, case, input_path):
    return {
        "metadata_schema": "gate2-input-metadata-0.1",
        "run_id": run_id,
        "model_id": case["case_id"],
        "relative_path": Path(case["output_step"]).as_posix(),
        "source_step_sha256": result_package._sha256(input_path),
        "source": case.get("source"),
        "units": case.get("units"),
        "split": case.get("split"),
        "valid_step": True,
    }


def _failure_stage(exc):
    if isinstance(exc, brep_inspection.BRepInspectionError):
        return "brep_inspection"
    if isinstance(exc, profile_reconstruction.ProfileReconstructionError):
        return "profile_reconstruction"
    if isinstance(exc, candidate_validation.CandidateValidationError):
        return "candidate_validation"
    return "analysis_pipeline"


def _failure_code(exc):
    message = str(exc).strip()
    return message.split(":", 1)[0] if message else exc.__class__.__name__


def run_analysis_cases(project_root, run_dir, run_id, cases, protocol):
    project_root = Path(project_root)
    run_dir = Path(run_dir)
    failed = []
    awaiting_fusion = []

    for case in cases:
        case_id = case["case_id"]
        case_dir = run_dir / "cases" / case_id
        if case_dir.exists():
            raise result_package.ResultPackageError("case_exists")
        input_path = result_package.validate_development_input(
            project_root, project_root / case["output_step"]
        )
        metadata = _metadata(run_id, case, input_path)
        _write_json(case_dir / "metadata" / "input_metadata.json", metadata)
        stage = "brep_inspection"
        try:
            summary, context = brep_inspection.inspect_step_with_context(input_path, case_id)
            _write_json(case_dir / "analysis" / "brep_summary.json", summary)
            stage = "candidate_validation"
            validated = candidate_validation.validate_inferred_facts(
                input_path,
                summary,
                context,
                case_dir / "work" / "candidate_rebuilds",
                protocol,
            )
            selected_id = validated["ranking"]["selected_candidate_id"]
            if selected_id is None:
                raise candidate_validation.CandidateValidationError("no_validated_candidate")
            _write_json(
                case_dir / "analysis" / "candidates.json",
                {
                    "model_id": case_id,
                    "source_step_sha256": summary["source_step_sha256"],
                    "inference": validated["inference"],
                    "ranking": validated["ranking"],
                },
            )
            _write_json(
                case_dir / "sequence" / "inferred_sequence.json",
                validated["sequences"][selected_id],
            )
            _write_json(
                case_dir / "analysis" / "inference_log.json",
                {
                    "inference_log_schema": "gate2-inference-log-0.1",
                    "model_id": case_id,
                    "status": "awaiting_fusion",
                    "selected_candidate_id": selected_id,
                    "qualified_candidate_count": validated["ranking"][
                        "qualified_candidate_count"
                    ],
                    "ambiguous": validated["ranking"]["ambiguous"],
                    "completed_stages": [
                        "input_validation",
                        "brep_inspection",
                        "candidate_generation",
                        "profile_reconstruction",
                        "cadquery_validation",
                        "sequence_generation",
                    ],
                },
            )
            awaiting_fusion.append(case_id)
        except Exception as exc:
            if stage == "brep_inspection":
                metadata["valid_step"] = False
                _write_json(
                    case_dir / "metadata" / "input_metadata.json", metadata
                )
            failure_stage = _failure_stage(exc)
            code = _failure_code(exc)
            _write_json(
                case_dir / "analysis" / "inference_log.json",
                {
                    "inference_log_schema": "gate2-inference-log-0.1",
                    "model_id": case_id,
                    "status": "failure",
                    "failure_stage": failure_stage,
                    "failure_code": code,
                    "error_summary": str(exc),
                },
            )
            _write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "failed",
                    "ambiguous": False,
                    "failure_stage": failure_stage,
                    "failure_code": code,
                    "error_summary": str(exc),
                    "not_applicable_reason": "Fusion replay was not attempted",
                },
            )
            failed.append(case_id)

    batch = {
        "run_id": run_id,
        "failed_case_ids": failed,
        "awaiting_fusion_case_ids": awaiting_fusion,
    }
    _write_json(run_dir / "analysis_summary.json", batch)
    return batch


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finalize_replay_case(project_root, case_dir, protocol):
    project_root = Path(project_root)
    case_dir = Path(case_dir)
    status_path = case_dir / "final_status.json"
    if status_path.exists():
        raise FileExistsError(f"refusing to overwrite final status: {status_path}")
    metadata = _read_json(case_dir / "metadata" / "input_metadata.json")
    replay_log = _read_json(case_dir / "replay" / "replay_log.json")
    candidates = _read_json(case_dir / "analysis" / "candidates.json")
    case_id = metadata["model_id"]
    ambiguous = bool(candidates["ranking"]["ambiguous"])

    if replay_log.get("status") != "success":
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": replay_log.get("error_code") or "fusion_replay_failed",
            "error_summary": replay_log.get("error") or "Fusion replay failed",
            "not_applicable_reason": "No valid replay entity was available for geometry validation",
        }
        _write_json(status_path, status)
        return status

    replay_f3d = case_dir / "replay" / "replay.f3d"
    replay_step = case_dir / "replay" / "replay.step"
    if not replay_f3d.is_file() or not replay_step.is_file():
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": "replay_artifact_missing",
            "error_summary": "Fusion success log exists but F3D or STEP output is missing",
            "not_applicable_reason": "No complete replay entity was available for validation",
        }
        _write_json(status_path, status)
        return status

    input_path = result_package.validate_development_input(
        project_root, project_root / metadata["relative_path"]
    )
    metrics = candidate_validation.validate_replay_step(input_path, replay_step, protocol)
    _write_json(case_dir / "validation" / "validation_metrics.json", metrics)
    if metrics["geometry_pass"]:
        status = {
            "terminal_status": "automatic_success",
            "ambiguous": ambiguous,
            "selected_candidate_id": candidates["ranking"]["selected_candidate_id"],
        }
    else:
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "geometry_validation",
            "failure_code": "frozen_geometry_check_failed",
            "error_summary": "Fusion replay failed the frozen Gate 2 geometry protocol",
        }
    _write_json(status_path, status)
    return status


def finalize_replay_run(project_root, run_dir, protocol):
    run_dir = Path(run_dir)
    summary_path = run_dir / "finalization_summary.json"
    if summary_path.exists():
        raise FileExistsError(f"refusing to overwrite finalization summary: {summary_path}")
    batch_path = run_dir / "batch_replay_log.json"
    if not batch_path.is_file():
        raise result_package.ResultPackageError("batch_replay_incomplete")
    batch = _read_json(batch_path)
    if (
        batch.get("status") != "complete"
        or batch.get("case_count") != 10
        or batch.get("success_count", 0) + batch.get("failure_count", 0) != 10
    ):
        raise result_package.ResultPackageError("batch_replay_incomplete")
    manifest = _read_json(run_dir / "manifest.json")
    if manifest.get("case_ids") != EXPECTED_CASE_IDS:
        raise result_package.ResultPackageError("gate2_case_selection_mismatch")

    statuses = {}
    for case_id in EXPECTED_CASE_IDS:
        case_dir = run_dir / "cases" / case_id
        existing = case_dir / "final_status.json"
        statuses[case_id] = (
            _read_json(existing)
            if existing.is_file()
            else finalize_replay_case(project_root, case_dir, protocol)
        )
    counts = {status: 0 for status in sorted(result_package.TERMINAL_STATUSES)}
    for status in statuses.values():
        counts[status["terminal_status"]] += 1
    summary = {
        "finalization_schema": "gate2-finalization-0.1",
        "run_id": manifest["run_id"],
        "terminal_status_counts": counts,
        "cases": statuses,
    }
    _write_json(summary_path, summary)
    return summary
