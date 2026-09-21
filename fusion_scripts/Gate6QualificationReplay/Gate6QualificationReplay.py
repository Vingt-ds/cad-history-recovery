"""Qualification-only Fusion replay adapter for Gate 6 implementation tests.

This script deliberately cannot execute the frozen formal OS/DE campaign.  Its
only purpose is to qualify the construction and export mechanics on independent
synthetic boxes before formal execution is separately authorized.
"""

import datetime
import hashlib
import json
import math
import os
import platform
import re
import sys
import traceback
from decimal import Decimal

import adsk.core
import adsk.fusion


REQUEST_VERSION = "gate6-qualification-replay-0.1"
CHALLENGE_VERSION = "gate6-fusion-qualification-challenge-0.1"
SPECIFICATION_COMMIT = "c440aace7306b9d68e2ae6a6ae757f36d8db1d85"
FROZEN_CONFIG_SHA256 = "9e81b6c3d119a53df8735969a29cb6b282539e460b3de22c415d81d71b896a6b"
OUTPUT_NAMES = (
    "base.step",
    "join_tool.step",
    "cut_tool.step",
    "after_modifier_1.step",
    "final.step",
    "construction.f3d",
    "qualification_log.json",
)
FORMAL_RUN_RE = re.compile(r"^(?:OS|DE)_(?:JC|CJ)_R[123]$")


class ReplayError(Exception):
    def __init__(self, code, message, diagnostics=None):
        super().__init__(message)
        self.code = code
        self.diagnostics = list(diagnostics or [])


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_request_sha256(request):
    payload = json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_frozen_config(project_root):
    path = os.path.join(project_root, "config", "gate6_precheck_v0_1.json")
    with open(path, "rb") as handle:
        payload = handle.read()
    measured_sha256 = hashlib.sha256(payload).hexdigest()
    if measured_sha256 != FROZEN_CONFIG_SHA256:
        raise ReplayError(
            "specification_binding_failure",
            "frozen config SHA-256 does not match the qualification build",
        )
    return json.loads(payload.decode("utf-8")), measured_sha256


def _safe_output_dir(path):
    if not isinstance(path, str) or not path.strip() or not os.path.isabs(path):
        return False
    normalized = os.path.normcase(os.path.normpath(path))
    parts = [part.casefold() for part in normalized.replace("\\", "/").split("/") if part]
    for index in range(len(parts) - 2):
        if parts[index : index + 3] == ["runs", "gate6", "precheck"]:
            return False
    return any(part in {"qualification", "qualifications", "temp", "tmp"} or part.startswith("qualification-") for part in parts)


def _safe_challenge_path(path):
    if not _safe_output_dir(path) or any(ord(character) < 32 for character in path):
        return False
    normalized = os.path.normcase(os.path.normpath(path))
    tokens = re.findall(r"[A-Za-z0-9_]+", normalized)
    return not any(FORMAL_RUN_RE.fullmatch(token) for token in tokens)


def _load_challenge(request, config):
    path = request.get("external_preflight_record_path")
    expected_sha256 = request.get("external_preflight_record_sha256")
    if not isinstance(path, str) or not _safe_challenge_path(path):
        raise ReplayError("challenge_path_invalid", "challenge path must be a safe absolute qualification path")
    if not os.path.isfile(path):
        raise ReplayError("challenge_missing", "qualification challenge file does not exist")
    if not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ReplayError("schema_invalid", "external_preflight_record_sha256 must be lowercase SHA-256")
    with open(path, "rb") as handle:
        payload = handle.read()
    measured_sha256 = hashlib.sha256(payload).hexdigest()
    if measured_sha256 != expected_sha256:
        raise ReplayError("challenge_hash_mismatch", "qualification challenge SHA-256 mismatch")
    try:
        challenge = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayError("challenge_invalid_json", "qualification challenge is not valid UTF-8 JSON") from exc
    required = {
        "schema_version",
        "challenge_id",
        "challenge_nonce",
        "specification_commit",
        "contract_version",
        "expected_environment",
    }
    if not isinstance(challenge, dict) or set(challenge) != required:
        raise ReplayError("challenge_schema_invalid", "qualification challenge fields are not exact")
    if challenge["schema_version"] != CHALLENGE_VERSION:
        raise ReplayError("challenge_schema_invalid", "qualification challenge schema is invalid")
    challenge_id = request.get("challenge_id")
    nonce = request.get("challenge_nonce")
    if (
        not isinstance(challenge_id, str)
        or not challenge_id.startswith("QCH-")
        or any(ord(character) < 32 for character in challenge_id)
        or FORMAL_RUN_RE.search(challenge_id)
        or challenge["challenge_id"] != challenge_id
    ):
        raise ReplayError("challenge_binding_failure", "challenge identifier does not match request")
    if (
        not isinstance(nonce, str)
        or re.fullmatch(r"[0-9a-f]{32,128}", nonce) is None
        or challenge["challenge_nonce"] != nonce
    ):
        raise ReplayError("challenge_binding_failure", "challenge nonce does not match request")
    if challenge["specification_commit"] != SPECIFICATION_COMMIT:
        raise ReplayError("challenge_binding_failure", "challenge specification commit is invalid")
    if challenge["contract_version"] != config.get("contract_version"):
        raise ReplayError("challenge_binding_failure", "challenge contract version is invalid")
    if challenge["expected_environment"] != config.get("environment"):
        raise ReplayError("challenge_binding_failure", "challenge expected environment differs from frozen config")
    return {
        "path": os.path.abspath(path),
        "sha256": measured_sha256,
        "id": challenge_id,
        "nonce": nonce,
    }


