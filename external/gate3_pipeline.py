"""Gate 3 result-package pipeline for five frozen development through holes."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import brep_inspection
import candidate_validation
import gate2_pipeline
import result_package
import through_hole_inference
import through_hole_reconstruction
import topology_adjacency


EXPECTED_CASE_IDS = ["D-H{:02d}".format(index) for index in range(1, 6)]


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result_package._write_json(path, value)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_cases(project_root):
    return through_hole_inference.load_gate3_development_cases(project_root)


def load_protocol(project_root):
    root = Path(project_root)
    path = root / "config" / "gate3_validation_protocol.json"
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != checksum_path.read_text(encoding="ascii").strip():
        raise result_package.ResultPackageError("validation_protocol_hash_mismatch")
    protocol = _read_json(path)
    if protocol.get("frozen") is not True:
        raise result_package.ResultPackageError("validation_protocol_not_frozen")
    return protocol


def capture_environment():
    environment = gate2_pipeline.capture_environment()
    environment["environment_schema"] = "gate3-environment-0.1"
    return environment


def create_debug_run(project_root, run_id, case_ids):
    if not isinstance(run_id, str) or result_package.RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise result_package.ResultPackageError("invalid_run_id")
    run_dir = Path(project_root) / "logs" / "gate3" / "debug_runs" / run_id
    if run_dir.exists():
        raise result_package.ResultPackageError("run_exists")
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_schema": "gate3-debug-manifest-0.1",
            "run_id": run_id,
            "run_kind": "debug",
            "case_ids": list(case_ids),
            "terminal_gate_claim": False,
        },
    )
    return run_dir


def create_formal_run(project_root, run_id, git_commit, git_dirty_at_start, environment):
    root = Path(project_root)
    if git_dirty_at_start:
        raise result_package.ResultPackageError("formal_run_requires_clean_git")
    if not isinstance(git_commit, str) or re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise result_package.ResultPackageError("invalid_git_commit")
    if not isinstance(run_id, str) or result_package.RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise result_package.ResultPackageError("invalid_run_id")
    protocol = load_protocol(root)
    protocol_path = root / "config" / "gate3_validation_protocol.json"
    protocol_hash = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    cases = load_cases(root)
    hashes = result_package.frozen_input_hashes(root)
    run_dir = root / "benchmark_results" / run_id
    if run_dir.exists():
        raise result_package.ResultPackageError("run_exists")
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_schema": "gate3-run-manifest-0.1",
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "git_dirty_at_start": False,
            "matrix_sha256": hashes["matrix_sha256"],
            "benchmark_manifest_sha256": hashes["benchmark_manifest_sha256"],
            "selection_rule": "development && through_hole && case_id in D-H01..D-H05",
            "case_ids": [case["case_id"] for case in cases],
            "schema_versions": {
                "brep_summary": "brep-summary-0.1",
                "sequence": "cadseq-0.2",
                "coupled_candidates": "coupled-through-hole-candidates-0.1",
            },
            "validation_protocol_ref": "../../config/gate3_validation_protocol.json",
            "validation_protocol_sha256": protocol_hash,
            "seed_policy": "first_8_bytes_of_reference_step_sha256_shared_by_comparison_pair",
            "environment_ref": "environment.json",
        },
    )
    _write_json(run_dir / "environment.json", environment)
    return run_dir, cases, protocol


def write_replay_request(project_root, run_dir, run_id, case_ids, output_path):
    root = Path(project_root).resolve()
    run_dir = Path(run_dir).resolve()
    output = Path(output_path).resolve()
    if not run_dir.is_relative_to(root) or not output.is_relative_to(root):
        raise result_package.ResultPackageError("path_outside_project")
    if sorted(case_ids) != EXPECTED_CASE_IDS or len(set(case_ids)) != 5:
        raise result_package.ResultPackageError("gate3_case_selection_mismatch")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite replay request: {output}")
    ordered = ["D-H04"] + [case_id for case_id in EXPECTED_CASE_IDS if case_id != "D-H04"]
    _write_json(
        output,
        {
            "request_version": "gate3-replay-0.1",
            "run_id": run_id,
            "run_relative_path": run_dir.relative_to(root).as_posix(),
            "case_ids": ordered,
        },
    )
    return output


def _metadata(run_id, case, input_path):
    return {
        "metadata_schema": "gate3-input-metadata-0.1",
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
    if isinstance(exc, through_hole_inference.ThroughHoleInferenceError):
        return "through_hole_inference"
    if isinstance(exc, through_hole_reconstruction.ThroughHoleReconstructionError):
        return "sequence_reconstruction"
    if isinstance(exc, candidate_validation.CandidateValidationError):
        return "candidate_validation"
    return "analysis_pipeline"


def _failure_code(exc):
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code.split(":", 1)[0]
    text = str(exc).strip()
    return text.split(":", 1)[0] if text else exc.__class__.__name__


def _accepted_hole_group(step_path, model_id):
    summary, context = brep_inspection.inspect_step_with_context(step_path, model_id)
    adjacency = topology_adjacency.build_adjacency(summary, context)
    facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
    accepted = [
        group for group in facts.get("hole_fact_groups", []) if group.get("status") == "accepted"
    ]
    if len(accepted) != 1:
        raise candidate_validation.CandidateValidationError(
            "replay_hole_fact_count_mismatch"
        )
    edges = {edge["edge_id"]: edge for edge in summary["solids"][0]["edges"]}
    centers = [
        [float(value) for value in edges[edge_id]["curve_parameters"]["center_mm"]]
        for edge_id in accepted[0]["circle_edge_ids"]
    ]
    return accepted[0], centers


def _subtract(left, right):
    return [float(a) - float(b) for a, b in zip(left, right)]


def _dot(left, right):
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _cross(left, right):
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _norm(vector):
    return math.sqrt(_dot(vector, vector))


def _distance(left, right):
    return _norm(_subtract(left, right))


def _line_offset(point, line_point, line_axis):
    return _norm(_cross(_subtract(point, line_point), line_axis))


def validate_gate3_replay(reference_path, replay_path, model_id, protocol):
    """Combine generic solid checks with exact through-hole feature agreement."""

    conditions = protocol.get("feature_conditions")
    if not isinstance(conditions, dict):
        raise result_package.ResultPackageError("feature_conditions_missing")
    base = candidate_validation.validate_replay_step(reference_path, replay_path, protocol)
    reference_group, reference_centers = _accepted_hole_group(reference_path, model_id)
    replay_group, replay_centers = _accepted_hole_group(replay_path, model_id)
    reference_axis = [float(value) for value in reference_group["measured_axis"]]
    replay_axis = [float(value) for value in replay_group["measured_axis"]]
    axis_dot = max(-1.0, min(1.0, abs(_dot(reference_axis, replay_axis))))
    axis_angle = math.acos(axis_dot)
    axis_offset = max(
        _line_offset(reference_centers[0], replay_centers[0], replay_axis),
        _line_offset(replay_centers[0], reference_centers[0], reference_axis),
    )
    pairings = (
        max(_distance(reference_centers[0], replay_centers[0]), _distance(reference_centers[1], replay_centers[1])),
        max(_distance(reference_centers[0], replay_centers[1]), _distance(reference_centers[1], replay_centers[0])),
    )
    center_error = min(pairings)
    reference_span = _distance(reference_centers[0], reference_centers[1])
    replay_span = _distance(replay_centers[0], replay_centers[1])
    feature = {
        "radius_error_mm": abs(
            float(reference_group["measured_radius_mm"])
            - float(replay_group["measured_radius_mm"])
        ),
        "axis_angle_error_rad": axis_angle,
        "axis_line_offset_mm": axis_offset,
        "opening_center_max_error_mm": center_error,
        "span_error_mm": abs(reference_span - replay_span),
    }
    checks = {
        "radius": feature["radius_error_mm"] <= float(conditions["radius_tolerance_mm"]),
        "axis_angle": feature["axis_angle_error_rad"]
        <= float(conditions["axis_angular_tolerance_rad"]),
        "axis_line_offset": feature["axis_line_offset_mm"]
        <= float(conditions["axis_line_offset_tolerance_mm"]),
        "opening_centers": feature["opening_center_max_error_mm"]
        <= float(conditions["opening_center_tolerance_mm"]),
        "span": feature["span_error_mm"] <= float(conditions["span_tolerance_mm"]),
    }
    feature_pass = all(checks.values())
    base["base_geometry_pass"] = bool(base["geometry_pass"])
    base["feature_match"] = feature
    base["feature_checks"] = checks
    base["feature_match_pass"] = feature_pass
    base["geometry_pass"] = base["base_geometry_pass"] and feature_pass
    return base


def run_analysis_cases(project_root, run_dir, run_id, cases, protocol):
    root = Path(project_root)
    run_dir = Path(run_dir)
    failed = []
    awaiting = []
    for case in cases:
        case_id = case["case_id"]
        case_dir = run_dir / "cases" / case_id
        if case_dir.exists():
            raise result_package.ResultPackageError("case_exists")
        input_path = through_hole_inference.validate_gate3_development_input(
            root, case_id, root / case["output_step"]
        )
        metadata = _metadata(run_id, case, input_path)
        _write_json(case_dir / "metadata" / "input_metadata.json", metadata)
        try:
            summary, context = brep_inspection.inspect_step_with_context(input_path, case_id)
            _write_json(case_dir / "analysis" / "brep_summary.json", summary)
            adjacency = topology_adjacency.build_adjacency(summary, context)
            hole_facts = through_hole_inference.analyze_through_hole_facts(summary, adjacency)
            coupled = through_hole_inference.generate_coupled_candidates(
                summary, adjacency, hole_facts
            )
            accepted = [
                candidate
                for candidate in coupled.get("candidates", [])
                if isinstance(candidate, dict) and candidate.get("status") == "accepted"
            ]
            if len(accepted) != 1:
                raise through_hole_reconstruction.ThroughHoleReconstructionError(
                    "accepted_candidate_count_mismatch"
                )
            selected = accepted[0]
            sequence = through_hole_reconstruction.sequence_from_summary(summary, selected)
            candidate_step = through_hole_reconstruction.rebuild_sequence_step(
                sequence, case_dir / "work" / "candidate_rebuild.step"
            )
            pre_fusion = validate_gate3_replay(
                input_path, candidate_step, case_id, protocol
            )
            if not pre_fusion.get("geometry_pass"):
                raise candidate_validation.CandidateValidationError(
                    "pre_fusion_geometry_check_failed"
                )
            _write_json(
                case_dir / "analysis" / "candidates.json",
                {
                    "candidates_schema": "gate3-candidate-evidence-0.1",
                    "model_id": case_id,
                    "source_step_sha256": summary["source_step_sha256"],
                    "hole_facts": hole_facts,
                    "coupled_candidates": coupled,
                    "selected_candidate_id": selected["candidate_id"],
                    "ambiguous": False,
                    "pre_fusion_validation": pre_fusion,
                },
            )
            through_hole_reconstruction.write_sequence(
                sequence, case_dir / "sequence" / "inferred_sequence.json"
            )
            _write_json(
                case_dir / "analysis" / "inference_log.json",
                {
                    "inference_log_schema": "gate3-inference-log-0.1",
                    "model_id": case_id,
                    "status": "awaiting_fusion",
                    "selected_candidate_id": selected["candidate_id"],
                    "ambiguous": False,
                    "completed_stages": [
                        "input_validation",
                        "brep_inspection",
                        "through_hole_fact_analysis",
                        "coupled_candidate_generation",
                        "external_reconstruction_validation",
                        "sequence_generation",
                    ],
                },
            )
            awaiting.append(case_id)
        except Exception as exc:
            if isinstance(exc, brep_inspection.BRepInspectionError):
                metadata["valid_step"] = False
                _write_json(case_dir / "metadata" / "input_metadata.json", metadata)
            stage = _failure_stage(exc)
            code = _failure_code(exc)
            _write_json(
                case_dir / "analysis" / "inference_log.json",
                {
                    "inference_log_schema": "gate3-inference-log-0.1",
                    "model_id": case_id,
                    "status": "failure",
                    "failure_stage": stage,
                    "failure_code": code,
                    "error_summary": str(exc),
                },
            )
            _write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "failed",
                    "ambiguous": False,
                    "failure_stage": stage,
                    "failure_code": code,
                    "error_summary": str(exc),
                    "not_applicable_reason": "Fusion replay was not attempted",
                },
            )
            failed.append(case_id)
    result = {
        "run_id": run_id,
        "failed_case_ids": failed,
        "awaiting_fusion_case_ids": awaiting,
    }
    _write_json(run_dir / "analysis_summary.json", result)
    return result


def finalize_replay_case(project_root, case_dir, protocol):
    root = Path(project_root)
    case_dir = Path(case_dir)
    status_path = case_dir / "final_status.json"
    if status_path.exists():
        raise FileExistsError(f"refusing to overwrite final status: {status_path}")
    metadata = _read_json(case_dir / "metadata" / "input_metadata.json")
    replay_log = _read_json(case_dir / "replay" / "replay_log.json")
    candidates = _read_json(case_dir / "analysis" / "candidates.json")
    ambiguous = bool(candidates.get("ambiguous"))
    if replay_log.get("status") != "success":
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": replay_log.get("error_code") or "fusion_replay_failed",
            "error_summary": replay_log.get("error") or "Fusion replay failed",
            "not_applicable_reason": "No valid replay entity was available for validation",
        }
        _write_json(status_path, status)
        return status
    replay_f3d = case_dir / "replay" / "replay.f3d"
    replay_step = case_dir / "replay" / "replay.step"
    frame_error = replay_log.get("world_frame_max_error_mm")
    if not replay_f3d.is_file() or not replay_step.is_file():
        code = "replay_artifact_missing"
    elif not isinstance(frame_error, (int, float)) or isinstance(frame_error, bool):
        code = "world_frame_evidence_missing"
    else:
        sequence = _read_json(case_dir / "sequence" / "inferred_sequence.json")
        if float(frame_error) > float(sequence["tolerance"]["length_mm"]):
            code = "world_frame_error_exceeded"
        else:
            code = None
    if code is not None:
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": code,
            "error_summary": "Fusion replay evidence is incomplete or outside frame tolerance",
            "not_applicable_reason": "No trusted replay entity was available for validation",
        }
        _write_json(status_path, status)
        return status
    input_path = through_hole_inference.validate_gate3_development_input(
        root, metadata["model_id"], root / metadata["relative_path"]
    )
    metrics = validate_gate3_replay(
        input_path, replay_step, metadata["model_id"], protocol
    )
    _write_json(case_dir / "validation" / "validation_metrics.json", metrics)
    if metrics["geometry_pass"]:
        status = {
            "terminal_status": "automatic_success",
            "ambiguous": ambiguous,
            "selected_candidate_id": candidates["selected_candidate_id"],
        }
    else:
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "geometry_validation",
            "failure_code": "frozen_geometry_check_failed",
            "error_summary": "Fusion replay failed the frozen Gate 3 geometry protocol",
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
        or batch.get("case_count") != 5
        or batch.get("success_count", 0) + batch.get("failure_count", 0) != 5
    ):
        raise result_package.ResultPackageError("batch_replay_incomplete")
    manifest = _read_json(run_dir / "manifest.json")
    if manifest.get("case_ids") != EXPECTED_CASE_IDS:
        raise result_package.ResultPackageError("gate3_case_selection_mismatch")
    statuses = {}
    for case_id in EXPECTED_CASE_IDS:
        case_dir = run_dir / "cases" / case_id
        status_path = case_dir / "final_status.json"
        statuses[case_id] = (
            _read_json(status_path)
            if status_path.is_file()
            else finalize_replay_case(project_root, case_dir, protocol)
        )
    counts = {status: 0 for status in sorted(result_package.TERMINAL_STATUSES)}
    for status in statuses.values():
        counts[status["terminal_status"]] += 1
    summary = {
        "finalization_schema": "gate3-finalization-0.1",
        "run_id": manifest["run_id"],
        "terminal_status_counts": counts,
        "cases": statuses,
    }
    _write_json(summary_path, summary)
    return summary
