"""Replay one Gate 1 known sequence in a fresh Fusion document."""

import hashlib
import json
import math
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


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_shared(project_root):
    shared_path = os.path.join(project_root, "shared")
    if shared_path not in sys.path:
        sys.path.insert(0, shared_path)
    from frame_math import parallel_alignment_error, world_point
    from sequence_validator import validate_sequence

    return validate_sequence, world_point, parallel_alignment_error


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mm_to_internal(units, value):
    return units.convert(float(value), "mm", units.internalUnits)


def _internal_to_mm(units, value):
    return units.convert(float(value), units.internalUnits, "mm")


def _point_mm_to_model(units, coordinates):
    return adsk.core.Point3D.create(
        _mm_to_internal(units, coordinates[0]),
        _mm_to_internal(units, coordinates[1]),
        _mm_to_internal(units, coordinates[2]),
    )


def _distance_mm(units, left, right):
    distance = math.sqrt(
        (left.x - right.x) ** 2
        + (left.y - right.y) ** 2
        + (left.z - right.z) ** 2
    )
    return _internal_to_mm(units, distance)


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _unit(vector):
    length = math.sqrt(_dot(vector, vector))
    if length == 0:
        raise ReplayError("invalid_fusion_plane", "Fusion returned a zero-length plane vector")
    return tuple(value / length for value in vector)


def _actual_sketch_normal(sketch):
    origin = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
    point_x = sketch.sketchToModelSpace(adsk.core.Point3D.create(1, 0, 0))
    point_y = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 1, 0))
    axis_x = (point_x.x - origin.x, point_x.y - origin.y, point_x.z - origin.z)
    axis_y = (point_y.x - origin.x, point_y.y - origin.y, point_y.z - origin.z)
    return _unit(
        (
            axis_x[1] * axis_y[2] - axis_x[2] * axis_y[1],
            axis_x[2] * axis_y[0] - axis_x[0] * axis_y[2],
            axis_x[0] * axis_y[1] - axis_x[1] * axis_y[0],
        )
    )


def _origin_plane(component, role):
    if role == "XY":
        return component.xYConstructionPlane
    if role == "XZ":
        return component.xZConstructionPlane
    if role == "YZ":
        return component.yZConstructionPlane
    raise ReplayError("unsupported_reference_plane", "unsupported origin plane: {}".format(role))


def _rotated_plane(component, frame, angular_tolerance):
    normal = frame["normal"]
    root = math.sqrt(0.5)
    rx30 = (0.0, -0.5, math.sqrt(3.0) / 2.0)
    ry45 = (root, 0.0, root)
    if max(abs(a - b) for a, b in zip(normal, rx30)) <= angular_tolerance:
        axis = component.xConstructionAxis
        angle = math.radians(30.0)
    elif max(abs(a - b) for a, b in zip(normal, ry45)) <= angular_tolerance:
        axis = component.yConstructionAxis
        angle = math.radians(45.0)
    else:
        raise ReplayError(
            "unsupported_absolute_frame",
            "Gate 1 supports only the fixed RX30 and RY45 absolute frames",
        )
    plane_input = component.constructionPlanes.createInput()
    if not plane_input.setByAngle(
        axis,
        adsk.core.ValueInput.createByReal(angle),
        component.xYConstructionPlane,
    ):
        raise ReplayError("construction_plane_failed", "setByAngle returned false")
    return component.constructionPlanes.add(plane_input)


def _resolve_operation_cap(reference, extrude_features):
    feature = extrude_features.get(reference["operation_id"])
    if feature is None:
        raise ReplayError(
            "semantic_reference_failed",
            "parent Extrude is unavailable: {}".format(reference["operation_id"]),
        )
    if reference["role"] == "positive_end_cap":
        faces = feature.endFaces
    else:
        faces = feature.startFaces
    if faces is None or faces.count != 1:
        count = 0 if faces is None else faces.count
        raise ReplayError(
            "semantic_reference_failed",
            "{} resolved to {} cap faces; expected 1".format(reference["role"], count),
        )
    face = faces.item(0)
    if face is None:
        raise ReplayError("semantic_reference_failed", "Fusion returned a null cap face")
    return face


