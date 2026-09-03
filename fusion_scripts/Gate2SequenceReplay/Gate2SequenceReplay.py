"""Batch-replay Gate 2 sequences through the validated Gate 1 replay core."""

import hashlib
import importlib.util
import json
import os
import platform
import re
import sys
import traceback

import adsk.core
import adsk.fusion


class ReplayError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


EXPECTED_CASE_IDS = {"D-S{:02d}".format(index) for index in range(1, 11)}


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_core(project_root):
    core_path = os.path.join(
        project_root,
        "fusion_scripts",
        "Gate1SequenceReplay",
        "Gate1SequenceReplay.py",
    )
    spec = importlib.util.spec_from_file_location("_gate2_gate1_replay_core", core_path)
    if spec is None or spec.loader is None:
        raise ReplayError("core_load_failed", core_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shared(project_root):
    shared_dir = os.path.join(project_root, "shared")

    def load_current(module_name, filename):
        path = os.path.join(shared_dir, filename)
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ReplayError("shared_load_failed", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    frame_math = load_current("_gate2_frame_math_current", "frame_math.py")
    validator = load_current("_gate2_sequence_validator_current", "sequence_validator.py")
    return (
        validator.validate_sequence,
        frame_math.world_point,
        frame_math.parallel_alignment_error,
    )


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, record):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _safe_project_path(project_root, relative_path, code):
    if not isinstance(relative_path, str) or os.path.isabs(relative_path):
        raise ReplayError(code, "path must be project-relative")
    resolved = os.path.abspath(os.path.join(project_root, relative_path))
    if os.path.commonpath((project_root, resolved)) != project_root:
        raise ReplayError(code, "path leaves the project directory")
    return resolved


def _paths(project_root, request):
    if request.get("request_version") != "gate2-replay-0.1":
        raise ReplayError("invalid_request_version", "unsupported replay request version")
    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
        raise ReplayError("invalid_run_id", "invalid Gate 2 run ID")
    run_dir = _safe_project_path(
        project_root, request.get("run_relative_path"), "invalid_run_path"
    )
    case_ids = request.get("case_ids")
    if (
        not isinstance(case_ids, list)
        or len(case_ids) != 10
        or set(case_ids) != EXPECTED_CASE_IDS
        or len(set(case_ids)) != len(case_ids)
        or case_ids[0] != "D-S04"
    ):
        raise ReplayError(
            "invalid_case_set", "request must contain D-S01..D-S10 exactly once with D-S04 first"
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


def _assert_outputs_absent(case_paths):
    existing = [
        case_paths[key]
        for key in ("f3d", "step", "log")
        if os.path.exists(case_paths[key])
    ]
    if existing:
        raise ReplayError(
            "output_exists", "refusing to overwrite existing output: {}".format(", ".join(existing))
        )


def _error_code(exc):
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else "fusion_exception"


def _absolute_frame_plane(component, frame, units):
    origin = adsk.core.Point3D.create(
        units.convert(float(frame["origin"][0]), "mm", units.internalUnits),
        units.convert(float(frame["origin"][1]), "mm", units.internalUnits),
        units.convert(float(frame["origin"][2]), "mm", units.internalUnits),
    )
    normal = adsk.core.Vector3D.create(*[float(value) for value in frame["normal"]])
    geometry = adsk.core.Plane.create(origin, normal)
    plane_input = component.constructionPlanes.createInput()
    if not plane_input.setByPlane(geometry):
        raise ReplayError("construction_plane_failed", "setByPlane returned false")
    plane = component.constructionPlanes.add(plane_input)
    if plane is None:
        raise ReplayError("construction_plane_failed", "Fusion returned a null plane")
    return plane


def _plane_resolver(core, component, operation, angular_tolerance, extrude_features, units):
    reference = operation["sketch_plane"]["semantic_reference"]
    if reference["type"] == "absolute_frame":
        return _absolute_frame_plane(component, operation["sketch_plane"]["frame"], units)
    return core._sketch_plane(component, operation, angular_tolerance, extrude_features)


def _replay_case(app, core, case_id, case_paths):
    if not os.path.isfile(case_paths["sequence"]):
        raise ReplayError("sequence_not_found", case_paths["sequence"])
    _assert_outputs_absent(case_paths)
    sequence = _load_json(case_paths["sequence"])
    validate_sequence, world_point, parallel_alignment_error = _load_shared(_project_root())
    validation = validate_sequence(sequence)
    if not validation["valid"]:
        raise ReplayError(
            "sequence_validation_failed", json.dumps(validation["errors"], ensure_ascii=False)
        )

    document = None
    try:
        os.makedirs(case_paths["replay_dir"], exist_ok=True)
        document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise ReplayError("fusion_design_unavailable", "new document is not a Fusion design")
        component = design.rootComponent
        resolver = lambda comp, op, angle, features, units: _plane_resolver(
            core, comp, op, angle, features, units
        )
        operation_records, world_frame_max_error_mm = core._run_sequence(
            sequence,
            component,
            design,
            world_point,
            parallel_alignment_error,
            plane_resolver=resolver,
        )
        archive = design.exportManager.createFusionArchiveExportOptions(case_paths["f3d"])
        if not design.exportManager.execute(archive):
            raise ReplayError("f3d_export_failed", "Fusion archive export returned false")
        step = design.exportManager.createSTEPExportOptions(case_paths["step"], component)
        if not design.exportManager.execute(step):
            raise ReplayError("step_export_failed", "STEP export returned false")
        body = component.bRepBodies.item(0)
        record = {
            "status": "success",
            "case_id": case_id,
            "model_id": sequence["model_id"],
            "replay_mode": sequence["replay_mode"],
            "sequence_sha256": _sha256(case_paths["sequence"]),
            "fusion_version": app.version,
            "python_version": platform.python_version(),
            "body_count": component.bRepBodies.count,
            "face_count": body.faces.count,
            "world_frame_max_error_mm": world_frame_max_error_mm,
            "operations": operation_records,
            "outputs": {"f3d": "replay.f3d", "step": "replay.step"},
        }
        _write_json(case_paths["log"], record)
        return record
    finally:
        if document is not None:
            document.close(False)


def _record_fusion_environment(path, app):
    environment = _load_json(path) if os.path.isfile(path) else {}
    environment["fusion"] = {
        "version": app.version,
        "python_version": platform.python_version(),
    }
    _write_json(path, environment)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    project_root = _project_root()
    request_path = os.path.join(project_root, "config", "gate2_replay_request.json")
    paths = None
    records = []
    try:
        request = _load_json(request_path)
        paths = _paths(project_root, request)
        if os.path.exists(paths["batch_log"]):
            raise ReplayError("output_exists", "batch_replay_log.json already exists")
        core = _load_core(project_root)
        _record_fusion_environment(paths["environment"], app)
        for case_id in paths["case_ids"]:
            case_paths = paths["cases"][case_id]
            try:
                records.append(_replay_case(app, core, case_id, case_paths))
            except Exception as exc:
                code = _error_code(exc)
                failure = {
                    "status": "failure",
                    "case_id": case_id,
                    "error_code": code,
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
            "case_count": len(records),
            "success_count": sum(item["status"] == "success" for item in records),
            "failure_count": sum(item["status"] == "failure" for item in records),
            "cases": records,
        }
        _write_json(paths["batch_log"], batch)
        ui.messageBox(
            "Gate 2 batch complete: {} success, {} failure".format(
                batch["success_count"], batch["failure_count"]
            )
        )
    except Exception as exc:
        code = _error_code(exc)
        ui.messageBox("Gate 2 batch failed [{}]:\n{}".format(code, exc))
