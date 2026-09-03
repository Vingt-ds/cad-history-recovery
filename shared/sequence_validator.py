"""Shared standard-library validator for CAD sequence schema v0.1."""

import math
import re


SCHEMA_VERSION = "cadseq-0.1"
SCHEMA_VERSION_V02 = "cadseq-0.2"
REPLAY_STATUSES = {"pending", "success", "failed", "unsupported"}
REPLAY_MODES = {"semantic", "absolute_fallback"}
REPLAY_MODES_V02 = {"automatic", "absolute_fallback"}
ORIGIN_PLANES = {
    "XY": (0.0, 0.0, 1.0),
    "XZ": (0.0, 1.0, 0.0),
    "YZ": (1.0, 0.0, 0.0),
}


class _ValidationFailure(Exception):
    def __init__(self, code, path, message):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self):
        return {"code": self.code, "path": self.path, "message": self.message}


def _fail(code, path, message):
    raise _ValidationFailure(code, path, message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _positive_number(value, path, code="invalid_number"):
    if not _is_number(value) or value <= 0:
        _fail(code, path, "value must be a finite number greater than zero")
    return float(value)


def _vector(value, size, path):
    if not isinstance(value, list) or len(value) != size or not all(_is_number(item) for item in value):
        _fail("invalid_vector", path, f"expected {size} finite numeric values")
    return tuple(float(item) for item in value)


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _norm(vector):
    return math.sqrt(_dot(vector, vector))


def _unit_vector(value, path, angular_tolerance):
    vector = _vector(value, 3, path)
    if abs(_norm(vector) - 1.0) > angular_tolerance:
        _fail("non_unit_vector", path, "vector must already have unit length")
    return vector


def _points_close(left, right, tolerance):
    return math.dist(left, right) <= tolerance


def _validate_header(data, schema_version):
    if not isinstance(data, dict):
        _fail("invalid_document", "$", "document must be a JSON object")
    if data.get("schema_version") != schema_version:
        _fail("invalid_schema_version", "$.schema_version", f"expected {schema_version}")
    if data.get("units") != "mm":
        _fail("invalid_units", "$.units", "units must be mm")
    if not isinstance(data.get("model_id"), str) or not data["model_id"]:
        _fail("invalid_model_id", "$.model_id", "model_id must be a non-empty string")
    tolerance = data.get("tolerance")
    if not isinstance(tolerance, dict):
        _fail("invalid_tolerance", "$.tolerance", "tolerance must be an object")
    length_tolerance = _positive_number(
        tolerance.get("length_mm"), "$.tolerance.length_mm", "invalid_tolerance"
    )
    angular_tolerance = _positive_number(
        tolerance.get("angular_rad"), "$.tolerance.angular_rad", "invalid_tolerance"
    )
    if data.get("replay_status") not in REPLAY_STATUSES:
        _fail("invalid_replay_status", "$.replay_status", "unsupported replay status")
    replay_modes = REPLAY_MODES_V02 if schema_version == SCHEMA_VERSION_V02 else REPLAY_MODES
    if data.get("replay_mode") not in replay_modes:
        _fail("invalid_replay_mode", "$.replay_mode", "unsupported replay mode")
    if not isinstance(data.get("corrections"), list):
        _fail("invalid_corrections", "$.corrections", "corrections must be a list")
    if not isinstance(data.get("operations"), list) or not data["operations"]:
        _fail("invalid_operations", "$.operations", "operations must be a non-empty list")
    return length_tolerance, angular_tolerance


def _validate_line_loop(primitives, path, length_tolerance):
    points = []
    for index, primitive in enumerate(primitives):
        primitive_path = f"{path}.primitives[{index}]"
        start = _vector(primitive.get("start"), 2, f"{primitive_path}.start")
        end = _vector(primitive.get("end"), 2, f"{primitive_path}.end")
        if _points_close(start, end, length_tolerance):
            _fail("degenerate_line", primitive_path, "line endpoints must differ")
        points.append((start, end))
    for index, (_, end) in enumerate(points):
        next_start = points[(index + 1) % len(points)][0]
        if not _points_close(end, next_start, length_tolerance):
            _fail("open_loop", path, "line endpoints do not form a closed ordered chain")


def _validate_loop(loop, path, length_tolerance, primitive_ids):
    if not isinstance(loop, dict):
        _fail("invalid_loop", path, "loop must be an object")
    loop_id = loop.get("loop_id")
    if not isinstance(loop_id, str) or not loop_id:
        _fail("invalid_loop_id", f"{path}.loop_id", "loop_id must be a non-empty string")
    if loop.get("loop_type") not in {"outer", "inner"}:
        _fail("invalid_loop_type", f"{path}.loop_type", "loop_type must be outer or inner")
    primitives = loop.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        _fail("invalid_primitives", f"{path}.primitives", "primitives must be a non-empty list")
    primitive_types = []
    for index, primitive in enumerate(primitives):
        primitive_path = f"{path}.primitives[{index}]"
        if not isinstance(primitive, dict):
            _fail("invalid_primitive", primitive_path, "primitive must be an object")
        primitive_id = primitive.get("primitive_id")
        if not isinstance(primitive_id, str) or not primitive_id:
            _fail("invalid_primitive_id", f"{primitive_path}.primitive_id", "invalid primitive_id")
        if primitive_id in primitive_ids:
            _fail("duplicate_primitive_id", f"{primitive_path}.primitive_id", "primitive_id is duplicated")
        primitive_ids.add(primitive_id)
        primitive_types.append(primitive.get("type"))
    if all(primitive_type == "line" for primitive_type in primitive_types):
        _validate_line_loop(primitives, path, length_tolerance)
    elif primitive_types == ["circle"]:
        _vector(primitives[0].get("center"), 2, f"{path}.primitives[0].center")
        _positive_number(
            primitives[0].get("radius_mm"),
            f"{path}.primitives[0].radius_mm",
            "invalid_radius",
        )
    else:
        _fail(
            "unsupported_primitive_configuration",
            f"{path}.primitives",
            "v0.1 loops must be all lines or one complete circle",
        )
    return loop_id, loop["loop_type"]


def _find_correction(data, correction_id, operation_id):
    for correction in data["corrections"]:
        if (
            isinstance(correction, dict)
            and correction.get("correction_id") == correction_id
            and correction.get("operation_id") == operation_id
        ):
            return correction
    return None


def _validate_correction_record(correction):
    correction_number = correction.get("correction_number")
    if (
        not isinstance(correction_number, int)
        or isinstance(correction_number, bool)
        or correction_number <= 0
        or not isinstance(correction.get("reason"), str)
        or not correction["reason"]
        or not isinstance(correction.get("before"), dict)
        or not isinstance(correction.get("after"), dict)
    ):
        _fail(
            "invalid_correction_record",
            "$.corrections",
            "fallback correction requires number, reason, before, and after audit fields",
        )


def _validate_semantic_reference(
    data,
    operation,
    reference,
    path,
    frame,
    seen,
    dependencies,
    length_tolerance,
    angular_tolerance,
    schema_version,
):
    if not isinstance(reference, dict):
        _fail("invalid_semantic_reference", path, "semantic_reference must be an object")
    reference_type = reference.get("type")
    sketch_plane = operation["sketch_plane"]
    frame_source = sketch_plane.get("frame_source")
    if reference_type == "origin_plane":
        if schema_version == SCHEMA_VERSION_V02:
            if frame_source != "origin_named":
                _fail(
                    "frame_source_reference_mismatch",
                    f"{path.rsplit('.', 1)[0]}.frame_source",
                    "origin_plane requires frame_source origin_named",
                )
            if data.get("replay_mode") != "automatic":
                _fail(
                    "frame_source_replay_mode_mismatch",
                    "$.replay_mode",
                    "origin_named requires automatic replay mode",
                )
        role = reference.get("role")
        if role not in ORIGIN_PLANES:
            _fail("invalid_origin_plane", f"{path}.role", "role must be XY, XZ, or YZ")
        canonical_normal = ORIGIN_PLANES[role]
        if abs(abs(_dot(frame["normal"], canonical_normal)) - 1.0) > angular_tolerance:
            _fail("frame_plane_mismatch", f"{path}.role", "frame normal does not match origin plane")
        if abs(_dot(frame["origin"], canonical_normal)) > length_tolerance:
            _fail(
                "origin_not_on_reference_plane",
                f"{path.rsplit('.', 1)[0]}.frame.origin",
                "frame origin is not on the named origin plane",
            )
    elif reference_type == "operation_cap":
        if schema_version == SCHEMA_VERSION_V02 and "frame_source" in sketch_plane:
            _fail(
                "operation_cap_frame_source_forbidden",
                f"{path.rsplit('.', 1)[0]}.frame_source",
                "operation_cap is a semantic reference and has no frame_source",
            )
        reference_id = reference.get("operation_id")
        referenced = seen.get(reference_id)
        if (
            referenced is None
            or referenced.get("operation_type") != "extrude"
            or referenced.get("boolean_type") != "new"
            or referenced.get("extent", {}).get("type") != "distance"
        ):
            _fail(
                "invalid_operation_cap_reference",
                f"{path}.operation_id",
                "operation_cap must reference an earlier new-distance Extrude",
            )
        if reference_id not in dependencies:
            _fail(
                "operation_cap_dependency_missing",
                f"{path}.operation_id",
                "referenced Extrude must be a Sketch dependency",
            )
        role = reference.get("role")
        if role not in {"positive_end_cap", "negative_end_cap"}:
            _fail("invalid_operation_cap_role", f"{path}.role", "invalid cap role")
        offset = reference.get("offset_mm")
        if not _is_number(offset):
            _fail("invalid_operation_cap_offset", f"{path}.offset_mm", "offset must be finite")
        if abs(offset) > length_tolerance:
            _fail(
                "unsupported_operation_cap_offset",
                f"{path}.offset_mm",
                "v0.1 supports only zero-offset operation caps",
            )

        parent_direction = tuple(float(value) for value in referenced["direction"])
        if abs(abs(_dot(frame["normal"], parent_direction)) - 1.0) > angular_tolerance:
            _fail(
                "operation_cap_frame_mismatch",
                f"{path.rsplit('.', 1)[0]}.frame.normal",
                "operation-cap frame normal must follow the parent Extrude direction",
            )
        parent_sketch_id = referenced["profile"]["sketch_id"]
        parent_sketch = seen[parent_sketch_id]
        parent_origin = tuple(
            float(value) for value in parent_sketch["sketch_plane"]["frame"]["origin"]
        )
        distance = float(referenced["extent"]["distance_mm"])
        if role == "positive_end_cap":
            cap_origin = tuple(
                origin + direction * distance
                for origin, direction in zip(parent_origin, parent_direction)
            )
        else:
            cap_origin = parent_origin
        cap_delta = tuple(
            actual - expected for actual, expected in zip(frame["origin"], cap_origin)
        )
        if abs(_dot(cap_delta, parent_direction)) > length_tolerance:
            _fail(
                "origin_not_on_reference_plane",
                f"{path.rsplit('.', 1)[0]}.frame.origin",
                "frame origin is not on the referenced operation cap",
            )
    elif reference_type == "absolute_frame":
        if schema_version == SCHEMA_VERSION_V02:
            if frame_source == "inferred_brep":
                if data.get("replay_mode") != "automatic":
                    _fail(
                        "frame_source_replay_mode_mismatch",
                        "$.replay_mode",
                        "inferred_brep requires automatic replay mode",
                    )
                provenance = sketch_plane.get("frame_provenance")
                if (
                    not isinstance(provenance, dict)
                    or not isinstance(provenance.get("source_step_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", provenance["source_step_sha256"]) is None
                    or not isinstance(provenance.get("base_face_id"), str)
                    or not provenance["base_face_id"]
                ):
                    _fail(
                        "invalid_frame_provenance",
                        f"{path.rsplit('.', 1)[0]}.frame_provenance",
                        "inferred_brep requires STEP SHA-256 and base face ID",
                    )
                outward = _unit_vector(
                    provenance.get("source_face_outward_normal"),
                    f"{path.rsplit('.', 1)[0]}.frame_provenance.source_face_outward_normal",
                    angular_tolerance,
                )
                if abs(_dot(outward, frame["normal"]) + 1.0) > angular_tolerance:
                    _fail(
                        "invalid_frame_provenance",
                        f"{path.rsplit('.', 1)[0]}.frame_provenance.source_face_outward_normal",
                        "base-face outward normal must oppose inferred extrusion frame normal",
                    )
                if "correction_id" in reference:
                    _fail(
                        "frame_source_reference_mismatch",
                        f"{path}.correction_id",
                        "automatic inferred frame cannot cite a manual correction",
                    )
                return
            if frame_source != "manual_correction":
                _fail(
                    "frame_source_reference_mismatch",
                    f"{path.rsplit('.', 1)[0]}.frame_source",
                    "absolute_frame requires inferred_brep or manual_correction",
                )
        correction_id = reference.get("correction_id")
        if (
            data.get("replay_mode") != "absolute_fallback"
            or not isinstance(correction_id, str)
        ):
            _fail(
                "absolute_fallback_not_authorized",
                path,
                "absolute frame requires explicit replay mode and matching correction",
            )
        correction = _find_correction(data, correction_id, operation["operation_id"])
        if correction is None:
            _fail(
                "absolute_fallback_not_authorized",
                path,
                "absolute frame requires explicit replay mode and matching correction",
            )
        _validate_correction_record(correction)
    else:
        _fail("invalid_semantic_reference", f"{path}.type", "unsupported reference type")


def _validate_sketch(
    data,
    operation,
    path,
    seen,
    dependencies,
    length_tolerance,
    angular_tolerance,
    schema_version,
):
    sketch_plane = operation.get("sketch_plane")
    if not isinstance(sketch_plane, dict):
        _fail("invalid_sketch_plane", f"{path}.sketch_plane", "sketch_plane must be an object")
    frame_data = sketch_plane.get("frame")
    if not isinstance(frame_data, dict):
        _fail("invalid_frame", f"{path}.sketch_plane.frame", "frame must be an object")
    frame = {
        "origin": _vector(frame_data.get("origin"), 3, f"{path}.sketch_plane.frame.origin"),
        "normal": _unit_vector(
            frame_data.get("normal"), f"{path}.sketch_plane.frame.normal", angular_tolerance
        ),
        "x_axis": _unit_vector(
            frame_data.get("x_axis"), f"{path}.sketch_plane.frame.x_axis", angular_tolerance
        ),
    }
    if abs(_dot(frame["normal"], frame["x_axis"])) > angular_tolerance:
        _fail(
            "frame_not_orthogonal",
            f"{path}.sketch_plane.frame",
            "normal and x_axis must be orthogonal",
        )
    _validate_semantic_reference(
        data,
        operation,
        sketch_plane.get("semantic_reference"),
        f"{path}.sketch_plane.semantic_reference",
        frame,
        seen,
        dependencies,
        length_tolerance,
        angular_tolerance,
        schema_version,
    )
    loops = operation.get("loops")
    if not isinstance(loops, list) or not loops:
        _fail("invalid_loops", f"{path}.loops", "loops must be a non-empty list")
    loop_map = {}
    primitive_ids = set()
    for index, loop in enumerate(loops):
        loop_id, loop_type = _validate_loop(
            loop, f"{path}.loops[{index}]", length_tolerance, primitive_ids
        )
        if loop_id in loop_map:
            _fail("duplicate_loop_id", f"{path}.loops[{index}].loop_id", "loop_id is duplicated")
        loop_map[loop_id] = loop_type
    return {
        "normal": frame["normal"],
        "loops": loop_map,
        "frame_source": sketch_plane.get("frame_source"),
    }


def _validate_extrude(
    operation,
    path,
    sketches,
    dependencies,
    angular_tolerance,
    new_body_seen,
    schema_version,
):
    profile = operation.get("profile")
    if not isinstance(profile, dict):
        _fail("invalid_profile", f"{path}.profile", "profile must be an object")
    sketch_id = profile.get("sketch_id")
    if sketch_id not in sketches:
        _fail("unknown_sketch_reference", f"{path}.profile.sketch_id", "profile Sketch does not exist")
    if sketch_id not in dependencies:
        _fail(
            "missing_profile_dependency",
            f"{path}.dependencies",
            "Extrude dependencies must include the profile Sketch",
        )
    sketch = sketches[sketch_id]
    outer_loop_id = profile.get("outer_loop_id")
    inner_loop_ids = profile.get("inner_loop_ids")
    if outer_loop_id not in sketch["loops"]:
        _fail(
            "unknown_loop_reference",
            f"{path}.profile.outer_loop_id",
            "outer loop does not exist in the profile Sketch",
        )
    if sketch["loops"][outer_loop_id] != "outer":
        _fail(
            "outer_loop_type_mismatch",
            f"{path}.profile.outer_loop_id",
            "outer_loop_id must reference a loop declared as outer",
        )
    if not isinstance(inner_loop_ids, list) or not all(isinstance(item, str) for item in inner_loop_ids):
        _fail("invalid_inner_loops", f"{path}.profile.inner_loop_ids", "inner_loop_ids must be strings")
    if outer_loop_id in inner_loop_ids or len(set(inner_loop_ids)) != len(inner_loop_ids):
        _fail(
            "duplicate_profile_loop",
            f"{path}.profile.inner_loop_ids",
            "outer and inner loop references must be distinct",
        )
    for index, loop_id in enumerate(inner_loop_ids):
        if loop_id not in sketch["loops"]:
            _fail(
                "unknown_loop_reference",
                f"{path}.profile.inner_loop_ids[{index}]",
                "inner loop does not exist in the profile Sketch",
            )
        if sketch["loops"][loop_id] != "inner":
            _fail(
                "inner_loop_type_mismatch",
                f"{path}.profile.inner_loop_ids[{index}]",
                "inner_loop_ids must reference loops declared as inner",
            )
    direction = _unit_vector(operation.get("direction"), f"{path}.direction", angular_tolerance)
    if abs(abs(_dot(direction, sketch["normal"])) - 1.0) > angular_tolerance:
        _fail(
            "direction_not_parallel",
            f"{path}.direction",
            "Extrude direction must be parallel or antiparallel to Sketch normal",
        )
    if (
        schema_version == SCHEMA_VERSION_V02
        and sketch["frame_source"] == "inferred_brep"
        and _dot(direction, sketch["normal"]) < 1.0 - angular_tolerance
    ):
        _fail(
            "inferred_direction_mismatch",
            f"{path}.direction",
            "inferred_brep Extrude direction must equal the canonical frame normal",
        )
    boolean_type = operation.get("boolean_type")
    if boolean_type not in {"new", "cut"}:
        _fail(
            "unsupported_boolean_type",
            f"{path}.boolean_type",
            "v0.1 supports only new and cut",
        )
    extent = operation.get("extent")
    if not isinstance(extent, dict):
        _fail("invalid_extent", f"{path}.extent", "extent must be an object")
    extent_type = extent.get("type")
    if boolean_type == "new" and extent_type != "distance":
        _fail("invalid_boolean_extent", f"{path}.extent.type", "new requires distance")
    if boolean_type == "cut" and extent_type != "through_all":
        _fail("invalid_boolean_extent", f"{path}.extent.type", "cut requires through_all")
    if extent_type == "distance":
        _positive_number(extent.get("distance_mm"), f"{path}.extent.distance_mm", "invalid_distance")
    if boolean_type == "cut" and not new_body_seen:
        _fail("cut_without_body", path, "cut requires an earlier new body")
    return boolean_type == "new" or new_body_seen


def _validate_document(data, schema_version):
    length_tolerance, angular_tolerance = _validate_header(data, schema_version)
    seen = {}
    sketches = {}
    new_body_seen = False
    for index, operation in enumerate(data["operations"]):
        path = f"$.operations[{index}]"
        if not isinstance(operation, dict):
            _fail("invalid_operation", path, "operation must be an object")
        operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            _fail("invalid_operation_id", f"{path}.operation_id", "invalid operation_id")
        if operation_id in seen:
            _fail("duplicate_operation_id", f"{path}.operation_id", "operation_id is duplicated")
        dependencies = operation.get("dependencies")
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            _fail("invalid_dependencies", f"{path}.dependencies", "dependencies must be strings")
        if len(set(dependencies)) != len(dependencies):
            _fail("duplicate_dependency", f"{path}.dependencies", "dependencies must be unique")
        for dependency in dependencies:
            if dependency not in seen:
                _fail(
                    "dependency_not_earlier",
                    f"{path}.dependencies",
                    "dependencies may reference only earlier operations",
                )
        if operation.get("replay_status") not in REPLAY_STATUSES:
            _fail("invalid_replay_status", f"{path}.replay_status", "unsupported replay status")
        operation_type = operation.get("operation_type")
        if operation_type == "sketch":
            sketches[operation_id] = _validate_sketch(
                data,
                operation,
                path,
                seen,
                dependencies,
                length_tolerance,
                angular_tolerance,
                schema_version,
            )
        elif operation_type == "extrude":
            new_body_seen = _validate_extrude(
                operation,
                path,
                sketches,
                dependencies,
                angular_tolerance,
                new_body_seen,
                schema_version,
            )
        else:
            _fail("unsupported_operation_type", f"{path}.operation_type", "expected sketch or extrude")
        seen[operation_id] = operation


def _validate(data):
    schema_version = data.get("schema_version") if isinstance(data, dict) else None
    if schema_version not in {SCHEMA_VERSION, SCHEMA_VERSION_V02}:
        schema_version = SCHEMA_VERSION
    _validate_document(data, schema_version)


def validate_sequence(data):
    """Return a structured static-validation result without mutating input data."""

    try:
        _validate(data)
    except _ValidationFailure as error:
        return {"valid": False, "errors": [error.as_dict()]}
    return {"valid": True, "errors": []}
