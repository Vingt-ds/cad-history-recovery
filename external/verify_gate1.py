"""Verify the evidence required to close Gate 1."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from freeze_benchmark import verify_frozen_benchmark
from geometry_validation import inspect_step


def _check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_validator(root):
    path = root / "shared" / "sequence_validator.py"
    spec = importlib.util.spec_from_file_location("gate1_sequence_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load shared sequence validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_check(root):
    required = [
        "docs/sequence_schema_v0.1.md",
        "docs/third_party_and_references.md",
        "shared/sequence_validator.py",
        "fusion_scripts/Gate1SequenceReplay/Gate1SequenceReplay.py",
        "fusion_scripts/Gate1SequenceReplay/Gate1SequenceReplay.manifest",
        "sequences/known/box.json",
        "sequences/known/box_hole.json",
    ]
    missing = [relative for relative in required if not (root / relative).is_file()]
    return _check("required_artifacts", not missing, "all present" if not missing else f"missing={missing}")


def _sequence_check(root):
    try:
        validator = _load_validator(root)
        known = sorted((root / "sequences" / "known").glob("*.json"))
        invalid = sorted((root / "sequences" / "invalid").glob("*.json"))
        known_failures = [path.name for path in known if not validator.validate_sequence(_load_json(path))["valid"]]
        invalid_passes = [path.name for path in invalid if validator.validate_sequence(_load_json(path))["valid"]]
        passed = len(known) >= 2 and len(invalid) >= 4 and not known_failures and not invalid_passes
        detail = (
            f"known_valid={len(known) - len(known_failures)}/{len(known)}; "
            f"invalid_rejected={len(invalid) - len(invalid_passes)}/{len(invalid)}"
        )
        if known_failures or invalid_passes:
            detail += f"; known_failures={known_failures}; invalid_passes={invalid_passes}"
        return _check("schema_validation", passed, detail)
    except Exception as error:
        return _check("schema_validation", False, error)


def _frame_replay_check(root):
    names = [
        "box_xy_run01",
        "box_xz_run01",
        "box_yz_run01",
        "box_rx30_run01",
        "box_ry45_run01",
        "cylinder_xy_run01",
    ]
    try:
        logs = [_load_json(root / "replay_outputs" / f"{name}.json") for name in names]
        passed = all(
            log.get("status") == "success"
            and log.get("body_count") == 1
            and float(log.get("world_frame_max_error_mm", float("inf"))) <= 1e-6
            for log in logs
        )
        maximum = max(float(log["world_frame_max_error_mm"]) for log in logs)
        return _check("frame_replays", passed, f"success={sum(log.get('status') == 'success' for log in logs)}/6; max_world_error_mm={maximum}")
    except Exception as error:
        return _check("frame_replays", False, error)


def _semantic_behavior_check(root):
    try:
        hole = _load_json(root / "replay_outputs" / "box_hole_run02.json")
        fallback = _load_json(root / "replay_outputs" / "box_rx30_run02.json")
        preserved_failure = _load_json(root / "replay_outputs" / "box_hole_run01.json")
        cut = next(item for item in hole["operations"] if item["operation_id"] == "cut_hole")
        passed = (
            hole.get("status") == "success"
            and hole.get("replay_mode") == "semantic"
            and cut["volume_after_cm3"] < cut["volume_before_cm3"]
            and fallback.get("status") == "success"
            and fallback.get("replay_mode") == "absolute_fallback"
            and preserved_failure.get("status") == "failure"
            and preserved_failure.get("error_code") == "profile_count_mismatch"
        )
        return _check(
            "semantic_and_failure_evidence",
            passed,
            "semantic Cut reduced volume; explicit absolute fallback succeeded; first profile failure preserved",
        )
    except Exception as error:
        return _check("semantic_and_failure_evidence", False, error)


def _stability_check(root, family, expected_model, expected_faces):
    try:
        logs = []
        metrics = []
        for run in range(1, 4):
            stem = f"{family}_stability_run{run:02d}"
            for suffix in ("f3d", "step", "json"):
                path = root / "replay_outputs" / f"{stem}.{suffix}"
                if not path.is_file() or path.stat().st_size == 0:
                    raise FileNotFoundError(f"missing or empty {path.name}")
            logs.append(_load_json(root / "replay_outputs" / f"{stem}.json"))
            metrics.append(inspect_step(root / "replay_outputs" / f"{stem}.step"))

        signatures = {
            (
                round(item["volume_mm3"], 9),
                round(item["surface_area_mm2"], 9),
                tuple(round(item["bbox_mm"][key], 9) for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")),
            )
            for item in metrics
        }
        passed = (
            len(signatures) == 1
            and all(log.get("status") == "success" for log in logs)
            and all(log.get("model_id") == expected_model for log in logs)
            and all(log.get("body_count") == 1 and log.get("face_count") == expected_faces for log in logs)
            and len({log.get("sequence_sha256") for log in logs}) == 1
        )
        volume = metrics[0]["volume_mm3"]
        return _check(f"{family}_stability", passed, f"3/3 artifacts audited; geometry_signatures={len(signatures)}; volume_mm3={volume}")
    except Exception as error:
        return _check(f"{family}_stability", False, error)


def _freeze_check(root):
    try:
        errors = verify_frozen_benchmark(root)
        manifest = _load_json(root / "benchmarks" / "manifest.json")
        passed = not errors and manifest.get("case_count") == 30 and manifest.get("split_counts") == {"development": 15, "held_out": 15}
        return _check("benchmark_freeze", passed, "30 cases; 15 development; 15 held_out; all hashes match" if passed else errors)
    except Exception as error:
        return _check("benchmark_freeze", False, error)


def _baseline_check(root):
    try:
        baseline = _load_json(root / "logs" / "gate1_geometry_baseline.json")
        repeatability = baseline.get("repeatability", {})
        passed = (
            baseline.get("contract") == "calibration_only_no_general_acceptance_threshold"
            and repeatability.get("same_file_exact") is True
            and repeatability.get("roundtrip_exact") is True
            and "acceptance_threshold" not in baseline
        )
        p95 = baseline["roundtrip"]["surface_distance_mm"]["symmetric_p95_mm"]
        return _check("geometry_baseline", passed, f"self and roundtrip repeatable; calibration symmetric_p95_mm={p95}; no general threshold")
    except Exception as error:
        return _check("geometry_baseline", False, error)


def run_checks(project_root):
    root = Path(project_root)
    return [
        _artifact_check(root),
        _sequence_check(root),
        _frame_replay_check(root),
        _semantic_behavior_check(root),
        _stability_check(root, "box", "known_box", 6),
        _stability_check(root, "box_hole", "known_box_hole", 7),
        _freeze_check(root),
        _baseline_check(root),
    ]


def render_report(checks):
    passed_count = sum(check["passed"] for check in checks)
    status = "PASS" if passed_count == len(checks) else "FAIL"
    lines = [
        "# Gate 1 Verification Report",
        "",
        f"Overall status: **{status}** ({passed_count}/{len(checks)} checks passed)",
        "",
        "| Status | Check | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        mark = "PASS" if check["passed"] else "FAIL"
        detail = check["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {mark} | `{check['name']}` | {detail} |")
    return "\n".join(lines) + "\n"


def main():
    root = Path(__file__).resolve().parents[1]
    checks = run_checks(root)
    report = render_report(checks)
    (root / "logs" / "gate1_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
