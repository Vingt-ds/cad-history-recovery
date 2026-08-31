"""Create the automated Gate 0 PASS/FAIL report."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gate0_common import ConfigError, load_gate0_config, sha256_file


REQUIRED_ARTIFACTS = (
    "models/manual_box_hole.f3d",
    "models/manual_box_hole.step",
    "models/manual_box_hole_reimported.f3d",
    "models/fusion_script_box_run01.step",
    "models/fusion_script_box_run02.step",
    "models/cadquery_box.step",
    "evidence/01_original_timeline.png",
    "evidence/02_reimported_timeline.png",
    "evidence/export_settings.md",
    "docs/gate0_reuse_audit.md",
    "environment/environment.yml",
    "environment/pip-freeze.txt",
    "logs/fusion_run01.json",
    "logs/fusion_run02.json",
    "logs/external_python.json",
)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "top-level JSON value is not an object"
    return value, None


def _is_nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def verify_project(root: str | Path) -> list[Check]:
    project_root = Path(root).resolve()
    checks: list[Check] = []

    config_path = project_root / "config" / "gate0_box.json"
    try:
        load_gate0_config(config_path)
        config_hash = sha256_file(config_path)
        checks.append(Check("shared_config", True, f"valid; SHA-256={config_hash}"))
    except (ConfigError, OSError) as exc:
        config_hash = None
        checks.append(Check("shared_config", False, str(exc)))

    for relative in REQUIRED_ARTIFACTS:
        path = project_root / relative
        present = _is_nonempty(path)
        detail = f"{path.stat().st_size} bytes" if present else "missing or empty"
        checks.append(Check(f"artifact:{relative}", present, detail))

    evidence_path = project_root / "evidence" / "export_settings.md"
    try:
        evidence_text = evidence_path.read_text(encoding="utf-8")
    except OSError as exc:
        evidence_text = ""
        evidence_detail = str(exc)
    else:
        evidence_detail = "manual export record and both visual reviews marked PASS"
    evidence_passed = (
        "PENDING" not in evidence_text
        and "Original timeline visual review: PASS" in evidence_text
        and "Reimported timeline visual review: PASS" in evidence_text
        and "Fusion version:" in evidence_text
        and "STEP export" in evidence_text
    )
    checks.append(Check("manual_evidence_record", evidence_passed, evidence_detail))

    environment_yml = project_root / "environment" / "environment.yml"
    pip_freeze = project_root / "environment" / "pip-freeze.txt"
    try:
        environment_text = environment_yml.read_text(encoding="utf-8")
        freeze_text = pip_freeze.read_text(encoding="utf-8")
    except OSError as exc:
        environment_passed = False
        environment_detail = str(exc)
    else:
        normalized_environment = environment_text.replace(" ", "").lower()
        normalized_freeze = freeze_text.lower()
        environment_passed = (
            "PENDING" not in environment_text
            and "PENDING" not in freeze_text
            and "name: cadseq" in environment_text
            and "python=3.11" in normalized_environment
            and (
                "cadquery=2.8.0" in normalized_environment
                or "cadquery==2.8.0" in normalized_freeze
            )
            and (
                "cadquery==2.8.0" in normalized_freeze
                or "cadquery @ " in normalized_freeze
            )
        )
        environment_detail = "Conda history and pip records present; OCP version is verified by external smoke log"
    checks.append(Check("environment_record", environment_passed, environment_detail))

    fusion_logs: list[dict[str, Any]] = []
    for run_id in ("run01", "run02"):
        log_path = project_root / "logs" / f"fusion_{run_id}.json"
        data, error = _read_json(log_path)
        passed = bool(
            data
            and data.get("status") == "success"
            and data.get("run_id") == run_id
            and data.get("body_count") == 1
            and data.get("face_count") == 6
            and data.get("fusion_version")
            and data.get("python_version")
        )
        detail = error or (
            f"status={data.get('status')}, bodies={data.get('body_count')}, faces={data.get('face_count')}"
            if data
            else "unreadable log"
        )
        checks.append(Check(f"fusion_{run_id}", passed, detail))
        if data:
            fusion_logs.append(data)

    external_path = project_root / "logs" / "external_python.json"
    external, external_error = _read_json(external_path)
    required_external_checks = {
        "cadquery_box": (1, 6, 12),
        "fusion_run01": (1, 6, None),
        "fusion_run02": (1, 6, None),
        "manual_box_hole": (1, None, None),
    }
    external_passed = bool(external and external.get("status") == "success")
    external_details: list[str] = []
    if external:
        versions = external.get("versions", {})
        if not all(versions.get(key) for key in ("python", "cadquery", "cadquery_ocp")):
            external_passed = False
            external_details.append("missing Python/CadQuery/OCP version")
        recorded = external.get("checks", {})
        for name, expected in required_external_checks.items():
            item = recorded.get(name, {})
            solid_count, face_count, edge_count = expected
            item_ok = item.get("valid") is True and item.get("solid_count") == solid_count
            if face_count is not None:
                item_ok = item_ok and item.get("face_count") == face_count
            if edge_count is not None:
                item_ok = item_ok and item.get("edge_count") == edge_count
            if not item_ok:
                external_passed = False
                external_details.append(f"{name} failed expected topology/validity")
    checks.append(
        Check(
            "external_python",
            external_passed,
            external_error or "; ".join(external_details) or "all four STEP checks passed",
        )
    )

    recorded_hashes = [item.get("json_sha256") for item in fusion_logs]
    if external:
        recorded_hashes.append(external.get("json_sha256"))
    hash_passed = bool(
        config_hash
        and len(recorded_hashes) == 3
        and all(value == config_hash for value in recorded_hashes)
    )
    checks.append(
        Check(
            "shared_json_hash",
            hash_passed,
            f"config={config_hash}; recorded={recorded_hashes}",
        )
    )
    return checks


def render_report(checks: list[Check]) -> str:
    passed = sum(check.passed for check in checks)
    status = "PASS" if passed == len(checks) else "FAIL"
    lines = [
        "# Gate 0 Verification Report",
        "",
        f"Overall automated status: **{status}** ({passed}/{len(checks)} checks passed)",
        "",
        "> Timeline screenshots require separate visual review; file presence alone is not visual approval.",
        "",
        "| Status | Check | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        detail = check.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {marker} | `{check.name}` | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    checks = verify_project(args.project_root)
    report = render_report(checks)
    report_path = args.report or args.project_root / "logs" / "gate0_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
