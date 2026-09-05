"""Gate 4 formal-run creation and immutable raw-result sealing."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import candidate_validation
import gate3_pipeline
import gate4_policy
import gate4_inference
import gate4_validation
import result_package


class Gate4PipelineError(ValueError):
    pass


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _semantic_sha256(path):
    normalized = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _git_snapshot(code_root):
    code_root = Path(code_root).resolve()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=code_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=code_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Gate4PipelineError("git_snapshot_failed") from exc
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Gate4PipelineError("invalid_git_commit")
    return commit, bool(status.strip())


def _verify_freeze(code_root):
    code_root = Path(code_root)
    lock_path = code_root / "config" / "gate4_freeze_lock.json"
    lock = _read_json(lock_path)
    if (
        lock.get("freeze_schema") != "gate4-freeze-lock-0.1"
        or lock.get("frozen") is not True
    ):
        raise Gate4PipelineError("invalid_gate4_freeze_lock")
    if lock.get("evaluation_commit_binding") != "containing_git_commit":
        raise Gate4PipelineError("invalid_evaluation_commit_binding")
    files = lock.get("files")
    if (
        not isinstance(files, dict)
        or "config/gate4_input_inventory.json" not in files
        or "config/gate4_semantic_hash_inventory.json" not in files
    ):
        raise Gate4PipelineError("freeze_file_inventory_missing")
    for relative, expected in files.items():
        path = (code_root / relative).resolve()
        if not path.is_relative_to(code_root.resolve()) or not path.is_file():
            raise Gate4PipelineError("freeze_file_missing")
        if _sha256(path) != expected:
            raise Gate4PipelineError("freeze_file_hash_mismatch")
    semantic = _read_json(code_root / "config" / "gate4_semantic_hash_inventory.json")
    if (
        semantic.get("semantic_hash_inventory_schema")
        != "gate4-semantic-hashes-0.1"
        or semantic.get("hash_mode") != "sha256_lf_normalized_text"
        or not isinstance(semantic.get("files"), dict)
        or not semantic["files"]
    ):
        raise Gate4PipelineError("semantic_hash_inventory_invalid")
    for relative, expected in semantic["files"].items():
        path = (code_root / relative).resolve()
        if not path.is_relative_to(code_root.resolve()) or not path.is_file():
            raise Gate4PipelineError("semantic_file_missing")
        if _semantic_sha256(path) != expected:
            raise Gate4PipelineError("semantic_file_hash_mismatch")
    return lock_path, lock


def _assert_formal_execution_context(code_root, run_dir):
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = _read_json(manifest_path)
    if manifest.get("manifest_schema") != "gate4-run-manifest-0.1":
        return manifest
    commit, _ = _git_snapshot(code_root)
    if commit != manifest.get("git_commit"):
        raise Gate4PipelineError("evaluation_commit_mismatch")
    _verify_freeze(code_root)
    if manifest.get("evaluation_split") == "held_out":
        if run_dir.parent.name != "benchmark_results":
            raise Gate4PipelineError("formal_run_layout_invalid")
        lock_path = (
            run_dir.parent.parent
            / "logs"
            / "gate4"
            / "heldout_execution_lock.json"
        )
        if not lock_path.is_file():
            raise Gate4PipelineError("held_out_execution_lock_missing")
        lock = _read_json(lock_path)
        if (
            lock.get("lock_schema") != "gate4-heldout-execution-lock-0.1"
            or lock.get("run_id") != manifest.get("run_id")
            or lock.get("evaluation_commit") != commit
            or lock.get("attempt_number") != 1
        ):
            raise Gate4PipelineError("held_out_execution_lock_mismatch")
    return manifest


def create_formal_run(
    code_root,
    results_root,
    run_id,
    split,
    environment,
):
    code_root = Path(code_root).resolve()
    git_commit, git_dirty_at_start = _git_snapshot(code_root)
    if git_dirty_at_start:
        raise Gate4PipelineError("formal_run_requires_clean_git")
    if not isinstance(run_id, str) or result_package.RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise Gate4PipelineError("invalid_run_id")
    lock_path, _ = _verify_freeze(code_root)
    inventory_path = code_root / "config" / "gate4_input_inventory.json"
    inventory = _read_json(inventory_path)
    cases = gate4_policy.select_cases(inventory, split)

    run_dir = Path(results_root).resolve() / "benchmark_results" / run_id
    if run_dir.exists():
        raise Gate4PipelineError("run_exists")
    if split == "held_out":
        heldout_lock = (
            Path(results_root).resolve()
            / "logs"
            / "gate4"
            / "heldout_execution_lock.json"
        )
        if heldout_lock.exists():
            raise Gate4PipelineError("held_out_already_executed")
        heldout_lock.parent.mkdir(parents=True, exist_ok=True)
        result_package._write_json(
            heldout_lock,
            {
                "lock_schema": "gate4-heldout-execution-lock-0.1",
                "run_id": run_id,
                "evaluation_commit": git_commit,
                "attempt_number": 1,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    run_dir.mkdir(parents=True)
    result_package._write_json(
        run_dir / "manifest.json",
        {
            "manifest_schema": "gate4-run-manifest-0.1",
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_split": split,
            "git_commit": git_commit,
            "git_dirty_at_start": False,
            "expected_labels_loaded": False,
            "case_ids": [case["case_id"] for case in cases],
            "case_count": 15,
            "input_inventory_sha256": _sha256(inventory_path),
            "benchmark_manifest_sha256": inventory[
                "benchmark_manifest_sha256"
            ],
            "freeze_lock_sha256": _sha256(lock_path),
            "manual_correction_policy": "automatic_only",
            "schema_versions": {
                "brep_summary": "brep-summary-0.1",
                "sequence": "cadseq-0.2",
                "semantic_inference": "gate4-semantic-inference-0.1",
                "validation": "gate4-validation-0.1",
            },
            "environment_ref": "environment.json",
        },
    )
    result_package._write_json(run_dir / "environment.json", environment)
    return run_dir, cases


def _validate_case_input(code_root, case):
    root = Path(code_root).resolve()
    path = (root / case["path"]).resolve()
    expected_parent = (root / "benchmarks" / "inputs" / case["split"]).resolve()
    if not path.is_relative_to(expected_parent):
        raise Gate4PipelineError("input_path_outside_frozen_split")
    if not path.is_file():
        raise Gate4PipelineError("input_step_missing")
    if _sha256(path) != case["sha256"]:
        raise Gate4PipelineError("input_step_hash_mismatch")
    return path


def run_analysis_cases(
    code_root,
    run_dir,
    run_id,
    cases,
    gate2_protocol,
    gate3_protocol,
    infer_fn=None,
):
    manifest = _assert_formal_execution_context(code_root, run_dir)
    if (
        any(case.get("split") == "held_out" for case in cases)
        and manifest.get("manifest_schema") != "gate4-run-manifest-0.1"
    ):
        raise Gate4PipelineError("held_out_requires_formal_run")
    infer = gate4_inference.inspect_and_infer_step if infer_fn is None else infer_fn
    run_dir = Path(run_dir)
    failed = []
    unsupported = []
    awaiting = []
    for case in cases:
        case_id = case["case_id"]
        case_dir = run_dir / "cases" / case_id
        if case_dir.exists():
            raise Gate4PipelineError("case_exists")
        input_path = _validate_case_input(code_root, case)
        metadata = {
            "metadata_schema": "gate4-input-metadata-0.1",
            "run_id": run_id,
            "model_id": case_id,
            "relative_path": Path(case["path"]).as_posix(),
            "source_step_sha256": case["sha256"],
            "source": case["source"],
            "units": case["units"],
            "split": case["split"],
            "valid_step": True,
        }
        (case_dir / "metadata").mkdir(parents=True)
        result_package._write_json(
            case_dir / "metadata" / "input_metadata.json", metadata
        )
        started = time.perf_counter()
        try:
            semantic = infer(
                input_path,
                case["sha256"],
                case_dir / "work",
                gate2_protocol,
                gate3_protocol,
            )
            elapsed = time.perf_counter() - started
            summary = semantic.get("brep_summary")
            if not isinstance(summary, dict):
                raise Gate4PipelineError("brep_summary_missing_from_semantics")
            (case_dir / "analysis").mkdir(parents=True, exist_ok=True)
            result_package._write_json(
                case_dir / "analysis" / "brep_summary.json", summary
            )
            if semantic.get("candidate_generation_entered"):
                result_package._write_json(
                    case_dir / "analysis" / "candidates.json",
                    {
                        "candidates_schema": "gate4-candidate-evidence-0.1",
                        "source_step_sha256": case["sha256"],
                        "route": semantic["route"],
                        "candidate_set": semantic.get("candidate_set", []),
                        "selected_candidate_id": semantic.get(
                            "selected_candidate_id"
                        ),
                        "ambiguous": bool(semantic.get("ambiguous")),
                        "pre_fusion_validation": semantic.get("validation"),
                    },
                )
            outcome = semantic.get("semantic_outcome")
            inference_log = {
                "inference_log_schema": "gate4-inference-log-0.1",
                "model_id": case_id,
                "source_step_sha256": case["sha256"],
                "route": semantic["route"],
                "semantic_outcome": outcome,
                "ambiguous": bool(semantic.get("ambiguous")),
                "selected_candidate_id": semantic.get("selected_candidate_id"),
                "automatic_processing_seconds": elapsed,
            }
            if outcome == "candidate_selected":
                (case_dir / "sequence").mkdir(parents=True, exist_ok=True)
                result_package._write_json(
                    case_dir / "sequence" / "inferred_sequence.json",
                    semantic["selected_sequence"],
                )
                inference_log["status"] = "awaiting_fusion"
                awaiting.append(case_id)
            elif outcome == "unsupported":
                inference_log["status"] = "unsupported"
                inference_log["failure_code"] = semantic.get("failure_code")
                result_package._write_json(
                    case_dir / "final_status.json",
                    {
                        "terminal_status": "unsupported",
                        "ambiguous": bool(semantic.get("ambiguous")),
                        "scope_rule": semantic.get("unsupported_rule")
                        or semantic["route"]["reason"],
                        "not_applicable_reason": "No replayable hypothesis exists inside the frozen Gate 2/3 scope",
                    },
                )
                unsupported.append(case_id)
            else:
                raise Gate4PipelineError("invalid_semantic_outcome")
            result_package._write_json(
                case_dir / "analysis" / "inference_log.json", inference_log
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            code = str(exc).split(":", 1)[0] or exc.__class__.__name__
            analysis_dir = case_dir / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            result_package._write_json(
                analysis_dir / "inference_log.json",
                {
                    "inference_log_schema": "gate4-inference-log-0.1",
                    "model_id": case_id,
                    "status": "failure",
                    "failure_stage": "semantic_inference",
                    "failure_code": code,
                    "error_summary": str(exc),
                    "automatic_processing_seconds": elapsed,
                },
            )
            result_package._write_json(
                case_dir / "final_status.json",
                {
                    "terminal_status": "failed",
                    "ambiguous": False,
                    "failure_stage": "semantic_inference",
                    "failure_code": code,
                    "error_summary": str(exc),
                    "not_applicable_reason": "Fusion replay was not attempted",
                },
            )
            failed.append(case_id)
    summary = {
        "analysis_summary_schema": "gate4-analysis-summary-0.1",
        "run_id": run_id,
        "failed_case_ids": failed,
        "unsupported_case_ids": unsupported,
        "awaiting_fusion_case_ids": awaiting,
    }
    result_package._write_json(run_dir / "analysis_summary.json", summary)
    return summary


def finalize_replay_case(code_root, case_dir, gate2_protocol, gate3_protocol):
    root = Path(code_root).resolve()
    case_dir = Path(case_dir)
    _assert_formal_execution_context(root, case_dir.parent.parent)
    status_path = case_dir / "final_status.json"
    if status_path.exists():
        raise Gate4PipelineError("final_status_exists")
    metadata = _read_json(case_dir / "metadata" / "input_metadata.json")
    candidates = _read_json(case_dir / "analysis" / "candidates.json")
    replay_log = _read_json(case_dir / "replay" / "replay_log.json")
    ambiguous = bool(candidates.get("ambiguous"))
    if replay_log.get("status") != "success":
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": replay_log.get("error_code") or "FUSION_REPLAY_FAILURE",
            "error_summary": replay_log.get("error") or "Fusion replay failed",
            "not_applicable_reason": "No replay entity was available for validation",
        }
        result_package._write_json(status_path, status)
        return status

    replay_f3d = case_dir / "replay" / "replay.f3d"
    replay_step = case_dir / "replay" / "replay.step"
    frame_error = replay_log.get("world_frame_max_error_mm")
    if not replay_f3d.is_file() or not replay_step.is_file():
        code = "replay_artifact_missing"
    elif not isinstance(frame_error, (int, float)) or isinstance(frame_error, bool):
        code = "world_frame_evidence_missing"
    else:
        code = None
    if code is not None:
        status = {
            "terminal_status": "failed",
            "ambiguous": ambiguous,
            "failure_stage": "fusion_replay",
            "failure_code": code,
            "error_summary": "Fusion replay evidence is incomplete",
            "not_applicable_reason": "No trusted replay entity was available for validation",
        }
        result_package._write_json(status_path, status)
        return status

    reference = (root / metadata["relative_path"]).resolve()
    benchmark_root = (root / "benchmarks" / "inputs").resolve()
    if not reference.is_relative_to(benchmark_root) or not reference.is_file():
        raise Gate4PipelineError("reference_path_invalid")
    if _sha256(reference) != metadata["source_step_sha256"]:
        raise Gate4PipelineError("reference_hash_mismatch")
    route = candidates.get("route", {}).get("route")
    if route == "gate2":
        frozen = candidate_validation.validate_replay_step(
            reference, replay_step, gate2_protocol
        )
    elif route == "gate3":
        internal_model_id = "shape-" + metadata["source_step_sha256"][:16]
        frozen = gate3_pipeline.validate_gate3_replay(
            reference, replay_step, internal_model_id, gate3_protocol
        )
    else:
        raise Gate4PipelineError("invalid_replay_route")

    overlap = gate4_validation.calculate_volume_iou(reference, replay_step)
    metrics = dict(frozen)
    metrics.update(overlap)
    metrics["validation_schema"] = "gate4-validation-0.1"
    metrics["frozen_geometry_protocol"] = route
    metrics["surface_only_pass"] = None
    (case_dir / "validation").mkdir(parents=True, exist_ok=True)
    result_package._write_json(
        case_dir / "validation" / "validation_metrics.json", metrics
    )
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
            "failure_code": "GEOMETRY_MISMATCH",
            "error_summary": "Replay failed the frozen route-specific geometry protocol",
        }
    result_package._write_json(status_path, status)
    return status


def write_replay_request(project_root, run_dir, run_id, case_ids, output_path):
    root = Path(project_root).resolve()
    run_dir = Path(run_dir).resolve()
    output = Path(output_path).resolve()
    if not run_dir.is_relative_to(root) or not output.is_relative_to(root):
        raise Gate4PipelineError("path_outside_project")
    manifest = _assert_formal_execution_context(root, run_dir)
    if (
        manifest.get("manifest_schema") != "gate4-run-manifest-0.1"
        or manifest.get("run_id") != run_id
        or manifest.get("case_count") != 15
        or manifest.get("case_ids") != list(case_ids)
    ):
        raise Gate4PipelineError("replay_request_manifest_mismatch")
    if output.exists():
        raise Gate4PipelineError("replay_request_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    result_package._write_json(
        output,
        {
            "request_version": "gate4-replay-0.1",
            "run_id": run_id,
            "run_relative_path": run_dir.relative_to(root).as_posix(),
            "case_ids": list(case_ids),
        },
    )
    return output


def finalize_replay_run(code_root, run_dir, gate2_protocol, gate3_protocol):
    run_dir = Path(run_dir)
    output = run_dir / "finalization_summary.json"
    if output.exists():
        raise Gate4PipelineError("finalization_summary_exists")
    manifest = _assert_formal_execution_context(code_root, run_dir)
    case_ids = manifest.get("case_ids", [])
    if len(case_ids) != 15 or len(set(case_ids)) != 15:
        raise Gate4PipelineError("formal_case_count_mismatch")
    pending = [
        case_id
        for case_id in case_ids
        if not (run_dir / "cases" / case_id / "final_status.json").is_file()
    ]
    batch = _read_json(run_dir / "batch_replay_log.json")
    records = batch.get("cases", [])
    attempted_ids = [record.get("case_id") for record in records]
    if (
        batch.get("status") != "complete"
        or batch.get("run_id") != manifest.get("run_id")
        or batch.get("requested_case_count") != 15
        or batch.get("attempted_replay_count") != len(records)
        or batch.get("success_count", 0) + batch.get("failure_count", 0)
        != len(records)
        or sorted(attempted_ids) != sorted(pending)
    ):
        raise Gate4PipelineError("batch_replay_incomplete")

    statuses = {}
    for case_id in case_ids:
        status_path = run_dir / "cases" / case_id / "final_status.json"
        statuses[case_id] = (
            _read_json(status_path)
            if status_path.is_file()
            else finalize_replay_case(
                code_root,
                run_dir / "cases" / case_id,
                gate2_protocol,
                gate3_protocol,
            )
        )
    counts = Counter(status["terminal_status"] for status in statuses.values())
    summary = {
        "finalization_schema": "gate4-finalization-0.1",
        "run_id": manifest["run_id"],
        "evaluation_split": manifest.get("evaluation_split"),
        "terminal_status_counts": dict(sorted(counts.items())),
        "cases": statuses,
    }
    result_package._write_json(output, summary)
    return summary


def _file_inventory(run_dir):
    run_dir = Path(run_dir)
    return [
        {
            "path": path.relative_to(run_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(run_dir.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "seal.json"
    ]


def audit_gate4_case_package(case_dir):
    case_dir = Path(case_dir)
    base = result_package.audit_case_package(case_dir)
    issues = list(base.get("issues", []))
    try:
        status = _read_json(case_dir / "final_status.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return {"complete": False, "issues": sorted(set(issues))}

    terminal = status.get("terminal_status")
    paths = {
        "candidates": case_dir / "analysis" / "candidates.json",
        "sequence": case_dir / "sequence" / "inferred_sequence.json",
        "manual_correction": case_dir / "sequence" / "manual_correction.json",
        "replay_log": case_dir / "replay" / "replay_log.json",
        "replay_f3d": case_dir / "replay" / "replay.f3d",
        "replay_step": case_dir / "replay" / "replay.step",
        "validation": case_dir / "validation" / "validation_metrics.json",
    }
    if terminal == "manual_success":
        issues.append("manual_success_forbidden")
    if terminal == "unsupported":
        for name, path in paths.items():
            if path.exists():
                issues.append(f"unsupported_forbids_{name}")
    if terminal == "failed":
        stage = status.get("failure_stage")
        if stage == "semantic_inference":
            for name, path in paths.items():
                if path.exists():
                    issues.append(f"semantic_failure_forbids_{name}")
        elif stage == "fusion_replay":
            for name in ("candidates", "sequence", "replay_log"):
                if not paths[name].is_file():
                    issues.append(f"fusion_failure_requires_{name}")
        elif stage == "geometry_validation":
            for name in (
                "candidates",
                "sequence",
                "replay_log",
                "replay_f3d",
                "replay_step",
                "validation",
            ):
                if not paths[name].is_file():
                    issues.append(f"geometry_failure_requires_{name}")
    issues = sorted(set(issues))
    return {"complete": bool(base.get("complete")) and not issues, "issues": issues}


def seal_run(run_dir):
    run_dir = Path(run_dir)
    seal_path = run_dir / "seal.json"
    if seal_path.exists():
        raise Gate4PipelineError("run_already_sealed")
    manifest = _read_json(run_dir / "manifest.json")
    case_ids = manifest.get("case_ids", [])
    if len(case_ids) != 15 or len(set(case_ids)) != 15:
        raise Gate4PipelineError("formal_case_count_mismatch")
    audits = {
        case_id: audit_gate4_case_package(run_dir / "cases" / case_id)
        for case_id in case_ids
    }
    if not all(audit["complete"] for audit in audits.values()):
        raise Gate4PipelineError("incomplete_case_packages")
    statuses = [
        _read_json(run_dir / "cases" / case_id / "final_status.json")[
            "terminal_status"
        ]
        for case_id in case_ids
    ]
    seal = {
        "seal_schema": "gate4-run-seal-0.1",
        "run_id": manifest["run_id"],
        "evaluation_split": manifest["evaluation_split"],
        "git_commit": manifest["git_commit"],
        "case_count": 15,
        "package_complete_count": 15,
        "terminal_status_counts": dict(sorted(Counter(statuses).items())),
        "files": _file_inventory(run_dir),
    }
    result_package._write_json(seal_path, seal)
    return seal


def verify_seal(run_dir):
    run_dir = Path(run_dir)
    seal_path = run_dir / "seal.json"
    if not seal_path.is_file():
        return {"valid": False, "reason": "seal_missing"}
    try:
        seal = _read_json(seal_path)
        current = _file_inventory(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"valid": False, "reason": str(exc)}
    valid = (
        seal.get("seal_schema") == "gate4-run-seal-0.1"
        and seal.get("case_count") == 15
        and seal.get("files") == current
    )
    return {"valid": valid, "reason": None if valid else "file_inventory_mismatch"}