def _sketch_plane(component, operation, angular_tolerance, extrude_features):
    plane = operation["sketch_plane"]
    reference = plane["semantic_reference"]
    if reference["type"] == "origin_plane":
        return _origin_plane(component, reference["role"])
    if reference["type"] == "absolute_frame":
        return _rotated_plane(component, plane["frame"], angular_tolerance)
    if reference["type"] == "operation_cap":
        return _resolve_operation_cap(reference, extrude_features)
    raise ReplayError("semantic_reference_failed", "unsupported semantic reference")


def _to_sketch_point(sketch, units, frame, point_2d, world_point):
    world_mm = world_point(frame, point_2d)
    model_point = _point_mm_to_model(units, world_mm)
    sketch_point = sketch.modelToSketchSpace(model_point)
    plane_offset_mm = abs(_internal_to_mm(units, sketch_point.z))
    planar_point = adsk.core.Point3D.create(sketch_point.x, sketch_point.y, 0)
    restored = sketch.sketchToModelSpace(planar_point)
    return planar_point, max(plane_offset_mm, _distance_mm(units, model_point, restored))


def _draw_sketch(sketch, operation, units, world_point):
    frame = operation["sketch_plane"]["frame"]
    max_error = 0.0
    for loop in operation["loops"]:
        for primitive in loop["primitives"]:
            if primitive["type"] == "line":
                start, start_error = _to_sketch_point(
                    sketch, units, frame, primitive["start"], world_point
                )
                end, end_error = _to_sketch_point(
                    sketch, units, frame, primitive["end"], world_point
                )
                sketch.sketchCurves.sketchLines.addByTwoPoints(start, end)
                max_error = max(max_error, start_error, end_error)
            elif primitive["type"] == "circle":
                center, center_error = _to_sketch_point(
                    sketch, units, frame, primitive["center"], world_point
                )
                radius = _mm_to_internal(units, primitive["radius_mm"])
                sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius)
                max_error = max(max_error, center_error)
            else:
                raise ReplayError(
                    "unsupported_primitive_type",
                    "unsupported primitive: {}".format(primitive["type"]),
                )
    return max_error


def _select_profile(profiles, expected_curve_count):
    matches = []
    for index in range(profiles.count):
        profile = profiles.item(index)
        loops = profile.profileLoops
        if loops.count != 1:
            continue
        outer = loops.item(0)
        if outer.isOuter and outer.profileCurves.count == expected_curve_count:
            matches.append(profile)
    if len(matches) != 1:
        raise ReplayError(
            "profile_resolution_failed",
            "declared loop matched {} Fusion profiles; expected 1".format(len(matches)),
        )
    return matches[0]


