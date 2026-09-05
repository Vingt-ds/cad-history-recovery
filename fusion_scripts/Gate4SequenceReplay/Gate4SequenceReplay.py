"""Replay one frozen Gate 4 split through the validated Gate 2 adapter."""

import hashlib
import importlib.util
import json
import os
import re
import sys
import traceback

import adsk.core


class ReplayError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_gate2_adapter(project_root):
    path = os.path.join(
        project_root,
        "fusion_scripts",
        "Gate2SequenceReplay",
        "Gate2SequenceReplay.py",
    )
    spec = importlib.util.spec_from_file_location("_gate4_gate2_adapter_current", path)
    if spec is None or spec.loader is None:
        raise ReplayError("adapter_load_failed", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path, record):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_project_path(project_root, relative_path, code):
    if not isinstance(relative_path, str) or os.path.isabs(relative_path):
        raise ReplayError(code, "path must be project-relative")
    resolved = os.path.abspath(os.path.join(project_root, relative_path))
    if os.path.commonpath((project_root, resolved)) != project_root:
        raise ReplayError(code, "path leaves the project directory")
    return resolved


def _paths(project_root, request):
    if request.get("request_version") != "gate4-replay-0.1":
        raise ReplayError("invalid_request_version", "unsupported replay request version")
    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id
    ):
        raise ReplayError("invalid_run_id", "invalid Gate 4 run ID")
    run_dir = _safe_project_path(
        project_root, request.get("run_relative_path"), "invalid_run_path"
    )
    manifest = _load_json(os.path.join(run_dir, "manifest.json"))
    manifest_ids = manifest.get("case_ids")
    case_ids = request.get("case_ids")
    if (
        manifest.get("manifest_schema") != "gate4-run-manifest-0.1"
        or manifest.get("run_id") != run_id
        or manifest.get("case_count") != 15
        or not isinstance(manifest_ids, list)
        or len(manifest_ids) != 15
        or len(set(manifest_ids)) != 15
        or case_ids != manifest_ids
    ):
        raise ReplayError(
            "invalid_case_set",
            "request must exactly match the ordered 15-case run manifest",
        )
    cases = {}
    for case_id in case_ids:
        case_dir = os.path.join(run_dir, "cases", case_id)
        replay_dir = os.path.join(case_dir, "replay")
        cases[case_id] = {
            "sequence": os.path.join(case_dir, "sequence", "inferred_sequence.json"),
            "replay_dir": replay_dir,
            "f3d": os.path.join(replay_dir, "replay.f3d"),
            "step": os.path.join(replay_dir, "replay.step"),
            "log": os.path.join(replay_dir, "replay_log.json"),
        }
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "case_ids": case_ids,
        "cases": cases,
        "batch_log": os.path.join(run_dir, "batch_replay_log.json"),
        "environment": os.path.join(run_dir, "environment.json"),
    }


def _error_code(exc):
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else "fusion_exception"


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    project_root = _project_root()
    request_path = os.path.join(project_root, "config", "gate4_replay_request.json")
    records = []
    try:
        request = _load_json(request_path)
        paths = _paths(project_root, request)
        if os.path.exists(paths["batch_log"]):
            raise ReplayError("output_exists", "batch_replay_log.json already exists")
        gate2 = _load_gate2_adapter(project_root)
        core = gate2._load_core(project_root)
        gate2._record_fusion_environment(paths["environment"], app)
        for case_id in paths["case_ids"]:
            case_paths = paths["cases"][case_id]
            if not os.path.isfile(case_paths["sequence"]):
                continue
            try:
                records.append(gate2._replay_case(app, core, case_id, case_paths))
            except Exception as exc:
                failure = {
                    "status": "failure",
                    "case_id": case_id,
                    "error_code": _error_code(exc),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "fusion_version": getattr(app, "version", "unknown"),
                    "python_version": sys.version,
                }
                if not os.path.exists(case_paths["log"]):
                    _write_json(case_paths["log"], failure)
                records.append(failure)
        batch = {
            "status": "complete",
            "run_id": paths["run_id"],
            "request_sha256": _sha256(request_path),
            "requested_case_count": len(paths["case_ids"]),
            "attempted_replay_count": len(records),
            "success_count": sum(item["status"] == "success" for item in records),
            "failure_count": sum(item["status"] == "failure" for item in records),
            "cases": records,
        }
        _write_json(paths["batch_log"], batch)
        ui.messageBox(
            "Gate 4 batch complete: {} attempted, {} success, {} failure".format(
                batch["attempted_replay_count"],
                batch["success_count"],
                batch["failure_count"],
            )
        )
    except Exception as exc:
        ui.messageBox("Gate 4 batch failed [{}]:\n{}".format(_error_code(exc), exc))
