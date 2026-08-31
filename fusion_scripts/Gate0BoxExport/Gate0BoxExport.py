"""Fusion Gate 0 script: create a fresh box document and export one STEP."""

import hashlib
import json
import os
import platform
import sys
import traceback

import adsk.core
import adsk.fusion


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mm_to_internal(units, value):
    return units.convert(value, "mm", units.internalUnits)


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != "gate0-0.1":
        raise ValueError("schema_version must be gate0-0.1")
    if config.get("units") != "mm":
        raise ValueError("units must be mm")
    model = config.get("model", {})
    if model.get("type") != "box":
        raise ValueError("model.type must be box")
    for field in ("width", "depth", "height"):
        value = model.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("model.{} must be positive".format(field))
    return config


def _choose_run(project_root):
    for run_number in (1, 2):
        run_id = "run{:02d}".format(run_number)
        step_path = os.path.join(project_root, "models", "fusion_script_box_{}.step".format(run_id))
        log_path = os.path.join(project_root, "logs", "fusion_{}.json".format(run_id))
        if not os.path.exists(step_path) and not os.path.exists(log_path):
            return run_id, step_path, log_path
    raise RuntimeError("run01 and run02 already exist; preserve evidence instead of overwriting")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    project_root = _project_root()
    config_path = os.path.join(project_root, "config", "gate0_box.json")
    run_id = None
    log_path = None

    try:
        config = _load_config(config_path)
        run_id, step_path, log_path = _choose_run(project_root)
        os.makedirs(os.path.dirname(step_path), exist_ok=True)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise RuntimeError("new document is not a Fusion Design")

        component = design.rootComponent
        sketch = component.sketches.add(component.xYConstructionPlane)
        model = config["model"]
        units = design.unitsManager
        width = _mm_to_internal(units, model["width"])
        depth = _mm_to_internal(units, model["depth"])
        height = _mm_to_internal(units, model["height"])

        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(width, depth, 0),
        )
        if sketch.profiles.count != 1:
            raise RuntimeError("expected exactly one closed rectangle profile")

        component.features.extrudeFeatures.addSimple(
            sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(height),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        )
        if component.bRepBodies.count != 1:
            raise RuntimeError("expected body_count=1")
        body = component.bRepBodies.item(0)
        if body.faces.count != 6:
            raise RuntimeError("expected face_count=6")

        options = design.exportManager.createSTEPExportOptions(step_path, component)
        if not design.exportManager.execute(options):
            raise RuntimeError("Fusion STEP export returned false")

        record = {
            "status": "success",
            "run_id": run_id,
            "json_sha256": _sha256(config_path),
            "fusion_version": app.version,
            "python_version": platform.python_version(),
            "body_count": component.bRepBodies.count,
            "face_count": body.faces.count,
            "output_path": step_path,
            "document_name": document.name,
            "ascii_path_fallback": False,
        }
        with open(log_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, ensure_ascii=False)
        ui.messageBox("Gate 0 {} succeeded.\n{}".format(run_id, step_path))
    except Exception as exc:
        failure = {
            "status": "failure",
            "run_id": run_id,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "fusion_version": getattr(app, "version", "unknown"),
            "python_version": sys.version,
        }
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as handle:
                json.dump(failure, handle, indent=2, ensure_ascii=False)
        ui.messageBox("Gate 0 script failed:\n{}\n\n{}".format(exc, traceback.format_exc()))
