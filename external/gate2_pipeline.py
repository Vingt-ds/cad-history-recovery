"""Gate 2 analysis pipeline with immutable debug runs and case-level failure isolation."""

from __future__ import annotations

import json
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