def _live_environment_guard(app, config):
    expected = config.get("environment", {})
    live = {
        "fusion": str(getattr(app, "version", "")),
        "fusion_python": platform.python_version(),
        "os": platform.platform(),
    }
    for key, value in live.items():
        if value != expected.get(key):
            raise ReplayError(
                "environment_mismatch",
                "live {} environment does not match frozen config".format(key),
            )
    pid = os.getpid()
    created = _process_creation_time()
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ReplayError("environment_mismatch", "valid process ID is required")
    if not isinstance(created, str) or not created.strip():
        raise ReplayError("environment_mismatch", "Windows process creation time is required")
    try:
        datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayError("environment_mismatch", "Windows process creation time is invalid") from exc
    live["pid"] = pid
    live["process_creation_time"] = created
    return live


def _validate_box(name, value):
    if not isinstance(value, dict) or set(value) != {"min", "max"}:
        raise ReplayError("schema_invalid", "{}. must contain exactly min/max".format(name))
    minimum = value["min"]
    maximum = value["max"]
    if not isinstance(minimum, list) or not isinstance(maximum, list) or len(minimum) != 3 or len(maximum) != 3:
        raise ReplayError("schema_invalid", "{} bounds must be three-vectors".format(name))
    for low, high in zip(minimum, maximum):
        if (
            isinstance(low, bool)
            or isinstance(high, bool)
            or not isinstance(low, (int, float))
            or not isinstance(high, (int, float))
            or not math.isfinite(low)
            or not math.isfinite(high)
            or low >= high
        ):
            raise ReplayError("schema_invalid", "{} bounds must be finite increasing numbers".format(name))


def _is_frozen_formal_geometry(request, config):
    solids = request.get("solids", {})
    tolerance = Decimal(
        str(
            max(
                config["tolerances"]["surface_mm"],
                config["tolerances"]["parameter_length_mm"],
            )
        )
    )

    def box_matches(candidate, frozen):
        return all(
            abs(
                Decimal(str(candidate[bound][axis]))
                - Decimal(str(frozen[bound][axis]))
            )
            <= tolerance
            for bound in ("min", "max")
            for axis in range(3)
        )

    return (
        box_matches(solids["B"], config["solids"]["B"])
        and box_matches(solids["J"], config["solids"]["J"])
        and any(
            box_matches(solids["C"], config["solids"][name])
            for name in ("C_OS", "C_DE")
        )
        and request.get("order") in (["J", "C"], ["C", "J"])
    )


