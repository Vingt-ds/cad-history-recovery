"""Build the immutable Gate 4 evaluation protocol bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import gate4_policy


SEMANTIC_FILES = (
    ".gitattributes",
    "config/gate2_validation_protocol.json",
    "config/gate3_validation_protocol.json",
    "external/brep_inspection.py",
    "external/candidate_validation.py",
    "external/extrusion_inference.py",
    "external/gate2_pipeline.py",
    "external/gate3_pipeline.py",
    "external/gate4_inference.py",
    "external/gate4_pipeline.py",
    "external/gate4_policy.py",
    "external/gate4_reporting.py",
    "external/gate4_validation.py",
    "external/geometry_validation.py",
    "external/profile_reconstruction.py",
    "external/result_package.py",
    "external/through_hole_inference.py",
    "external/through_hole_reconstruction.py",
    "external/topology_adjacency.py",
    "external/verify_gate4.py",
    "fusion_scripts/Gate1SequenceReplay/Gate1SequenceReplay.py",
    "fusion_scripts/Gate2SequenceReplay/Gate2SequenceReplay.py",
    "fusion_scripts/Gate4SequenceReplay/Gate4SequenceReplay.py",
)


class Gate4FreezeError(ValueError):
    pass


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def semantic_sha256(path):
    normalized = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _canonical_bytes(value):
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def build_freeze_records(project_root):
    root = Path(project_root).resolve()
    benchmark_manifest = root / "benchmarks" / "manifest.json"
    case_matrix = root / "benchmarks" / "case_matrix.json"
    inventory = gate4_policy.build_input_inventory(root)
    routing = {
        "routing_policy_schema": "gate4-routing-policy-0.1",
        "frozen": True,
        "semantic_inputs": [
            "step_geometry",
            "source_step_sha256",
            "work_directory",
            "frozen_gate2_protocol",
            "frozen_gate3_protocol",
        ],
        "forbidden_semantic_inputs": [
            "case_id",
            "filename",
            "parent_directory",
            "family",
            "expected_scope",
            "expected_behavior",
            "geometry_parameters",
        ],
        "decision_order": [
            "exactly_one_supported_inner_opening_and_cylindrical_void_pair_to_gate3",
            "hole_like_geometry_outside_gate3_scope_to_unsupported",
            "otherwise_gate2",
        ],
        "gate3_requires": [
            "one_accepted_through_hole_fact_group",
            "paired_planar_inner_circular_openings",
            "one_connecting_straight_cylindrical_face",
        ],
        "rename_and_parent_path_invariance_required": True,
    }
    evaluation = {
        "evaluation_protocol_schema": "gate4-evaluation-0.1",
        "frozen": True,
        "benchmark_manifest_sha256": _sha256(benchmark_manifest),
        "case_matrix_sha256": _sha256(case_matrix),
        "case_count": 30,
        "split_counts": {"development": 15, "held_out": 15},
        "formal_execution_order": ["development", "seal", "held_out", "seal"],
        "formal_runs_use_same_evaluation_commit": True,
        "held_out_execution_count": 1,
        "expected_labels_release": "after_both_raw_runs_are_sealed",
        "manual_correction_policy": "automatic_only",
        "geometry_pass_source": "frozen_gate2_or_gate3_protocol",
        "gate2_protocol_sha256": _sha256(
            root / "config" / "gate2_validation_protocol.json"
        ),
        "gate3_protocol_sha256": _sha256(
            root / "config" / "gate3_validation_protocol.json"
        ),
        "primary_volume_metric": "volume_iou",
        "symmetric_difference_ratio": "one_minus_volume_iou",
        "boolean_failure_volume_iou": None,
        "boolean_failure_fallback": "surface_only",
        "surface_only_role": "diagnostic_completion_only",
        "success_rate_is_gate_condition": False,
        "package_completeness_required": "30_of_30",
    }
    retry = {
        "retry_policy_schema": "gate4-retry-policy-0.1",
        "frozen": True,
        "retryable_failure_codes": sorted(gate4_policy.INFRASTRUCTURE_RETRY_CODES),
        "nonretryable_failure_codes": [
            "AMBIGUOUS_CANDIDATE_FAILURE",
            "FUSION_GEOMETRIC_OPERATION_FAILURE",
            "GEOMETRY_MISMATCH",
            "NO_SUPPORTED_HYPOTHESIS",
            "ROUTING_REJECTION",
            "SCHEMA_REJECTION",
            "VALIDATION_FAILURE",
        ],
        "requirements": [
            "preserve_first_attempt",
            "semantic_hash_inventory_unchanged",
            "formal_development_rerun_complete",
        ],
    }
    semantic_files = {}
    for relative in SEMANTIC_FILES:
        path = root / relative
        if not path.is_file():
            raise Gate4FreezeError(f"semantic_file_missing:{relative}")
        semantic_files[relative] = semantic_sha256(path)
    semantic = {
        "semantic_hash_inventory_schema": "gate4-semantic-hashes-0.1",
        "hash_mode": "sha256_lf_normalized_text",
        "files": semantic_files,
    }
    records = {
        "gate4_input_inventory.json": inventory,
        "gate4_routing_policy.json": routing,
        "gate4_evaluation_protocol.json": evaluation,
        "gate4_retry_policy.json": retry,
        "gate4_semantic_hash_inventory.json": semantic,
    }
    lock_files = {
        f"config/{name}": hashlib.sha256(_canonical_bytes(value)).hexdigest()
        for name, value in sorted(records.items())
    }
    records["gate4_freeze_lock.json"] = {
        "freeze_schema": "gate4-freeze-lock-0.1",
        "frozen": True,
        "evaluation_commit_binding": "containing_git_commit",
        "files": lock_files,
    }
    return records


def write_freeze_records(project_root, records):
    config = Path(project_root).resolve() / "config"
    paths = [config / name for name in records]
    if any(path.exists() for path in paths):
        raise Gate4FreezeError("freeze_artifact_exists")
    config.mkdir(parents=True, exist_ok=True)
    ordered = [path for path in paths if path.name != "gate4_freeze_lock.json"]
    ordered.append(config / "gate4_freeze_lock.json")
    for path in ordered:
        path.write_bytes(_canonical_bytes(records[path.name]))
    return ordered


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args(argv)
    records = build_freeze_records(args.project_root)
    written = write_freeze_records(args.project_root, records)
    print(
        json.dumps(
            {path.name: _sha256(path) for path in written},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
