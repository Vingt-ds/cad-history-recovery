"""Freeze the 30-case Gate 1 benchmark with immutable file hashes."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


class FreezeError(ValueError):
    """Raised when the benchmark cannot be frozen safely."""


def _write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_frozen_matrix(matrix_path, frozen_at):
    text = Path(matrix_path).read_text(encoding="utf-8")
    version_marker = '"matrix_version": "gate1-draft-0.1"'
    frozen_marker = '"frozen": false,'
    if version_marker not in text or frozen_marker not in text:
        raise FreezeError("case matrix is not an unfrozen gate1-draft-0.1 matrix")
    text = text.replace(version_marker, '"matrix_version": "gate1-frozen-0.1"', 1)
    text = text.replace(
        frozen_marker,
        f'"frozen": true, "frozen_at": "{frozen_at}",',
        1,
    )
    Path(matrix_path).write_text(text, encoding="utf-8")


def freeze_benchmark(matrix_path, project_root, frozen_at=None):
    root = Path(project_root)
    matrix_path = Path(matrix_path)
    manifest_path = root / "benchmarks" / "manifest.json"
    lock_path = root / "benchmarks" / "freeze.lock.json"
    if lock_path.exists():
        raise FreezeError(f"benchmark is already frozen: {lock_path}")

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    cases = matrix.get("cases", [])
    if len(cases) != 30:
        raise FreezeError("benchmark must contain exactly 30 cases")
    split_counts = Counter(case.get("split") for case in cases)
    if split_counts != {"development": 15, "held_out": 15}:
        raise FreezeError("benchmark must contain 15 development and 15 held_out cases")

    manifest_cases = []
    for case in cases:
        relative = case.get("output_step")
        step_path = root / relative
        if not step_path.is_file() or step_path.stat().st_size == 0:
            raise FreezeError(f"missing or empty STEP for {case.get('case_id')}: {relative}")
        manifest_cases.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "source": case["source"],
                "expected_scope": case["expected_scope"],
                "expected_behavior": case["expected_behavior"],
                "path": relative,
                "size_bytes": step_path.stat().st_size,
                "sha256": _sha256(step_path),
            }
        )

    frozen_at = frozen_at or datetime.now(timezone.utc).isoformat()
    _write_frozen_matrix(matrix_path, frozen_at)
    matrix["matrix_version"] = "gate1-frozen-0.1"
    matrix["frozen"] = True
    matrix["frozen_at"] = frozen_at
    matrix_sha256 = _sha256(matrix_path)

    manifest = {
        "manifest_version": "gate1-0.1",
        "matrix_version": matrix["matrix_version"],
        "units": matrix.get("units"),
        "frozen_at": frozen_at,
        "case_count": len(manifest_cases),
        "split_counts": dict(split_counts),
        "matrix_sha256": matrix_sha256,
        "held_out_policy": "excluded_from_rule_and_threshold_development_after_freeze",
        "cases": manifest_cases,
    }
    _write_json(manifest_path, manifest)
    manifest_sha256 = _sha256(manifest_path)

    lock = {
        "lock_version": "gate1-0.1",
        "frozen_at": frozen_at,
        "matrix_path": str(matrix_path.relative_to(root)).replace("\\", "/"),
        "matrix_sha256": matrix_sha256,
        "manifest_path": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "manifest_sha256": manifest_sha256,
        "generator_overwrite_allowed": False,
    }
    _write_json(lock_path, lock)
    return lock


def verify_frozen_benchmark(project_root):
    root = Path(project_root)
    matrix_path = root / "benchmarks" / "case_matrix.json"
    manifest_path = root / "benchmarks" / "manifest.json"
    lock_path = root / "benchmarks" / "freeze.lock.json"
    errors = []
    for path in (matrix_path, manifest_path, lock_path):
        if not path.is_file():
            errors.append(f"missing freeze artifact: {path.name}")
    if errors:
        return errors

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if not matrix.get("frozen"):
        errors.append("case_matrix.json is not marked frozen")
    if _sha256(matrix_path) != lock.get("matrix_sha256"):
        errors.append("case_matrix.json sha256 does not match lock")
    if _sha256(manifest_path) != lock.get("manifest_sha256"):
        errors.append("manifest.json sha256 does not match lock")
    for case in manifest.get("cases", []):
        step_path = root / case["path"]
        if not step_path.is_file():
            errors.append(f"{case.get('case_id')} STEP is missing")
            continue
        if step_path.stat().st_size != case.get("size_bytes"):
            errors.append(f"{case.get('case_id')} size does not match manifest")
        if _sha256(step_path) != case.get("sha256"):
            errors.append(f"{case.get('case_id')} sha256 does not match manifest")
    return errors


def main():
    root = Path(__file__).resolve().parents[1]
    lock = freeze_benchmark(root / "benchmarks" / "case_matrix.json", root)
    print(f"GATE1_BENCHMARK_FROZEN {lock['manifest_sha256']}")


if __name__ == "__main__":
    main()
