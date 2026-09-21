"""Read-only Gate 6 Fusion environment probe. It never opens a document."""
import datetime
import hashlib
import json
import os
import platform
import re
import sys
import traceback

import adsk.core


CHALLENGE_SCHEMA_VERSION = "gate6-preflight-challenge-0.1"
RESPONSE_SCHEMA_VERSION = "gate6-fusion-environment-response-0.1"
SPECIFICATION_COMMIT = "c440aace7306b9d68e2ae6a6ae757f36d8db1d85"
PROBE_SCRIPT_PATH = "fusion_scripts/Gate6EnvironmentProbe/Gate6EnvironmentProbe.py"
PROBE_MANIFEST_PATH = "fusion_scripts/Gate6EnvironmentProbe/Gate6EnvironmentProbe.manifest"
FROZEN_SHA256 = {
    "docs/research_directions/gate6_precheck_v0_1.md": "5356ccef2eb6b8aa7cd52584b2b0990a5690e160654d09427d7f0e260fbc8015",
    "config/gate6_precheck_v0_1.json": "9e81b6c3d119a53df8735969a29cb6b282539e460b3de22c415d81d71b896a6b",
}
EXPECTED_ENVIRONMENT = {
    "fusion": "2704.1.53",
    "fusion_python": "3.14.0",
    "external_python": "3.11.16",
    "cadquery": "2.8.0",
    "ocp": "7.9.3.1",
    "numpy": "2.4.6",
    "scipy": "1.17.1",
    "os": "Windows-10-10.0.22621-SP0",
}
CHALLENGE_FIELDS = {
    "schema_version", "challenge_id", "challenge_nonce", "issued_at_utc",
    "specification_commit", "implementation_commit", "contract_version",
    "frozen_sha256", "probe_artifacts", "expected_environment", "execution_authorization",
    "formal_campaign_requested", "campaign_status", "oracle_run_count",
    "formal_replay_performed",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_INSTANT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
FORMAL_RUN_RE = re.compile(r"^(?:OS|DE)_(?:JC|CJ)_R[123]$", re.IGNORECASE)


class ProbeError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _project_root():
    return os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _safe_external_path(path, project_root):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ProbeError("PF_UNSAFE_PATH", "An absolute external path is required")
    candidate = os.path.realpath(path)
    root = os.path.realpath(project_root)
    try:
        if os.path.commonpath((candidate, root)) == root:
            raise ProbeError("PF_UNSAFE_PATH", "Probe files must be outside the repository")
    except ValueError:
        pass
    parts = [part.casefold() for part in os.path.normpath(candidate).split(os.sep) if part]
    if (any(parts[index:index + 3] == ["runs", "gate6", "precheck"]
            for index in range(max(0, len(parts) - 2)))
            or any(FORMAL_RUN_RE.fullmatch(part) for part in parts)
            or any(part.startswith("gate6-precheck-0.1") for part in parts)):
        raise ProbeError("PF_UNSAFE_PATH", "Formal campaign-like paths are forbidden")
    if not any(part in ("temp", "tmp", "qualification", "gate6-qualification") or part.startswith("qualification-")
               for part in parts):
        raise ProbeError("PF_UNSAFE_PATH", "Path must be under a temp or qualification location")
    return candidate


def _fusion_python_version():
    return "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)


def _platform_string():
    return platform.platform()


def _process_creation_time_from_winapi(ctypes_module):
    class FILETIME(ctypes_module.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes_module.c_uint32),
            ("dwHighDateTime", ctypes_module.c_uint32),
        ]

    try:
        kernel32 = ctypes_module.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = ctypes_module.c_void_p
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = [
            ctypes_module.c_void_p,
            ctypes_module.POINTER(FILETIME),
            ctypes_module.POINTER(FILETIME),
            ctypes_module.POINTER(FILETIME),
            ctypes_module.POINTER(FILETIME),
        ]
        get_process_times.restype = ctypes_module.c_int
        creation = FILETIME()
        exit_time = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        handle = get_current_process()
        if not get_process_times(
            handle, ctypes_module.byref(creation), ctypes_module.byref(exit_time),
            ctypes_module.byref(kernel), ctypes_module.byref(user)
        ):
            return None, "GetProcessTimes failed (WinError {})".format(
                ctypes_module.get_last_error()
            )
        ticks = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
        seconds = ticks / 10000000.0 - 11644473600.0
        return datetime.datetime.fromtimestamp(
            seconds, datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z"), None
    except Exception as exc:
        return None, "{}: {}".format(type(exc).__name__, exc)


def _process_creation_time_detail():
    if os.name != "nt":
        return None, "Windows process identity is unavailable on this platform"
    try:
        import ctypes
    except Exception as exc:
        return None, "{}: {}".format(type(exc).__name__, exc)
    return _process_creation_time_from_winapi(ctypes)


def _process_creation_time():
    timestamp, _ = _process_creation_time_detail()
    return timestamp


def _scripts_metadata(app):
    records = []
    scripts = getattr(app, "scripts", None)
    if scripts is None:
        return records
    for index in range(scripts.count):
        script = scripts.item(index)
        manifest_path = getattr(script, "manifestPath", None)
        records.append({
            "id": str(getattr(script, "id", "")),
            "name": str(getattr(script, "name", "")),
            "version": str(getattr(script, "version", "")),
            "manifest_sha256": _sha256(manifest_path)
            if manifest_path and os.path.isfile(manifest_path) else None,
        })
    return sorted(records, key=lambda item: (item["id"], item["name"], item["version"]))


def _load_challenge(path, expected_hash):
    if not isinstance(expected_hash, str) or SHA256_RE.fullmatch(expected_hash) is None:
        raise ProbeError("PF_CHALLENGE_INVALID", "Expected challenge hash is invalid")
    try:
        with open(path, "rb") as stream:
            payload = stream.read()
    except OSError as exc:
        raise ProbeError("PF_CHALLENGE_INVALID", str(exc)) from exc
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge SHA-256 mismatch")
    try:
        challenge = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge is not valid UTF-8 JSON") from exc
    if not isinstance(challenge, dict) or set(challenge) != CHALLENGE_FIELDS:
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge fields are not exact")
    if (challenge["schema_version"] != CHALLENGE_SCHEMA_VERSION
            or challenge["specification_commit"] != SPECIFICATION_COMMIT
            or challenge["contract_version"] != "gate6-precheck-0.1"
            or challenge["frozen_sha256"] != FROZEN_SHA256
            or challenge["probe_artifacts"] != {
                PROBE_SCRIPT_PATH: _sha256(__file__),
                PROBE_MANIFEST_PATH: _sha256(os.path.splitext(__file__)[0] + ".manifest"),
            }
            or challenge["expected_environment"] != EXPECTED_ENVIRONMENT
            or challenge["execution_authorization"] != "not_granted"
            or challenge["formal_campaign_requested"] is not False
            or challenge["campaign_status"] != "NOT_STARTED"
            or challenge["oracle_run_count"] != 0
            or challenge["formal_replay_performed"] is not False
            or COMMIT_RE.fullmatch(str(challenge["implementation_commit"])) is None
            or not isinstance(challenge["challenge_id"], str)
            or not challenge["challenge_id"].startswith("PFCH-")
            or not isinstance(challenge["challenge_nonce"], str)
            or len(challenge["challenge_nonce"]) != 64):
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge binding is invalid")
    return challenge


def _verify_challenge_seal(challenge_path, challenge_sha256, expected_seal_sha256):
    if not isinstance(expected_seal_sha256, str) or SHA256_RE.fullmatch(expected_seal_sha256) is None:
        raise ProbeError("PF_CHALLENGE_INVALID", "Expected challenge seal hash is invalid")
    seal_path = os.path.join(os.path.dirname(challenge_path), "SHA256SUMS")
    try:
        with open(seal_path, "rb") as stream:
            content = stream.read()
    except OSError as exc:
        raise ProbeError("PF_CHALLENGE_INVALID", str(exc)) from exc
    if hashlib.sha256(content).hexdigest() != expected_seal_sha256:
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge seal differs from external anchor")
    expected_line = "{}  {}\n".format(
        challenge_sha256, os.path.basename(challenge_path)
    ).encode("utf-8")
    if content != expected_line:
        raise ProbeError("PF_CHALLENGE_INVALID", "Challenge seal contents are invalid")


def _execute_probe(
    app,
    challenge_path,
    expected_challenge_sha256,
    expected_challenge_seal_sha256,
    response_path,
    project_root,
):
    """Validate a challenge and record environment only; no CAD API is used."""
    safe_challenge = _safe_external_path(challenge_path, project_root)
    safe_response = _safe_external_path(response_path, project_root)
    if os.path.exists(safe_response):
        raise ProbeError("PF_RESPONSE_EXISTS", "Response already exists")
    _verify_challenge_seal(
        safe_challenge, expected_challenge_sha256, expected_challenge_seal_sha256
    )
    challenge = _load_challenge(safe_challenge, expected_challenge_sha256)
    process_start, process_identity_diagnostic = _process_creation_time_detail()
    if not process_start or UTC_INSTANT_RE.fullmatch(process_start) is None:
        raise ProbeError(
            "PF_PROCESS_IDENTITY_UNAVAILABLE",
            "Fusion process creation time is unavailable ({})".format(
                process_identity_diagnostic or "no diagnostic"
            ),
        )
    try:
        datetime.datetime.fromisoformat(process_start[:-1] + "+00:00")
    except ValueError as exc:
        raise ProbeError("PF_PROCESS_IDENTITY_UNAVAILABLE", "Fusion process creation time is invalid") from exc
    live = {
        "fusion": str(getattr(app, "version", "")),
        "fusion_python": _fusion_python_version(),
        "os": _platform_string(),
        "pid": os.getpid(),
        "process_start_utc": process_start,
    }
    if any(live[key] != EXPECTED_ENVIRONMENT[key] for key in ("fusion", "fusion_python", "os")):
        raise ProbeError("PF_ENVIRONMENT_MISMATCH", "Live Fusion environment differs from challenge")
    manifest_path = os.path.splitext(__file__)[0] + ".manifest"
    response = {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "challenge_sha256": expected_challenge_sha256,
        "challenge_id": challenge["challenge_id"],
        "challenge_nonce": challenge["challenge_nonce"],
        "specification_commit": challenge["specification_commit"],
        "implementation_commit": challenge["implementation_commit"],
        "contract_version": challenge["contract_version"],
        "live_environment": live,
        "probe": {
            "script_sha256": _sha256(__file__),
            "manifest_sha256": _sha256(manifest_path),
            "fusion_scripts": _scripts_metadata(app),
        },
        "campaign": {
            "status": "NOT_STARTED", "oracle_run_count": 0,
            "formal_replay_performed": False, "authorized": False,
        },
    }
    parent = os.path.dirname(safe_response)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    try:
        with open(safe_response, "x", encoding="utf-8", newline="\n") as stream:
            json.dump(response, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            stream.write("\n")
    except FileExistsError as exc:
        raise ProbeError("PF_RESPONSE_EXISTS", "Response already exists") from exc
    return response


probe_environment = _execute_probe


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        names = (
            "GATE6_PREFLIGHT_CHALLENGE_PATH",
            "GATE6_PREFLIGHT_CHALLENGE_SHA256",
            "GATE6_PREFLIGHT_CHALLENGE_SEAL_SHA256",
            "GATE6_PREFLIGHT_RESPONSE_PATH",
        )
        values = [os.environ.get(name) for name in names]
        if any(not value for value in values):
            raise ProbeError("PF_CONTEXT_INVALID", "Required preflight environment variables are missing")
        response = _execute_probe(
            app,
            values[0],
            values[1],
            values[2],
            values[3],
            _project_root(),
        )
        ui.messageBox("Gate 6 environment probe succeeded.\n{}".format(response["challenge_id"]))
    except Exception as exc:
        code = exc.code if isinstance(exc, ProbeError) else "PF_FUSION_PROBE_INVALID"
        ui.messageBox("Gate 6 environment probe failed [{}]:\n{}\n\n{}".format(
            code, exc, traceback.format_exc()
        ))
