"""Gate 3 formal-run verifier."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

import result_package


EXPECTED_CASE_IDS = ["D-H{:02d}".format(index) for index in range(1, 6)]


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_run(run_dir):
    run_dir = Path(run_dir)
    project_root = run_dir.parents[1] if run_dir.parent.name == "benchmark_results" else None
    manifest_path = run_dir / "manifest.json"
    environment_path = run_dir / "environment.json"
    environment_present = environment_path.is_file()
    environment = _read_json(environment_path) if environment_present else {}
    fusion = environment.get("fusion", {}) if isinstance(environment, dict) else {}
    environment_complete = (
        environment.get("environment_schema") == "gate3-environment-0.1"
        and isinstance(fusion.get("version"), str)
        and bool(fusion["version"])
        and isinstance(fusion.get("python_version"), str)
        and bool(fusion["python_version"])
    )
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    manifest_schema = manifest.get("manifest_schema") == "gate3-run-manifest-0.1"
    git_commit_recorded = isinstance(manifest.get("git_commit"), str) and re.fullmatch(
        r"[0-9a-f]{40}", manifest["git_commit"]
    ) is not None
    manifest_case_set = manifest.get("case_ids") == EXPECTED_CASE_IDS
    git_clean = manifest.get("git_dirty_at_start") is False
    protocol_hash = manifest.get("validation_protocol_sha256")
    protocol_recorded = isinstance(protocol_hash, str) and re.fullmatch(
        r"[0-9a-f]{64}", protocol_hash
    ) is not None
    frozen_hashes_match = False
    protocol_hash_matches = False
    if project_root is not None:
        matrix_path = project_root / "benchmarks" / "case_matrix.json"
        benchmark_manifest_path = project_root / "benchmarks" / "manifest.json"
        protocol_path = project_root / "config" / "gate3_validation_protocol.json"
        if matrix_path.is_file() and benchmark_manifest_path.is_file():
            frozen_hashes_match = (
                hashlib.sha256(matrix_path.read_bytes()).hexdigest()
                == manifest.get("matrix_sha256")
                and hashlib.sha256(benchmark_manifest_path.read_bytes()).hexdigest()
                == manifest.get("benchmark_manifest_sha256")
            )
        if protocol_path.is_file() and protocol_recorded:
            protocol_hash_matches = (
                hashlib.sha256(protocol_path.read_bytes()).hexdigest() == protocol_hash
            )
    per_case = {}
    automatic = manual = failed = unsupported = ambiguous = geometry = complete = 0
    manual_audit_pass = True
    success_geometry_pass = True
    for case_id in EXPECTED_CASE_IDS:
        case_dir = run_dir / "cases" / case_id
        audit = result_package.audit_case_package(case_dir)
        if audit["complete"]:
            complete += 1
        status_path = case_dir / "final_status.json"
        status = _read_json(status_path) if status_path.is_file() else {}
        terminal = status.get("terminal_status")
        if terminal == "automatic_success":
            automatic += 1
        elif terminal == "manual_success":
            manual += 1
            correction_path = case_dir / "sequence" / "manual_correction.json"
            if not correction_path.is_file():
                manual_audit_pass = False
            else:
                correction = _read_json(correction_path)
                manual_audit_pass &= correction.get("correction_count") == 1
        elif terminal == "failed":
            failed += 1
        elif terminal == "unsupported":
            unsupported += 1
        if status.get("ambiguous") is True:
            ambiguous += 1
        geometry_pass = False
        metrics_path = case_dir / "validation" / "validation_metrics.json"
        if metrics_path.is_file():
            geometry_pass = _read_json(metrics_path).get("geometry_pass") is True
        if geometry_pass:
            geometry += 1
        if terminal in {"automatic_success", "manual_success"} and not geometry_pass:
            success_geometry_pass = False
        per_case[case_id] = {
            "terminal_status": terminal,
            "geometry_pass": geometry_pass,
            "package_complete": audit["complete"],
            "missing": audit["missing"],
            "invalid": audit["invalid"],
        }
    checks = {
        "environment_present": environment_present,
        "environment_complete": environment_complete,
        "manifest_schema": manifest_schema,
        "git_commit_recorded": git_commit_recorded,
        "manifest_case_set": manifest_case_set,
        "git_clean_at_start": git_clean,
        "validation_protocol_recorded": protocol_recorded,
        "validation_protocol_hash_matches": protocol_hash_matches,
        "frozen_benchmark_hashes_match": frozen_hashes_match,
        "automatic_success_at_least_3": automatic >= 3,
        "all_five_successful": automatic + manual == 5,
        "manual_cases_have_one_audited_correction": manual_audit_pass,
        "successful_cases_geometry_pass": success_geometry_pass,
        "packages_complete_5_of_5": complete == 5,
        "supported_cases_not_relabelled_unsupported": unsupported == 0,
    }
    return {
        "verifier_schema": "gate3-verifier-0.1",
        "run_id": manifest.get("run_id"),
        "gate_pass": all(checks.values()),
        "target_automatic_at_least_4": automatic >= 4,
        "stop_loss_triggered": automatic < 3,
        "automatic_success_count": automatic,
        "manual_success_count": manual,
        "failed_count": failed,
        "unsupported_count": unsupported,
        "ambiguous_count": ambiguous,
        "geometry_pass_count": geometry,
        "package_complete_count": complete,
        "checks": checks,
        "per_case": per_case,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: verify_gate3.py <run_dir>")
    report = verify_run(argv[0])
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
