"""Audit Gate 4 protocol integrity separately from recovery success."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import gate4_pipeline
import result_package


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _git_blob(project_root, commit, relative):
    if re.fullmatch(r"[0-9a-f]{40}", commit or "") is None:
        raise ValueError("invalid_evaluation_commit")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid_frozen_path")
    return subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        cwd=project_root,
        check=True,
        capture_output=True,
    ).stdout


def _freeze_integrity_at_commit(project_root, commit):
    lock = json.loads(
        _git_blob(project_root, commit, "config/gate4_freeze_lock.json")
    )
    if (
        lock.get("freeze_schema") != "gate4-freeze-lock-0.1"
        or lock.get("frozen") is not True
        or lock.get("evaluation_commit_binding") != "containing_git_commit"
    ):
        return False
    files = lock.get("files")
    if not isinstance(files, dict):
        return False
    for relative, expected in files.items():
        if hashlib.sha256(_git_blob(project_root, commit, relative)).hexdigest() != expected:
            return False
    semantic = json.loads(
        _git_blob(
            project_root,
            commit,
            "config/gate4_semantic_hash_inventory.json",
        )
    )
    if (
        semantic.get("semantic_hash_inventory_schema")
        != "gate4-semantic-hashes-0.1"
        or semantic.get("hash_mode") != "sha256_lf_normalized_text"
        or not isinstance(semantic.get("files"), dict)
        or not semantic["files"]
    ):
        return False
    for relative, expected in semantic["files"].items():
        normalized = (
            _git_blob(project_root, commit, relative)
            .replace(b"\r\n", b"\n")
            .replace(b"\r", b"\n")
        )
        if hashlib.sha256(normalized).hexdigest() != expected:
            return False
    return True


def _freeze_integrity(project_root, commit):
    try:
        gate4_pipeline._verify_freeze(project_root)
        return True
    except Exception:
        try:
            return _freeze_integrity_at_commit(project_root, commit)
        except Exception:
            return False


def verify(project_root, development_run, held_out_run):
    root = Path(project_root)
    development_run = Path(development_run)
    held_out_run = Path(held_out_run)
    development_manifest = _read_json(development_run / "manifest.json")
    held_out_manifest = _read_json(held_out_run / "manifest.json")
    commit = development_manifest.get("git_commit")
    checks = {}

    checks["freeze_integrity"] = _freeze_integrity(root, commit)
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
