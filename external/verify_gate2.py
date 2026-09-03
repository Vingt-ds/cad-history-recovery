"""Audit Gate 2 package completeness and geometric success as separate facts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import result_package


EXPECTED_CASE_IDS = [f"D-S{index:02d}" for index in range(1, 11)]


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify_run(run_dir):
    run_dir = Path(run_dir)
    manifest = _read_json(run_dir / "manifest.json") or {}
    environment_exists = (run_dir / "environment.json").is_file()
    manifest_case_ids = manifest.get("case_ids")
    per_case = {}
    status_counts = {status: 0 for status in sorted(result_package.TERMINAL_STATUSES)}
    package_complete_count = 0
    geometry_pass_count = 0
    ambiguous_count = 0
    successful_geometry_failures = []

    for case_id in EXPECTED_CASE_IDS:
        case_dir = run_dir / "cases" / case_id
        audit = result_package.audit_case_package(case_dir)
        status = _read_json(case_dir / "final_status.json") or {}
        terminal = status.get("terminal_status")
        if audit["complete"]:
            package_complete_count += 1
        if terminal in status_counts:
            status_counts[terminal] += 1
        if status.get("ambiguous") is True:
            ambiguous_count += 1

        validation = _read_json(case_dir / "validation" / "validation_metrics.json")
        geometry_pass = isinstance(validation, dict) and validation.get("geometry_pass") is True
        if geometry_pass:
            geometry_pass_count += 1
        if terminal in {"automatic_success", "manual_success"} and not geometry_pass:
            successful_geometry_failures.append(case_id)
        per_case[case_id] = {
            "package_complete": audit["complete"],
            "terminal_status": terminal,
            "geometry_pass": geometry_pass if validation is not None else None,
            "missing": audit["missing"],
            "invalid": audit["invalid"],
        }

    checks = {
        "manifest_case_set": manifest_case_ids == EXPECTED_CASE_IDS,
        "environment_present": environment_exists,
        "git_clean_at_start": manifest.get("git_dirty_at_start") is False,
        "packages_complete_10_of_10": package_complete_count == 10,
        "automatic_success_at_least_8": status_counts["automatic_success"] >= 8,
        "successful_cases_geometry_pass": not successful_geometry_failures,
        "supported_cases_not_relabelled_unsupported": status_counts["unsupported"] == 0,
    }
    return {
        "verifier_schema": "gate2-verifier-0.1",
        "run_id": manifest.get("run_id"),
        "checks": checks,
        "package_complete_count": package_complete_count,
        "automatic_success_count": status_counts["automatic_success"],
        "manual_success_count": status_counts["manual_success"],
        "failed_count": status_counts["failed"],
        "unsupported_count": status_counts["unsupported"],
        "ambiguous_count": ambiguous_count,
        "geometry_pass_count": geometry_pass_count,
        "successful_geometry_failures": successful_geometry_failures,
        "per_case": per_case,
        "gate_pass": all(checks.values()),
    }


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        raise SystemExit("usage: verify_gate2.py <run_dir>")
    report = verify_run(arguments[0])
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
