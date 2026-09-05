"""Frozen-evaluation policy helpers for Gate 4 orchestration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


INFRASTRUCTURE_RETRY_CODES = {
    "FUSION_LAUNCH_FAILURE",
    "PATH_IO_FAILURE",
    "EXPORT_IO_FAILURE",
    "LOGGING_FAILURE",
    "PACKAGE_WRITE_FAILURE",
}


class Gate4PolicyError(ValueError):
    pass


def is_retryable(failure_code):
    return failure_code in INFRASTRUCTURE_RETRY_CODES


def authorize_retry(
    failure_code,
    first_attempt_path,
    semantic_hashes_before,
    semantic_hashes_after,
    development_rerun_complete,
):
    if not is_retryable(failure_code):
        raise Gate4PolicyError("failure_code_not_retryable")
    if not Path(first_attempt_path).is_file():
        raise Gate4PolicyError("first_attempt_not_preserved")
    if semantic_hashes_before != semantic_hashes_after:
        raise Gate4PolicyError("semantic_hash_inventory_changed")
    if development_rerun_complete is not True:
        raise Gate4PolicyError("development_rerun_required")
    return True


def build_input_inventory(project_root):
    root = Path(project_root)
    manifest_path = root / "benchmarks" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    units = manifest.get("units")
    cases = [
        {
            "case_id": case["case_id"],
            "split": case["split"],
            "source": case["source"],
            "units": units,
            "path": Path(case["path"]).as_posix(),
            "sha256": case["sha256"],
        }
        for case in manifest.get("cases", [])
    ]
    cases.sort(key=lambda case: case["case_id"])
    if len(cases) != 30 or len({case["case_id"] for case in cases}) != 30:
        raise Gate4PolicyError("input_inventory_case_count_mismatch")
    return {
        "input_inventory_schema": "gate4-input-inventory-0.1",
        "benchmark_manifest_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "cases": cases,
    }


def select_cases(inventory, split):
    if inventory.get("input_inventory_schema") != "gate4-input-inventory-0.1":
        raise Gate4PolicyError("input_inventory_schema_mismatch")
    if split not in {"development", "held_out"}:
        raise Gate4PolicyError("invalid_evaluation_split")
    selected = [dict(case) for case in inventory.get("cases", []) if case.get("split") == split]
    selected.sort(key=lambda case: case["case_id"])
    if len(selected) != 15 or len({case["case_id"] for case in selected}) != 15:
        raise Gate4PolicyError("evaluation_split_case_count_mismatch")
    return selected
