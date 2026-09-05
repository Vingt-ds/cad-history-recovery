"""Audit Gate 4 protocol integrity separately from recovery success."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gate4_pipeline
import result_package


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(project_root, development_run, held_out_run):
    root = Path(project_root)
    development_run = Path(development_run)
    held_out_run = Path(held_out_run)
    development_manifest = _read_json(development_run / "manifest.json")
    held_out_manifest = _read_json(held_out_run / "manifest.json")
    commit = development_manifest.get("git_commit")
    checks = {}

    try:
        gate4_pipeline._verify_freeze(root)
        checks["freeze_integrity"] = True
    except Exception:
        checks["freeze_integrity"] = False
    checks["development_seal"] = gate4_pipeline.verify_seal(development_run).get(
        "valid", False
    )
    checks["held_out_seal"] = gate4_pipeline.verify_seal(held_out_run).get(
        "valid", False
    )
    checks["same_evaluation_commit"] = (
        isinstance(commit, str)
        and held_out_manifest.get("git_commit") == commit
    )
    checks["clean_start_snapshots"] = (
        development_manifest.get("git_dirty_at_start") is False
        and held_out_manifest.get("git_dirty_at_start") is False
    )
    checks["split_roles"] = (
        development_manifest.get("evaluation_split") == "development"
        and held_out_manifest.get("evaluation_split") == "held_out"
    )
    checks["label_firewall_at_run_time"] = (
        development_manifest.get("expected_labels_loaded") is False
        and held_out_manifest.get("expected_labels_loaded") is False
    )

    heldout_lock_path = root / "logs" / "gate4" / "heldout_execution_lock.json"
    try:
        lock = _read_json(heldout_lock_path)
        checks["held_out_single_execution"] = (
            lock.get("lock_schema") == "gate4-heldout-execution-lock-0.1"
            and lock.get("run_id") == held_out_manifest.get("run_id")
            and lock.get("evaluation_commit") == commit
            and lock.get("attempt_number") == 1
        )
    except (OSError, ValueError, json.JSONDecodeError):
        checks["held_out_single_execution"] = False

    package_complete_count = 0
    automatic_success_count = 0
    for run_dir, manifest in (
        (development_run, development_manifest),
        (held_out_run, held_out_manifest),
    ):
        for case_id in manifest.get("case_ids", []):
            case_dir = run_dir / "cases" / case_id
            audit = gate4_pipeline.audit_gate4_case_package(case_dir)
            package_complete_count += int(audit["complete"])
            try:
                status = _read_json(case_dir / "final_status.json")
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            automatic_success_count += int(
                status.get("terminal_status") == "automatic_success"
            )
    checks["package_completeness_30_of_30"] = package_complete_count == 30
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "verification_schema": "gate4-verification-0.1",
        "gate_pass": not failed,
        "checks": checks,
        "failed_checks": failed,
        "package_complete_count": package_complete_count,
        "automatic_success_count": automatic_success_count,
        "success_rate_is_gate_condition": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--development-run", required=True)
    parser.add_argument("--held-out-run", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = verify(args.project_root, args.development_run, args.held_out_run)
    if args.output:
        result_package._write_json(Path(args.output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
