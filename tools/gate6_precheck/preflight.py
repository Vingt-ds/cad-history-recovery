"""Gate 6 pre-execution handshake; never authorizes or runs the campaign."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .contract import (
    CONFIG_PATH,
    FROZEN_SHA256,
    SPECIFICATION_COMMIT,
    ContractError,
    load_contract,
    sha256_file,
)
from .evidence import EvidencePackage


CHALLENGE_SCHEMA_VERSION = "gate6-preflight-challenge-0.1"
RESPONSE_SCHEMA_VERSION = "gate6-fusion-environment-response-0.1"
EXTERNAL_ENVIRONMENT_SCHEMA_VERSION = "gate6-external-environment-capture-0.1"
QUALIFICATION_RESULT_SCHEMA_VERSION = "gate6-qualification-result-0.1"
PROBE_SCRIPT_PATH = "fusion_scripts/Gate6EnvironmentProbe/Gate6EnvironmentProbe.py"
PROBE_MANIFEST_PATH = "fusion_scripts/Gate6EnvironmentProbe/Gate6EnvironmentProbe.manifest"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_INSTANT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
FORMAL_RUN_RE = re.compile(r"^(?:OS|DE)_(?:JC|CJ)_R[123]$", re.IGNORECASE)

REQUIRED_QUALIFICATION_COMMANDS = {
    "gate6": "python -m unittest discover -s tests/gate6_precheck -t . -v",
    "full_repo": "python -m unittest discover -s tests -v",
}
REQUIRED_QUALIFICATION_ARGV = {
    "gate6": ("-m", "unittest", "discover", "-s", "tests/gate6_precheck", "-t", ".", "-v"),
    "full_repo": ("-m", "unittest", "discover", "-s", "tests", "-v"),
}
UNITTEST_SUMMARY_RE = re.compile(r"Ran (\d+) tests? in [^\r\n]+\r?\n\r?\nOK\r?\n?$")

CHALLENGE_FIELDS = {
    "schema_version", "challenge_id", "challenge_nonce", "issued_at_utc",
    "specification_commit", "implementation_commit", "contract_version",
    "frozen_sha256", "probe_artifacts", "expected_environment", "execution_authorization",
    "formal_campaign_requested", "campaign_status", "oracle_run_count",
    "formal_replay_performed",
}
RESPONSE_FIELDS = {
    "schema_version", "challenge_sha256", "challenge_id", "challenge_nonce",
    "specification_commit", "implementation_commit", "contract_version",
    "live_environment", "probe", "campaign",
}


def _git_output(repo_root, args):
    command = ["git", "-c", f"safe.directory={Path(repo_root).resolve()}", *args]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError("PF_GIT_CHECK_FAILED", str(exc)) from exc
    return completed.stdout.strip()


def _fail(code, message):
    raise ContractError(code, message)


def _validate_sha(value, length, code):
    pattern = FULL_SHA_RE if length == 40 else LOWER_SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(code, f"Expected a full lowercase SHA-{1 if length == 40 else 256} value")


def _validate_external_destination(repo_root, destination):
    raw = Path(destination)
    if not raw.is_absolute():
        _fail("PF_UNSAFE_PATH", "Destination must be absolute")
    root = Path(repo_root).resolve()
    resolved = raw.resolve()
    if resolved == root or resolved.is_relative_to(root):
        _fail("PF_UNSAFE_PATH", "Preflight evidence must be outside the repository")
    parts = [part.casefold() for part in resolved.parts]
    if (any(parts[index:index + 3] == ["runs", "gate6", "precheck"]
            for index in range(max(0, len(parts) - 2)))
            or any(FORMAL_RUN_RE.fullmatch(part) for part in parts)
            or any(part.startswith("gate6-precheck-0.1") for part in parts)):
        _fail("PF_UNSAFE_PATH", "Formal campaign-like paths are forbidden")
    return resolved


def _formal_request_present(root):
    candidates = (
        root / "gate6_formal_execution_request.json",
        root / "formal_gate6_request.json",
        root / "gate6_execution_request.json",
        root / "requests" / "gate6_formal_execution_request.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return True
        if not isinstance(value, dict) or value.get("formal_campaign_requested") is not False:
            return True
    return False


def _assert_issue_state(repo_root, implementation_commit, git):
    root = Path(repo_root).resolve()
    _validate_sha(implementation_commit, 40, "PF_IMPLEMENTATION_BINDING_INVALID")
    load_contract(root)
    config = load_contract(root)
    if config.get("execution_authorization") != "not_granted":
        _fail("PF_AUTHORIZATION_STATE_INVALID", "Frozen contract must remain not_granted")
    head = git(root, ("rev-parse", "HEAD"))
    if head != implementation_commit:
        _fail("PF_IMPLEMENTATION_BINDING_INVALID", "Implementation commit is not clean HEAD")
    if git(root, ("status", "--porcelain=v1")):
        _fail("PF_WORKTREE_DIRTY", "Worktree must be clean")
    try:
        git(root, ("merge-base", "--is-ancestor", SPECIFICATION_COMMIT, implementation_commit))
    except Exception as exc:
        if isinstance(exc, ContractError):
            _fail("PF_SPEC_ANCESTRY_INVALID", "Implementation does not descend from the specification commit")
        raise
    formal_root = root / "runs" / "gate6" / "precheck"
    if formal_root.exists():
        _fail("PF_FORMAL_ROOT_PRESENT", "Formal Gate 6 evidence root already exists")
    if _formal_request_present(root):
        _fail("PF_FORMAL_REQUEST_PRESENT", "A formal Gate 6 execution request is present")
    return config


def _probe_artifact_hashes(root, implementation_commit=None, git=None):
    try:
        hashes = {
            PROBE_SCRIPT_PATH: sha256_file(root / PROBE_SCRIPT_PATH),
            PROBE_MANIFEST_PATH: sha256_file(root / PROBE_MANIFEST_PATH),
        }
    except OSError as exc:
        _fail("PF_IMPLEMENTATION_BINDING_INVALID", str(exc))
    if implementation_commit is not None:
        if git is None:
            _fail("PF_IMPLEMENTATION_BINDING_INVALID", "Git binding checker is required")
        for relative in hashes:
            committed_blob = git(root, ("rev-parse", f"{implementation_commit}:{relative}"))
            worktree_blob = git(root, ("hash-object", f"--path={relative}", relative))
            if committed_blob != worktree_blob:
                _fail("PF_IMPLEMENTATION_BINDING_INVALID", f"Probe artifact differs from commit: {relative}")
    return hashes


def _assert_evaluation_state(root, implementation_commit, git):
    """Recheck all mutable preflight state; callers invoke this twice."""
    try:
        raw = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("PF_SPECIFICATION_BINDING_INVALID", str(exc))
    if not isinstance(raw, dict) or raw.get("execution_authorization") != "not_granted":
        _fail("PF_AUTHORIZATION_STATE_INVALID", "Execution authorization must remain not_granted")
    try:
        config = load_contract(root)
    except ContractError as exc:
        _fail("PF_SPECIFICATION_BINDING_INVALID", str(exc))
    if (root / "runs" / "gate6" / "precheck").exists():
        _fail("PF_FORMAL_ROOT_PRESENT", "Formal Gate 6 evidence root is present")
    if _formal_request_present(root):
        _fail("PF_FORMAL_REQUEST_PRESENT", "A formal Gate 6 execution request is present")
    head = git(root, ("rev-parse", "HEAD"))
    if head != implementation_commit:
        _fail("PF_IMPLEMENTATION_BINDING_INVALID", "Current HEAD differs from the challenge")
    if git(root, ("status", "--porcelain=v1")):
        _fail("PF_WORKTREE_DIRTY", "Worktree must remain clean")
    try:
        git(root, ("merge-base", "--is-ancestor", SPECIFICATION_COMMIT,
                   implementation_commit))
    except Exception as exc:
        _fail("PF_SPEC_ANCESTRY_INVALID", str(exc))
    _probe_artifact_hashes(root, implementation_commit, git)
    return config, {
        "head": head,
        "worktree_clean": True,
        "specification_commit": SPECIFICATION_COMMIT,
        "implementation_commit": implementation_commit,
        "execution_authorization": "not_granted",
        "formal_root_absent": True,
        "formal_request_absent": True,
        "frozen_sha256": dict(FROZEN_SHA256),
    }


def issue_challenge(repo_root, implementation_commit, destination, *, _git=None):
    """Create an exclusive, sealed, non-authorizing Fusion probe challenge."""
    git = _git or _git_output
    root = Path(repo_root).resolve()
    target = _validate_external_destination(root, destination)
    config = _assert_issue_state(root, implementation_commit, git)
    challenge = {
        "schema_version": CHALLENGE_SCHEMA_VERSION,
        "challenge_id": "PFCH-" + secrets.token_hex(16),
        "challenge_nonce": secrets.token_hex(32),
        "issued_at_utc": datetime.now(timezone.utc).isoformat(),
        "specification_commit": SPECIFICATION_COMMIT,
        "implementation_commit": implementation_commit,
        "contract_version": config["contract_version"],
        "frozen_sha256": dict(FROZEN_SHA256),
        "probe_artifacts": _probe_artifact_hashes(root, implementation_commit, git),
        "expected_environment": dict(config["environment"]),
        "execution_authorization": "not_granted",
        "formal_campaign_requested": False,
        "campaign_status": "NOT_STARTED",
        "oracle_run_count": 0,
        "formal_replay_performed": False,
    }
    package = EvidencePackage(target)
    challenge_path = package.write_json("preflight_challenge.json", challenge)
    challenge_sha256 = sha256_file(challenge_path)
    package.seal()
    return {
        "challenge": challenge,
        "challenge_path": str(challenge_path),
        "challenge_sha256": challenge_sha256,
        "seal_sha256": package.seal_digest,
    }


def _read_json_bound(path, expected_hash, *, code, required_fields):
    _validate_sha(expected_hash, 64, code)
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        _fail(code, str(exc))
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        _fail(code, "SHA-256 binding mismatch")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail(code, f"Invalid UTF-8 JSON: {exc}")
    if not isinstance(value, dict) or set(value) != required_fields:
        _fail(code, "Schema fields are not exact")
    return value, payload


def _append_failure(failures, code, message):
    record = {"code": code, "message": str(message)}
    if record not in failures:
        failures.append(record)


def _check_challenge(challenge, config, root):
    if challenge["schema_version"] != CHALLENGE_SCHEMA_VERSION:
        _fail("PF_CHALLENGE_INVALID", "Challenge schema version mismatch")
    if (not isinstance(challenge["challenge_id"], str)
            or not challenge["challenge_id"].startswith("PFCH-")
            or not isinstance(challenge["challenge_nonce"], str)
            or len(challenge["challenge_nonce"]) != 64):
        _fail("PF_CHALLENGE_INVALID", "Challenge identity is invalid")
    if challenge["specification_commit"] != SPECIFICATION_COMMIT:
        _fail("PF_CHALLENGE_INVALID", "Specification commit mismatch")
    _validate_sha(challenge["implementation_commit"], 40, "PF_CHALLENGE_INVALID")
    if (challenge["contract_version"] != config["contract_version"]
            or challenge["frozen_sha256"] != FROZEN_SHA256
            or challenge["probe_artifacts"] != _probe_artifact_hashes(root)
            or challenge["expected_environment"] != config["environment"]):
        _fail("PF_CHALLENGE_INVALID", "Frozen contract binding mismatch")
    expected_state = (
        challenge["execution_authorization"] == "not_granted"
        and challenge["formal_campaign_requested"] is False
        and challenge["campaign_status"] == "NOT_STARTED"
        and challenge["oracle_run_count"] == 0
        and challenge["formal_replay_performed"] is False
    )
    if not expected_state:
        _fail("PF_CHALLENGE_INVALID", "Challenge attempts to alter campaign state")


def _check_response(response, challenge, challenge_sha256, config, root):
    if response["schema_version"] != RESPONSE_SCHEMA_VERSION:
        _fail("PF_FUSION_PROBE_INVALID", "Response schema version mismatch")
    bindings = (
        response["challenge_sha256"] == challenge_sha256,
        response["challenge_id"] == challenge["challenge_id"],
        response["challenge_nonce"] == challenge["challenge_nonce"],
        response["specification_commit"] == SPECIFICATION_COMMIT,
        response["implementation_commit"] == challenge["implementation_commit"],
        response["contract_version"] == config["contract_version"],
    )
    if not all(bindings):
        _fail("PF_FUSION_PROBE_INVALID", "Fusion response binding mismatch")
    campaign = response["campaign"]
    if campaign != {
        "status": "NOT_STARTED", "oracle_run_count": 0,
        "formal_replay_performed": False, "authorized": False,
    }:
        _fail("PF_FUSION_PROBE_INVALID", "Fusion response campaign state is invalid")
    live = response["live_environment"]
    if not isinstance(live, dict):
        _fail("PF_FUSION_PROBE_INVALID", "Live environment must be an object")
    for name in ("fusion", "fusion_python", "os", "pid", "process_start_utc"):
        if name not in live:
            _fail("PF_FUSION_PROBE_INVALID", f"Missing live environment field: {name}")
    if not isinstance(live["pid"], int) or isinstance(live["pid"], bool) or live["pid"] <= 0:
        _fail("PF_FUSION_PROBE_INVALID", "Fusion PID is invalid")
    process_start = live["process_start_utc"]
    if not isinstance(process_start, str) or UTC_INSTANT_RE.fullmatch(process_start) is None:
        _fail("PF_FUSION_PROBE_INVALID", "Fusion process start must be a strict UTC Z instant")
    try:
        datetime.fromisoformat(process_start[:-1] + "+00:00")
    except ValueError as exc:
        _fail("PF_FUSION_PROBE_INVALID", f"Fusion process start is invalid: {exc}")
    expected = config["environment"]
    if any(live[key] != expected[key] for key in ("fusion", "fusion_python", "os")):
        _fail("PF_ENVIRONMENT_MISMATCH", "Live Fusion environment differs from the frozen contract")
    probe = response["probe"]
    if not isinstance(probe, dict) or set(probe) != {
        "script_sha256", "manifest_sha256", "fusion_scripts"
    }:
        _fail("PF_FUSION_PROBE_INVALID", "Probe metadata schema is invalid")
    _validate_sha(probe["script_sha256"], 64, "PF_FUSION_PROBE_INVALID")
    _validate_sha(probe["manifest_sha256"], 64, "PF_FUSION_PROBE_INVALID")
    expected_probe = _probe_artifact_hashes(root)
    if (probe["script_sha256"] != expected_probe[PROBE_SCRIPT_PATH]
            or probe["manifest_sha256"] != expected_probe[PROBE_MANIFEST_PATH]
            or challenge["probe_artifacts"] != expected_probe):
        _fail("PF_FUSION_PROBE_INVALID", "Probe artifacts do not match the bound implementation")
    if not isinstance(probe["fusion_scripts"], list):
        _fail("PF_FUSION_PROBE_INVALID", "Fusion script inventory must be a list")


def _check_external_environment(value, config):
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "environment"}
            or value["schema_version"] != EXTERNAL_ENVIRONMENT_SCHEMA_VERSION):
        _fail("PF_EXTERNAL_ENVIRONMENT_INVALID", "External environment artifact schema is invalid")
    environment = value["environment"]
    expected = config["environment"]
    keys = ("external_python", "cadquery", "ocp", "numpy", "scipy", "os")
    if not isinstance(environment, dict) or set(environment) != set(keys):
        _fail("PF_EXTERNAL_ENVIRONMENT_INVALID", "External environment schema is invalid")
    if any(environment[key] != expected[key] for key in keys):
        _fail("PF_ENVIRONMENT_MISMATCH", "External environment differs from the frozen contract")
    return environment


def _read_artifact(path, expected_hash, repo_root, code):
    source = _validate_external_destination(repo_root, path)
    _validate_sha(expected_hash, 64, code)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        _fail(code, str(exc))
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        _fail(code, "Artifact SHA-256 binding mismatch")
    return payload


def _check_qualifications(value, stdout_artifacts, root):
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "results"}
            or value["schema_version"] != QUALIFICATION_RESULT_SCHEMA_VERSION):
        _fail("PF_QUALIFICATION_INVALID", "Qualification result artifact schema is invalid")
    values = value["results"]
    if not isinstance(values, list) or len(values) != len(REQUIRED_QUALIFICATION_COMMANDS):
        _fail("PF_QUALIFICATION_INVALID", "Both qualification command records are required")
    if not isinstance(stdout_artifacts, dict) or set(stdout_artifacts) != set(REQUIRED_QUALIFICATION_COMMANDS):
        _fail("PF_QUALIFICATION_INVALID", "Qualification stdout artifact set is incomplete")
    seen = set()
    raw_outputs = {}
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "name", "command", "exit_code", "test_count", "stdout_sha256"
        }:
            _fail("PF_QUALIFICATION_INVALID", "Qualification record schema is invalid")
        name = value["name"]
        if name in seen or REQUIRED_QUALIFICATION_COMMANDS.get(name) != value["command"]:
            _fail("PF_QUALIFICATION_INVALID", "Qualification command is not the frozen command")
        seen.add(name)
        if value["exit_code"] != 0:
            _fail("PF_QUALIFICATION_INVALID", f"Qualification failed: {name}")
        if (not isinstance(value["test_count"], int) or isinstance(value["test_count"], bool)
                or value["test_count"] <= 0):
            _fail("PF_QUALIFICATION_INVALID", f"Positive test count is required: {name}")
        artifact = stdout_artifacts[name]
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            _fail("PF_QUALIFICATION_INVALID", "Qualification stdout binding schema is invalid")
        if artifact["sha256"] != value["stdout_sha256"]:
            _fail("PF_QUALIFICATION_INVALID", "Qualification stdout hash declarations differ")
        raw_outputs[name] = _read_artifact(
            artifact["path"], artifact["sha256"], root, "PF_QUALIFICATION_INVALID"
        )
    if seen != set(REQUIRED_QUALIFICATION_COMMANDS):
        _fail("PF_QUALIFICATION_INVALID", "Qualification command set is incomplete")
    return raw_outputs


def _collect_external_environment():
    import cadquery
    import OCP
    import numpy
    import scipy

    cadquery_version = getattr(cadquery, "__version__", None)
    if not cadquery_version:
        cadquery_version = importlib.metadata.version("cadquery")
    ocp_version = getattr(OCP, "__version__", None)
    if not ocp_version:
        try:
            ocp_version = importlib.metadata.version("cadquery-ocp")
        except importlib.metadata.PackageNotFoundError:
            ocp_version = importlib.metadata.version("OCP")
    return {
        "external_python": platform.python_version(),
        "cadquery": str(cadquery_version),
        "ocp": str(ocp_version),
        "numpy": str(numpy.__version__),
        "scipy": str(scipy.__version__),
        "os": platform.platform(),
    }


def _run_qualification(argv, cwd):
    return subprocess.run(
        list(argv), cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )


def _capture_qualifications(root, runner):
    records = []
    outputs = {}
    for name, suffix in REQUIRED_QUALIFICATION_ARGV.items():
        argv = (sys.executable, *suffix)
        completed = runner(argv, root)
        if not isinstance(completed, subprocess.CompletedProcess):
            _fail("PF_QUALIFICATION_INVALID", "Runner did not return subprocess.CompletedProcess")
        if tuple(completed.args) != argv:
            _fail("PF_QUALIFICATION_INVALID", f"Runner changed command: {name}")
        if not isinstance(completed.stdout, str) or not isinstance(completed.stderr, str):
            _fail("PF_QUALIFICATION_INVALID", "Qualification output must be captured text")
        combined = completed.stdout + completed.stderr
        match = UNITTEST_SUMMARY_RE.search(combined)
        if completed.returncode != 0 or match is None:
            _fail("PF_QUALIFICATION_INVALID", f"Qualification did not end in an exact passing unittest summary: {name}")
        stdout = completed.stdout.encode("utf-8")
        stderr = completed.stderr.encode("utf-8")
        outputs[name] = {"stdout": stdout, "stderr": stderr}
        records.append({
            "name": name,
            "command": REQUIRED_QUALIFICATION_COMMANDS[name],
            "argv": list(argv),
            "exit_code": completed.returncode,
            "test_count": int(match.group(1)),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        })
    return records, outputs


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _markdown_report(report):
    lines = [
        "# Gate 6 pre-execution status",
        "",
        f"- Outcome: `{report['outcome']}`",
        "- Formal campaign: `NOT_STARTED`",
        "- Oracle run count: `0`",
        "- Formal replay performed: `false`",
        "- Execution authorized: `false`",
        "",
    ]
    if report["failures"]:
        lines.extend(["## Blocking preflight findings", ""])
        lines.extend(f"- `{item['code']}`: {item['message']}" for item in report["failures"])
        lines.append("")
    else:
        lines.extend([
            "All required preflight evidence is internally consistent. This is readiness for review only; it does not authorize any oracle replay.",
            "",
        ])
    return "\n".join(lines).encode("utf-8")


def evaluate_preflight(
    repo_root,
    challenge_path,
    challenge_sha256,
    challenge_seal_sha256,
    response_path,
    response_sha256,
    destination,
    *,
    _git=None,
    _runner=None,
    _env_collector=None,
):
    """Capture and evaluate qualification evidence; never authorize the campaign."""
    git = _git or _git_output
    runner = _runner or _run_qualification
    env_collector = _env_collector or _collect_external_environment
    root = Path(repo_root).resolve()
    target = _validate_external_destination(root, destination)
    config = None
    failures = []
    challenge = None
    challenge_payload = None
    response_payload = None
    external_payload = None
    qualification_payload = None
    external_environment = None
    qualification_results = None
    qualification_outputs = {}
    state_snapshot = None

    try:
        EvidencePackage.verify_existing(Path(challenge_path).resolve().parent, challenge_seal_sha256)
    except ContractError as exc:
        raise ContractError("PF_CHALLENGE_INVALID", str(exc)) from exc

    try:
        challenge, challenge_payload = _read_json_bound(
            challenge_path, challenge_sha256,
            code="PF_CHALLENGE_INVALID", required_fields=CHALLENGE_FIELDS,
        )
        _validate_sha(challenge["implementation_commit"], 40, "PF_CHALLENGE_INVALID")
    except ContractError as exc:
        _append_failure(failures, exc.code, exc)

    if challenge is not None:
        try:
            config, state_snapshot = _assert_evaluation_state(
                root, challenge["implementation_commit"], git
            )
            _check_challenge(challenge, config, root)
        except ContractError as exc:
            _append_failure(failures, exc.code, exc)

        try:
            response, response_payload = _read_json_bound(
                response_path, response_sha256,
                code="PF_FUSION_PROBE_INVALID", required_fields=RESPONSE_FIELDS,
            )
            if config is not None:
                _check_response(response, challenge, challenge_sha256, config, root)
        except ContractError as exc:
            _append_failure(failures, exc.code, exc)
    else:
        _append_failure(failures, "PF_FUSION_PROBE_INVALID", "Challenge is invalid; response cannot be trusted")

    try:
        external_environment = env_collector()
        external_value = {
            "schema_version": EXTERNAL_ENVIRONMENT_SCHEMA_VERSION,
            "environment": external_environment,
        }
        if config is not None:
            external_environment = _check_external_environment(external_value, config)
        external_payload = (
            json.dumps(external_value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2).encode("utf-8") + b"\n"
        )
    except (ContractError, Exception) as exc:
        code = exc.code if isinstance(exc, ContractError) else "PF_EXTERNAL_ENVIRONMENT_INVALID"
        _append_failure(failures, code, exc)

    try:
        qualification_results, qualification_outputs = _capture_qualifications(root, runner)
        qualification_value = {
            "schema_version": QUALIFICATION_RESULT_SCHEMA_VERSION,
            "results": qualification_results,
        }
        qualification_payload = (
            json.dumps(qualification_value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2).encode("utf-8") + b"\n"
        )
    except (ContractError, Exception) as exc:
        code = exc.code if isinstance(exc, ContractError) else "PF_QUALIFICATION_INVALID"
        _append_failure(failures, code, exc)

    if challenge is not None:
        try:
            config, state_snapshot = _assert_evaluation_state(
                root, challenge["implementation_commit"], git
            )
        except ContractError as exc:
            _append_failure(failures, exc.code, exc)

    package = EvidencePackage(target)
    if challenge_payload is not None:
        package.write_bytes("inputs/preflight_challenge.json", challenge_payload)
    if response_payload is not None:
        package.write_bytes("inputs/fusion_environment_response.json", response_payload)
    if external_payload is not None:
        package.write_bytes("inputs/external_environment.json", external_payload)
    if qualification_payload is not None:
        package.write_bytes("inputs/qualification_results.json", qualification_payload)
    for name, streams in sorted(qualification_outputs.items()):
        package.write_bytes(f"inputs/{name}.stdout.txt", streams["stdout"])
        package.write_bytes(f"inputs/{name}.stderr.txt", streams["stderr"])

    report = {
        "schema_version": "gate6-preflight-report-0.1",
        "outcome": "NOT_READY_FOR_REVIEW" if failures else "READY_FOR_REVIEW_NOT_AUTHORIZED",
        "specification_commit": SPECIFICATION_COMMIT,
        "implementation_commit": challenge.get("implementation_commit") if challenge else None,
        "contract_version": (
            config["contract_version"] if config is not None
            else challenge.get("contract_version") if challenge else None
        ),
        "captured_at_utc": _utc_now(),
        "challenge_sha256": challenge_sha256,
        "response_sha256": response_sha256,
        "external_environment_sha256": (
            hashlib.sha256(external_payload).hexdigest() if external_payload is not None else None
        ),
        "qualification_result_sha256": (
            hashlib.sha256(qualification_payload).hexdigest() if qualification_payload is not None else None
        ),
        "external_environment": external_environment,
        "qualification_results": qualification_results,
        "state_snapshot": state_snapshot,
        "failures": failures,
        "campaign": {
            "status": "NOT_STARTED", "oracle_run_count": 0,
            "formal_replay_performed": False, "authorized": False,
        },
    }
    package.write_json("preflight_report.json", report)
    package.write_bytes("preflight_report.md", _markdown_report(report))
    package.seal()
    if not failures and challenge is not None:
        try:
            _assert_evaluation_state(root, challenge["implementation_commit"], git)
        except ContractError as exc:
            raise ContractError("PF_STATE_CHANGED_DURING_SEAL", str(exc)) from exc
    return {"report": report, "seal_sha256": package.seal_digest, "package_path": str(target)}
