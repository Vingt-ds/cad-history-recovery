"""Gate 5 development-case demonstration orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

import candidate_validation
import gate3_pipeline
import gate4_inference


BASELINE_TAG = "gate0-4-frozen-baseline-v1"
OUTPUT_ROOT = Path("runs/gate5")
ACTIVE_REQUEST = Path("runs/gate5_active_request.json")
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SEALED_ARTIFACT_ONLY = {"D-S01"}


class Gate5DemoError(ValueError):
    """Raised when a demonstration request violates the delivery contract."""


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Gate5DemoError(f"invalid_json:{Path(path).as_posix()}") from exc


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _output_root(project_root, output_root):
    root = Path(project_root).resolve()
    raw = str(output_root)
    if Path(raw).is_absolute() or "\\" in raw or Path(raw).as_posix() != OUTPUT_ROOT.as_posix():
        raise Gate5DemoError("invalid_output_root")
    return root / OUTPUT_ROOT


def _safe_run_dir(project_root, run_dir):
    root = Path(project_root).resolve()
    resolved = Path(run_dir)
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    parent = (root / OUTPUT_ROOT).resolve()
    if resolved.parent != parent or RUN_ID_PATTERN.fullmatch(resolved.name) is None:
        raise Gate5DemoError("invalid_run_dir")
    return resolved


def _load_case(project_root, case_id):
    root = Path(project_root).resolve()
    inventory = _read_json(root / "config" / "gate4_input_inventory.json")
    matches = [case for case in inventory.get("cases", []) if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise Gate5DemoError("case_not_found")
    case = matches[0]
    if case.get("split") != "development":
        raise Gate5DemoError("held_out_forbidden")
    if case_id in SEALED_ARTIFACT_ONLY:
        raise Gate5DemoError("sealed_artifact_only")
    path = (root / str(case.get("path"))).resolve()
    development = (root / "benchmarks" / "inputs" / "development").resolve()
    if not path.is_relative_to(development) or not path.is_file():
        raise Gate5DemoError("invalid_source_path")
    if _sha256(path) != case.get("sha256"):
        raise Gate5DemoError("source_sha256_mismatch")
    return case, path


def _default_run_id(case_id):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"gate5-demo-{stamp}-{uuid.uuid4().hex[:8]}"


def prepare_demo(
    project_root,
    case_id,
    output_root="runs/gate5",
    *,
    run_id=None,
    infer_fn=None,
):
    """Prepare one development case using the frozen Gate 4 inference entrypoint."""

    root = Path(project_root).resolve()
    base = _output_root(root, output_root)
    case, input_path = _load_case(root, case_id)
    run_id = _default_run_id(case_id) if run_id is None else run_id
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise Gate5DemoError("invalid_run_id")
    run_dir = base / run_id
    if run_dir.exists():
        raise Gate5DemoError("run_exists")
    request_path = root / ACTIVE_REQUEST
    if request_path.exists():
        raise Gate5DemoError("active_request_exists")

    gate2_protocol = _read_json(root / "config" / "gate2_validation_protocol.json")
    gate3_protocol = _read_json(root / "config" / "gate3_validation_protocol.json")
    infer = gate4_inference.inspect_and_infer_step if infer_fn is None else infer_fn
    base.mkdir(parents=True, exist_ok=True)
    staging = base / f".inference-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        neutral_step = staging / "source.step"
        neutral_step.write_bytes(input_path.read_bytes())
        semantic = infer(
            neutral_step,
            case["sha256"],
            staging / "work",
            gate2_protocol,
            gate3_protocol,
        )
        run_dir.mkdir()
        if (staging / "work").exists():
            shutil.move(str(staging / "work"), str(run_dir / "work"))
    finally:
        if staging.parent == base and staging.name.startswith(".inference-"):
            shutil.rmtree(staging, ignore_errors=True)
    if semantic.get("semantic_outcome") != "candidate_selected":
        raise Gate5DemoError("no_replayable_candidate")
    route = semantic.get("route", {}).get("route")
    if route not in {"gate2", "gate3"}:
        raise Gate5DemoError("invalid_replay_route")

    metadata = {
        "metadata_schema": "gate5-demo-input-metadata-0.1",
        "run_id": run_id,
        "model_id": case_id,
        "relative_path": Path(case["path"]).as_posix(),
        "source_step_sha256": case["sha256"],
        "source": case.get("source"),
        "units": case.get("units"),
        "split": "development",
        "valid_step": True,
    }
    candidates = {
        "candidates_schema": "gate5-demo-candidate-evidence-0.1",
        "source_step_sha256": case["sha256"],
        "route": semantic["route"],
        "candidate_set": semantic.get("candidate_set", []),
        "selected_candidate_id": semantic.get("selected_candidate_id"),
        "ambiguous": bool(semantic.get("ambiguous")),
        "pre_fusion_validation": semantic.get("validation"),
    }
    _write_json(run_dir / "manifest.json", {
        "manifest_schema": "gate5-demo-manifest-0.1",
        "run_id": run_id,
        "case_id": case_id,
        "evidence_role": "demonstration_only",
        "formal_evaluation": False,
        "source_split": "development",
        "baseline_tag": BASELINE_TAG,
        "source_step_sha256": case["sha256"],
        "replay_route": route,
    })
    _write_json(run_dir / "metadata" / "input_metadata.json", metadata)
    _write_json(run_dir / "analysis" / "brep_summary.json", semantic["brep_summary"])
    _write_json(run_dir / "analysis" / "candidates.json", candidates)
    _write_json(run_dir / "analysis" / "inference_log.json", {
        "inference_log_schema": "gate5-demo-inference-log-0.1",
        "status": "awaiting_fusion",
        "source_step_sha256": case["sha256"],
        "route": semantic["route"],
        "ambiguous": bool(semantic.get("ambiguous")),
        "selected_candidate_id": semantic.get("selected_candidate_id"),
    })
    _write_json(run_dir / "sequence" / "inferred_sequence.json", semantic["selected_sequence"])
    _write_json(request_path, {
        "request_version": "gate5-demo-replay-0.1",
        "run_id": run_id,
        "case_id": case_id,
        "run_relative_path": run_dir.relative_to(root).as_posix(),
    })
    return {"status": "prepared", "run_dir": run_dir, "request_path": request_path}


def finalize_demo(project_root, run_dir):
    """Validate one Fusion replay through the frozen route-specific validator."""

    root = Path(project_root).resolve()
    run_dir = _safe_run_dir(root, run_dir)
    status_path = run_dir / "final_status.json"
    if status_path.exists():
        raise Gate5DemoError("already_finalized")
    manifest = _read_json(run_dir / "manifest.json")
    metadata = _read_json(run_dir / "metadata" / "input_metadata.json")
    candidates = _read_json(run_dir / "analysis" / "candidates.json")
    replay_log_path = run_dir / "replay" / "replay_log.json"
    replay_f3d = run_dir / "replay" / "replay.f3d"
    replay_step = run_dir / "replay" / "replay.step"
    if not replay_log_path.is_file() or not replay_f3d.is_file() or not replay_step.is_file():
        raise Gate5DemoError("replay_artifact_missing")
    replay_log = _read_json(replay_log_path)
    if replay_log.get("status") != "success":
        raise Gate5DemoError("replay_artifact_missing")

    reference = (root / metadata["relative_path"]).resolve()
    development = (root / "benchmarks" / "inputs" / "development").resolve()
    if not reference.is_relative_to(development) or not reference.is_file():
        raise Gate5DemoError("invalid_source_path")
    if _sha256(reference) != metadata.get("source_step_sha256"):
        raise Gate5DemoError("source_sha256_mismatch")
    route = manifest.get("replay_route")
    if candidates.get("route", {}).get("route") != route:
        raise Gate5DemoError("replay_route_mismatch")
    if route == "gate2":
        metrics = candidate_validation.validate_replay_step(
            reference,
            replay_step,
            _read_json(root / "config" / "gate2_validation_protocol.json"),
        )
    elif route == "gate3":
        metrics = gate3_pipeline.validate_gate3_replay(
            reference,
            replay_step,
            "shape-" + metadata["source_step_sha256"][:16],
            _read_json(root / "config" / "gate3_validation_protocol.json"),
        )
    else:
        raise Gate5DemoError("invalid_replay_route")
    _write_json(run_dir / "validation" / "validation_metrics.json", metrics)
    status = {
        "final_status_schema": "gate5-demo-final-status-0.1",
        "terminal_status": "automatic_success" if metrics.get("geometry_pass") else "failed",
        "ambiguous": bool(candidates.get("ambiguous")),
        "selected_candidate_id": candidates.get("selected_candidate_id"),
        "evidence_role": "demonstration_only",
        "formal_evaluation": False,
    }
    if not metrics.get("geometry_pass"):
        status.update({
            "failure_stage": "geometry_validation",
            "failure_code": "frozen_geometry_check_failed",
        })
    request_path = root / ACTIVE_REQUEST
    if not request_path.is_file():
        raise Gate5DemoError("active_request_missing")
    request = _read_json(request_path)
    if (
        request.get("request_version") != "gate5-demo-replay-0.1"
        or request.get("run_id") != manifest.get("run_id")
        or request.get("run_relative_path") != run_dir.relative_to(root).as_posix()
    ):
        raise Gate5DemoError("active_request_mismatch")
    used_request = run_dir / "replay_request_used.json"
    if used_request.exists():
        raise Gate5DemoError("replay_request_archive_exists")
    request_path.replace(used_request)
    _write_json(status_path, status)
    return status


def verify_demo(project_root, run_dir):
    """Read-only completeness and provenance check for a finalized demo package."""

    root = Path(project_root).resolve()
    run_dir = _safe_run_dir(root, run_dir)
    required = (
        "manifest.json",
        "metadata/input_metadata.json",
        "analysis/brep_summary.json",
        "analysis/candidates.json",
        "analysis/inference_log.json",
        "sequence/inferred_sequence.json",
        "replay/replay.f3d",
        "replay/replay.step",
        "replay/replay_log.json",
        "batch_replay_log.json",
        "environment.json",
        "replay_request_used.json",
        "validation/validation_metrics.json",
        "final_status.json",
    )
    missing = [relative for relative in required if not (run_dir / relative).is_file()]
    errors = []
    if not missing:
        manifest = _read_json(run_dir / "manifest.json")
        metadata = _read_json(run_dir / "metadata" / "input_metadata.json")
        status = _read_json(run_dir / "final_status.json")
        if manifest.get("baseline_tag") != BASELINE_TAG:
            errors.append("baseline_tag")
        if manifest.get("evidence_role") != "demonstration_only" or manifest.get("formal_evaluation") is not False:
            errors.append("evidence_role")
        if manifest.get("source_split") != "development" or metadata.get("split") != "development":
            errors.append("source_split")
        reference = (root / str(metadata.get("relative_path"))).resolve()
        development = (root / "benchmarks" / "inputs" / "development").resolve()
        if not reference.is_relative_to(development) or not reference.is_file():
            errors.append("source_path")
        elif _sha256(reference) != metadata.get("source_step_sha256"):
            errors.append("source_sha256")
        if status.get("terminal_status") not in {"automatic_success", "failed"}:
            errors.append("terminal_status")
    return {
        "valid": not missing and not errors,
        "run_dir": run_dir.as_posix(),
        "missing": missing,
        "errors": errors,
    }


def _jsonable(value):
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--project-root", required=True)
    prepare.add_argument("--case-id", required=True)
    prepare.add_argument("--output-root", required=True)
    prepare.add_argument("--run-id")
    for name in ("finalize", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--project-root", required=True)
        command.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_demo(
                args.project_root,
                args.case_id,
                args.output_root,
                run_id=args.run_id,
            )
        elif args.command == "finalize":
            result = finalize_demo(args.project_root, args.run_dir)
        else:
            result = verify_demo(args.project_root, args.run_dir)
        print(json.dumps(_jsonable(result), sort_keys=True))
        return 0 if result.get("valid", True) else 1
    except Exception as exc:
        print(json.dumps({"error": str(exc), "status": "failed"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