def _guard(app, request, project_root):
    """Validate all safety gates without creating a document or touching output."""
    if not isinstance(request, dict):
        raise ReplayError("schema_invalid", "qualification request must be an object")
    config, config_sha256 = _load_frozen_config(project_root)
    if config.get("execution_authorization") != "not_granted":
        raise ReplayError(
            "execution_authorization_violation",
            "frozen execution_authorization must remain not_granted",
        )
    if request.get("request_version") != REQUEST_VERSION or request.get("mode") != "qualification":
        raise ReplayError("qualification_only", "request mode must be qualification")
    forbidden_campaign_fields = {"rounds", "campaign", "campaign_uuid", "execution_matrix", "run_id"}
    if forbidden_campaign_fields.intersection(request):
        raise ReplayError("formal_campaign_forbidden", "qualification request contains formal campaign fields")
    qualification_id = request.get("qualification_id")
    if not isinstance(qualification_id, str) or not qualification_id.startswith("Q-"):
        raise ReplayError("schema_invalid", "qualification_id must start with Q-")
    if FORMAL_RUN_RE.fullmatch(qualification_id):
        raise ReplayError("formal_run_forbidden", "formal run identifiers are forbidden")
    serialized = json.dumps(request, ensure_ascii=False, sort_keys=True)
    if any(FORMAL_RUN_RE.search(token) for token in re.findall(r"[A-Za-z0-9_]+", serialized)):
        raise ReplayError("formal_run_forbidden", "formal run identifiers are forbidden")
    if not _safe_output_dir(request.get("output_dir")):
        raise ReplayError("unsafe_output_path", "output_dir must be an absolute qualification/temp path outside runs/gate6/precheck")
    if request.get("order") not in (["J", "C"], ["C", "J"]):
        raise ReplayError("schema_invalid", "order must be exactly J,C or C,J")
    solids = request.get("solids")
    if not isinstance(solids, dict) or set(solids) != {"B", "J", "C"}:
        raise ReplayError("schema_invalid", "solids must contain exactly B, J and C")
    for name in ("B", "J", "C"):
        _validate_box(name, solids[name])
    if _is_frozen_formal_geometry(request, config):
        raise ReplayError("formal_geometry_forbidden", "qualification cannot execute complete frozen formal geometry")
    challenge = _load_challenge(request, config)
    live_environment = _live_environment_guard(app, config)
    return config, config_sha256, challenge, live_environment


def _paths(output_dir):
    return {name: os.path.join(output_dir, name) for name in OUTPUT_NAMES}


def _assert_outputs_absent(paths):
    existing = [path for path in paths.values() if os.path.exists(path)]
    if existing:
        raise ReplayError("output_exists", "refusing to overwrite: {}".format(existing[0]))


def _internal(units, value):
    converted = units.convert(value, "mm", units.internalUnits)
    if converted is None:
        raise ReplayError("unit_conversion_failed", "Fusion unit conversion returned null")
    return converted


def _new_component(root, name):
    occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    if not occurrence or not occurrence.component:
        raise ReplayError("component_creation_failed", "Fusion did not create {}".format(name))
    occurrence.component.name = name
    return occurrence


def _unique_solid(component, code="invalid_result_solid"):
    if component.bRepBodies.count != 1:
        raise ReplayError(code, "{} must contain exactly one body".format(component.name))
    body = component.bRepBodies.item(0)
    if not getattr(body, "isValid", True) or not getattr(body, "isSolid", False):
        raise ReplayError(code, "{} body must be a valid solid".format(component.name))
    if body.lumps.count != 1:
        raise ReplayError(code, "{} solid must contain exactly one lump".format(component.name))
    return body


