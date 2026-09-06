"""Thin Fusion entrypoint delegating replay to the frozen Gate 2 executor."""

import importlib.util
import json
import os
import traceback

import adsk.core


class DemoWrapperError(ValueError):
    pass


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_adapter(project_root):
    path = os.path.join(
        project_root,
        "fusion_scripts",
        "Gate2SequenceReplay",
        "Gate2SequenceReplay.py",
    )
    spec = importlib.util.spec_from_file_location("_gate5_frozen_gate2_adapter", path)
    if spec is None or spec.loader is None:
        raise DemoWrapperError("frozen_executor_load_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_request(project_root):
    request_path = os.path.join(project_root, "runs", "gate5_active_request.json")
    with open(request_path, "r", encoding="utf-8") as handle:
        request = json.load(handle)
    if request.get("request_version") != "gate5-demo-replay-0.1":
        raise DemoWrapperError("invalid_request_version")
    run_id = request.get("run_id")
    case_id = request.get("case_id")
    relative = request.get("run_relative_path")
    if not isinstance(run_id, str) or not isinstance(case_id, str) or not isinstance(relative, str):
        raise DemoWrapperError("invalid_request")
    if os.path.isabs(relative):
        raise DemoWrapperError("invalid_run_path")
    run_dir = os.path.abspath(os.path.join(project_root, relative))
    allowed = os.path.abspath(os.path.join(project_root, "runs", "gate5"))
    if os.path.dirname(run_dir) != allowed or os.path.basename(run_dir) != run_id:
        raise DemoWrapperError("invalid_run_path")
    return request_path, request, run_dir


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        project_root = _project_root()
        request_path, request, run_dir = _load_request(project_root)
        case_id = request["case_id"]
        replay_dir = os.path.join(run_dir, "replay")
        paths = {
            "sequence": os.path.join(run_dir, "sequence", "inferred_sequence.json"),
            "replay_dir": replay_dir,
            "f3d": os.path.join(replay_dir, "replay.f3d"),
            "step": os.path.join(replay_dir, "replay.step"),
            "log": os.path.join(replay_dir, "replay_log.json"),
        }
        adapter = _load_adapter(project_root)
        core = adapter._load_core(project_root)
        adapter._record_fusion_environment(os.path.join(run_dir, "environment.json"), app)
        record = adapter._replay_case(app, core, case_id, paths)
        adapter._write_json(
            os.path.join(run_dir, "batch_replay_log.json"),
            {
                "status": "complete",
                "run_id": request["run_id"],
                "request_sha256": adapter._sha256(request_path),
                "case_count": 1,
                "success_count": 1,
                "failure_count": 0,
                "cases": [record],
            },
        )
        ui.messageBox("Gate 5 demo replay complete: {}".format(case_id))
    except Exception as exc:
        ui.messageBox("Gate 5 demo replay failed:\n{}\n\n{}".format(exc, traceback.format_exc()))