def _run_sequence(sequence, component, design, world_point, parallel_alignment_error):
    units = design.unitsManager
    sketches = {}
    extrude_features = {}
    operation_records = []
    world_frame_max_error_mm = 0.0
    length_tolerance = float(sequence["tolerance"]["length_mm"])
    angular_tolerance = float(sequence["tolerance"]["angular_rad"])

    for operation in sequence["operations"]:
        operation_id = operation["operation_id"]
        operation_type = operation["operation_type"]
        if operation_type == "sketch":
            plane = _sketch_plane(
                component, operation, angular_tolerance, extrude_features
            )
            sketch = component.sketches.add(plane)
            declared_normal = tuple(
                float(value) for value in operation["sketch_plane"]["frame"]["normal"]
            )
            actual_normal = _actual_sketch_normal(sketch)
            normal_error = parallel_alignment_error(declared_normal, actual_normal)
            if normal_error > angular_tolerance:
                raise ReplayError(
                    "plane_normal_mismatch",
                    "{} plane angular error {} rad exceeds {} rad".format(
                        operation_id, normal_error, angular_tolerance
                    ),
                )
            error = _draw_sketch(sketch, operation, units, world_point)
            world_frame_max_error_mm = max(world_frame_max_error_mm, error)
            if error > length_tolerance:
                raise ReplayError(
                    "world_frame_error_exceeded",
                    "{} frame round-trip error {} mm exceeds {} mm".format(
                        operation_id, error, length_tolerance
                    ),
                )
            if sketch.profiles.count < 1:
                raise ReplayError(
                    "profile_count_mismatch",
                    "{} did not produce a closed profile".format(operation_id),
                )
            sketches[operation_id] = {"sketch": sketch, "operation": operation}
        elif operation_type == "extrude":
            sketch_record = sketches[operation["profile"]["sketch_id"]]
            sketch = sketch_record["sketch"]
            if operation["profile"]["inner_loop_ids"]:
                raise ReplayError(
                    "unsupported_operation_combination",
                    "Gate 1 replay requires normalized outer-loop operations",
                )
            outer_loop_id = operation["profile"]["outer_loop_id"]
            outer_loop = next(
                loop
                for loop in sketch_record["operation"]["loops"]
                if loop["loop_id"] == outer_loop_id
            )
            profile = _select_profile(
                sketch.profiles, expected_curve_count=len(outer_loop["primitives"])
            )
            actual_normal = _actual_sketch_normal(sketch)
            direction = tuple(float(value) for value in operation["direction"])
            direction_is_positive = _dot(actual_normal, direction) >= 0
            boolean_type = operation["boolean_type"]
            extent_type = operation["extent"]["type"]
            extrudes = component.features.extrudeFeatures
            operation_record = {"operation_id": operation_id, "status": "success"}
            if boolean_type == "new" and extent_type == "distance":
                signed_distance = float(operation["extent"]["distance_mm"])
                if not direction_is_positive:
                    signed_distance = -signed_distance
                feature = extrudes.addSimple(
                    profile,
                    adsk.core.ValueInput.createByReal(
                        _mm_to_internal(units, signed_distance)
                    ),
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                )
                if feature is None:
                    raise ReplayError("new_extrude_failed", "Fusion returned a null feature")
                extrude_features[operation_id] = feature
            elif boolean_type == "cut" and extent_type == "through_all":
                if component.bRepBodies.count != 1:
                    raise ReplayError(
                        "body_count_mismatch", "Cut requires exactly one existing body"
                    )
                volume_before = component.bRepBodies.item(0).volume
                cut_input = extrudes.createInput(
                    profile,
                    adsk.fusion.FeatureOperations.CutFeatureOperation,
                )
                through_all = adsk.fusion.ThroughAllExtentDefinition.create()
                extent_direction = (
                    adsk.fusion.ExtentDirections.PositiveExtentDirection
                    if direction_is_positive
                    else adsk.fusion.ExtentDirections.NegativeExtentDirection
                )
                if not cut_input.setOneSideExtent(through_all, extent_direction):
                    raise ReplayError(
                        "through_all_extent_failed", "Fusion rejected through-all extent"
                    )
                cut_feature = extrudes.add(cut_input)
                if cut_feature is None or component.bRepBodies.count != 1:
                    raise ReplayError("cut_feature_failed", "Fusion Cut did not return one body")
                volume_after = component.bRepBodies.item(0).volume
                if volume_after >= volume_before:
                    raise ReplayError(
                        "boolean_no_intersection", "Cut did not reduce body volume"
                    )
                operation_record["volume_before_cm3"] = volume_before
                operation_record["volume_after_cm3"] = volume_after
            else:
                raise ReplayError(
                    "unsupported_operation_combination",
                    "unsupported {} + {}".format(boolean_type, extent_type),
                )
        else:
            raise ReplayError(
                "unsupported_operation_type",
                "unsupported operation type: {}".format(operation_type),
            )
        if operation_type == "sketch":
            operation_record = {
                "operation_id": operation_id,
                "status": "success",
                "profile_count": sketch.profiles.count,
            }
        operation_records.append(operation_record)

    if component.bRepBodies.count != 1:
        raise ReplayError(
            "body_count_mismatch",
            "expected one body, found {}".format(component.bRepBodies.count),
        )
    return operation_records, world_frame_max_error_mm