def _create_source_box(root, units, name, specification):
    occurrence = _new_component(root, name)
    component = occurrence.component
    minimum = [_internal(units, value) for value in specification["min"]]
    maximum = [_internal(units, value) for value in specification["max"]]
    plane_input = component.constructionPlanes.createInput()
    if not plane_input.setByOffset(
        component.xYConstructionPlane, adsk.core.ValueInput.createByReal(minimum[2])
    ):
        raise ReplayError("construction_plane_failed", "Fusion rejected {} z-offset plane".format(name))
    plane = component.constructionPlanes.add(plane_input)
    if not plane:
        raise ReplayError("construction_plane_failed", "Fusion returned a null {} plane".format(name))
    sketch = component.sketches.add(plane)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(minimum[0], minimum[1], 0),
        adsk.core.Point3D.create(maximum[0], maximum[1], 0),
    )
    if sketch.profiles.count != 1:
        raise ReplayError("profile_creation_failed", "{} rectangle must create one profile".format(name))
    height = maximum[2] - minimum[2]
    feature = component.features.extrudeFeatures.addSimple(
        sketch.profiles.item(0),
        adsk.core.ValueInput.createByReal(height),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not feature:
        raise ReplayError("extrude_failed", "Fusion returned a null {} extrusion".format(name))
    _unique_solid(component, "source_geometry_invalid")
    return occurrence


def _body_snapshot(component):
    body = _unique_solid(component, "source_geometry_invalid")
    bounds = body.boundingBox
    return {
        "count": component.bRepBodies.count,
        "token": getattr(body, "entityToken", None),
        "volume": getattr(body.physicalProperties, "volume", None),
        "bbox": (
            bounds.minPoint.x,
            bounds.minPoint.y,
            bounds.minPoint.z,
            bounds.maxPoint.x,
            bounds.maxPoint.y,
            bounds.maxPoint.z,
        ),
        "faces": body.faces.count,
    }


def _assert_sources_unchanged(occurrences, snapshots):
    for name, occurrence in occurrences.items():
        if _body_snapshot(occurrence.component) != snapshots[name]:
            raise ReplayError("tool_identity_failure", "{} changed during replay".format(name))


def _copy_body(source_occurrence, destination_occurrence):
    source = _unique_solid(source_occurrence.component, "source_geometry_invalid")
    copied = source.copyToComponent(destination_occurrence)
    if not copied or copied.parentComponent is not destination_occurrence.component:
        raise ReplayError("target_role_violation", "copied body is not owned by RESULT")
    return copied


def _combine(result_occurrence, source_occurrence, operation_name):
    result_component = result_occurrence.component
    target = _unique_solid(result_component)
    tool = _copy_body(source_occurrence, result_occurrence)
    if target is tool:
        raise ReplayError("target_role_violation", "target and tool cannot be the same body")
    tools = adsk.core.ObjectCollection.create()
    tools.add(tool)
    combine_input = result_component.features.combineFeatures.createInput(target, tools)
    if not combine_input:
        raise ReplayError("combine_input_failed", "Fusion returned a null combine input")
    operation = {
        "J": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "C": adsk.fusion.FeatureOperations.CutFeatureOperation,
    }[operation_name]
    combine_input.operation = operation
    combine_input.isKeepToolBodies = False
    feature = result_component.features.combineFeatures.add(combine_input)
    if not feature:
        raise ReplayError("combine_failed", "Fusion returned a null {} feature".format(operation_name))
    return _unique_solid(result_component)


def _export_step(export_manager, path, component):
    if os.path.exists(path):
        raise ReplayError("output_exists", "refusing to overwrite: {}".format(path))
    options = export_manager.createSTEPExportOptions(path, component)
    if options is None:
        raise ReplayError("step_export_options_failed", "Fusion returned null STEP export options")
    if export_manager.execute(options) is not True:
        raise ReplayError("step_export_failed", "Fusion STEP export returned false")
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise ReplayError("step_export_missing", "Fusion did not create a non-empty STEP file")


def _export_f3d(export_manager, path):
    if os.path.exists(path):
        raise ReplayError("output_exists", "refusing to overwrite: {}".format(path))
    options = export_manager.createFusionArchiveExportOptions(path)
    if options is None:
        raise ReplayError("f3d_export_options_failed", "Fusion returned null F3D export options")
    if export_manager.execute(options) is not True:
        raise ReplayError("f3d_export_failed", "Fusion F3D export returned false")
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise ReplayError("f3d_export_missing", "Fusion did not create a non-empty F3D file")


def _process_creation_time():
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        ticks = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
        seconds = ticks / 10000000.0 - 11644473600.0
        return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()
    except Exception:
        return None


def _scripts_metadata(app):
    manifest_path = os.path.splitext(__file__)[0] + ".manifest"
    result = [
        {
            "id": "Gate6QualificationReplay",
            "name": "Gate6QualificationReplay",
            "version": "0.1.0",
            "manifest_sha256": _sha256(manifest_path),
        }
    ]
    scripts = getattr(app, "scripts", None)
    if scripts is None:
        return result
    for index in range(scripts.count):
        script = scripts.item(index)
        item = {
            "id": str(getattr(script, "id", "")),
            "name": str(getattr(script, "name", "")),
            "version": str(getattr(script, "version", "")),
            "manifest_sha256": None,
        }
        manifest_path = getattr(script, "manifestPath", None)
        if manifest_path and os.path.isfile(manifest_path):
            item["manifest_sha256"] = _sha256(manifest_path)
        result.append(item)
    return sorted(result, key=lambda item: (item["id"], item["name"], item["version"]))


def _environment(app, document, request, config_sha256, challenge, live_environment):
    return {
        "fusion_version": live_environment["fusion"],
        "fusion_python_version": live_environment["fusion_python"],
        "platform": live_environment["os"],
        "pid": live_environment["pid"],
        "process_creation_time": live_environment["process_creation_time"],
        "document": {
            "name": str(getattr(document, "name", "")),
            "id": str(getattr(document, "id", "")),
        },
        "request_sha256": _canonical_request_sha256(request),
        "config_sha256": config_sha256,
        "script_sha256": _sha256(__file__),
        "external_preflight_record_sha256": challenge["sha256"],
        "challenge_id": challenge["id"],
        "challenge_nonce": challenge["nonce"],
        "fusion_scripts": _scripts_metadata(app),
    }


def _write_log(path, record):
    if os.path.exists(path):
        raise ReplayError("output_exists", "refusing to overwrite: {}".format(path))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def execute_qualification(app, request, project_root):
    """Execute one guarded synthetic qualification replay.

    Guarding and overwrite checks intentionally precede directory creation and
    ``documents.add``.  This function is callable with a fake Fusion protocol
    so its orchestration can be qualified without claiming a real Fusion run.
    """
    _, config_sha256, challenge, live_environment = _guard(
        app, request, os.path.abspath(project_root)
    )
    paths = _paths(os.path.abspath(request["output_dir"]))
    _assert_outputs_absent(paths)
    os.makedirs(request["output_dir"], exist_ok=True)

    document = None
    record = None
    primary = None
    secondary = []
    try:
        document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise ReplayError("fusion_design_unavailable", "new document is not a Fusion design")
        root = design.rootComponent
        units = design.unitsManager
        components = {
            "B_SOURCE": _create_source_box(root, units, "B_SOURCE", request["solids"]["B"]),
            "J_SOURCE": _create_source_box(root, units, "J_SOURCE", request["solids"]["J"]),
            "C_SOURCE": _create_source_box(root, units, "C_SOURCE", request["solids"]["C"]),
        }
        result = _new_component(root, "RESULT")
        _copy_body(components["B_SOURCE"], result)
        _unique_solid(result.component)
        snapshots = {
            name: _body_snapshot(occurrence.component)
            for name, occurrence in components.items()
        }

        _export_step(design.exportManager, paths["base.step"], components["B_SOURCE"].component)
        _export_step(design.exportManager, paths["join_tool.step"], components["J_SOURCE"].component)
        _export_step(design.exportManager, paths["cut_tool.step"], components["C_SOURCE"].component)

        source_by_modifier = {"J": components["J_SOURCE"], "C": components["C_SOURCE"]}
        _combine(result, source_by_modifier[request["order"][0]], request["order"][0])
        _assert_sources_unchanged(components, snapshots)
        _export_step(design.exportManager, paths["after_modifier_1.step"], result.component)
        _combine(result, source_by_modifier[request["order"][1]], request["order"][1])
        _assert_sources_unchanged(components, snapshots)
        _export_step(design.exportManager, paths["final.step"], result.component)
        _export_f3d(design.exportManager, paths["construction.f3d"])

        record = {
            "status": "success",
            "request_version": REQUEST_VERSION,
            "qualification_id": request["qualification_id"],
            "environment": _environment(
                app,
                document,
                request,
                config_sha256,
                challenge,
                live_environment,
            ),
            "artifacts": {name: {"sha256": _sha256(path), "bytes": os.path.getsize(path)} for name, path in paths.items() if name != "qualification_log.json"},
            "secondary_diagnostics": secondary,
        }
    except Exception as exc:
        primary = exc if isinstance(exc, ReplayError) else ReplayError("replay_failure", str(exc))
    finally:
        if document is not None:
            try:
                document.close(False)
            except Exception as exc:
                secondary.append({"code": "document_close_failed", "message": str(exc)})

    if primary is None and secondary:
        primary = ReplayError("document_close_failed", secondary[0]["message"], diagnostics=secondary)
    if primary is not None:
        primary.diagnostics.extend(item for item in secondary if item not in primary.diagnostics)
        failure_record = {
            "status": "failure",
            "qualification_id": request.get("qualification_id"),
            "primary_error": {"code": primary.code, "message": str(primary)},
            "secondary_diagnostics": primary.diagnostics,
        }
        try:
            _write_log(paths["qualification_log.json"], failure_record)
        except Exception as log_exc:
            primary.diagnostics.append({"code": "qualification_log_failed", "message": str(log_exc)})
        raise primary

    record["secondary_diagnostics"] = secondary
    _write_log(paths["qualification_log.json"], record)
    return record


def _request_path_from_context(context):
    path = None
    if isinstance(context, dict):
        path = context.get("qualification_request_path")
    if path is None:
        path = os.environ.get("GATE6_QUALIFICATION_REQUEST")
    if not path or not os.path.isabs(path):
        raise ReplayError("request_path_invalid", "an absolute qualification request path is required")
    return path


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        request_path = _request_path_from_context(context)
        with open(request_path, "r", encoding="utf-8") as handle:
            request = json.load(handle)
        record = execute_qualification(app, request, _project_root())
        ui.messageBox(
            "Gate 6 qualification succeeded.\n{}".format(record["qualification_id"])
        )
    except Exception as exc:
        code = exc.code if isinstance(exc, ReplayError) else "replay_failure"
        ui.messageBox(
            "Gate 6 qualification failed [{}]:\n{}\n\n{}".format(
                code, exc, traceback.format_exc()
            )
        )