def _paths(project_root, request):
    if request.get("request_version") != "gate1-replay-0.1":
        raise ReplayError("invalid_request_version", "unsupported replay request version")
    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ReplayError("invalid_run_id", "run_id must contain only letters, digits, _ or -")
    relative_sequence = request.get("sequence_path")
    if not isinstance(relative_sequence, str):
        raise ReplayError("invalid_sequence_path", "sequence_path must be a string")
    sequence_path = os.path.abspath(os.path.join(project_root, relative_sequence))
    if os.path.commonpath((project_root, sequence_path)) != project_root:
        raise ReplayError("invalid_sequence_path", "sequence_path leaves the project directory")
    output_dir = os.path.join(project_root, "replay_outputs")
    return {
        "run_id": run_id,
        "sequence": sequence_path,
        "output_dir": output_dir,
        "f3d": os.path.join(output_dir, run_id + ".f3d"),
        "step": os.path.join(output_dir, run_id + ".step"),
        "log": os.path.join(output_dir, run_id + ".json"),
    }


def _assert_outputs_absent(paths):
    existing = [paths[key] for key in ("f3d", "step", "log") if os.path.exists(paths[key])]
    if existing:
        raise ReplayError(
            "output_exists",
            "refusing to overwrite existing output: {}".format(", ".join(existing)),
        )


def _write_log(path, record):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    project_root = _project_root()
    request_path = os.path.join(project_root, "config", "gate1_replay_request.json")
    paths = None

    try:
        validate_sequence, world_point, parallel_alignment_error = _load_shared(project_root)
        request = _load_json(request_path)
        paths = _paths(project_root, request)
        if not os.path.isfile(paths["sequence"]):
            raise ReplayError("sequence_not_found", paths["sequence"])
        _assert_outputs_absent(paths)
        sequence = _load_json(paths["sequence"])
        validation = validate_sequence(sequence)
        if not validation["valid"]:
            raise ReplayError(
                "sequence_validation_failed",
                json.dumps(validation["errors"], ensure_ascii=False),
            )

        os.makedirs(paths["output_dir"], exist_ok=True)
        document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise ReplayError("fusion_design_unavailable", "new document is not a Fusion design")
        component = design.rootComponent
        operation_records, world_frame_max_error_mm = _run_sequence(
            sequence, component, design, world_point, parallel_alignment_error
        )

        archive_options = design.exportManager.createFusionArchiveExportOptions(paths["f3d"])
        if not design.exportManager.execute(archive_options):
            raise ReplayError("f3d_export_failed", "Fusion archive export returned false")
        step_options = design.exportManager.createSTEPExportOptions(paths["step"], component)
        if not design.exportManager.execute(step_options):
            raise ReplayError("step_export_failed", "STEP export returned false")

        body = component.bRepBodies.item(0)
        record = {
            "status": "success",
            "run_id": paths["run_id"],
            "model_id": sequence["model_id"],
            "replay_mode": sequence["replay_mode"],
            "request_sha256": _sha256(request_path),
            "sequence_sha256": _sha256(paths["sequence"]),
            "fusion_version": app.version,
            "python_version": platform.python_version(),
            "body_count": component.bRepBodies.count,
            "face_count": body.faces.count,
            "world_frame_max_error_mm": world_frame_max_error_mm,
            "operations": operation_records,
            "outputs": {"f3d": paths["f3d"], "step": paths["step"]},
        }
        _write_log(paths["log"], record)
        ui.messageBox("Gate 1 replay succeeded: {}".format(paths["run_id"]))
    except Exception as exc:
        code = exc.code if isinstance(exc, ReplayError) else "fusion_exception"
        failure = {
            "status": "failure",
            "error_code": code,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "fusion_version": getattr(app, "version", "unknown"),
            "python_version": sys.version,
        }
        if paths and not os.path.exists(paths["log"]):
            os.makedirs(paths["output_dir"], exist_ok=True)
            _write_log(paths["log"], failure)
        ui.messageBox("Gate 1 replay failed [{}]:\n{}".format(code, exc))
