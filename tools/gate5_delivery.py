"""Generate and verify the local Gate 5 delivery-package manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_NAME = "gate5-delivery-v1_20260924"
BASELINE_TAG = "gate0-4-frozen-baseline-v1"
DELIVERY_TAG = "gate5-delivery-v1"
PPT = "slides/gate5_delivery_v1.pptx"
NON_PPT_ASSETS = (
    "README_DELIVERY.md",
    "videos/demo_01_single_extrusion_v1.mp4",
    "videos/demo_02_through_hole_v1.mp4",
    "videos/demo_03_ambiguity_v1.mp4",
    "screenshots/demo_01_single_extrusion_v1.png",
    "screenshots/demo_02_through_hole_v1.png",
    "screenshots/demo_03_ambiguity_v1.png",
)
CONTROL_FILES = {"submission_manifest.json", "SHA256SUMS.txt"}


class Gate5DeliveryError(ValueError):
    """Raised when the local delivery package violates its contract."""


def _run_git(root, *arguments):
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise Gate5DeliveryError("git_reference_invalid") from exc


def audit_readme_diff(project_root):
    """Reject claim-bearing language added after the frozen baseline README."""

    root = Path(project_root).resolve()
    diff = _run_git(
        root,
        "diff",
        "--unified=0",
        BASELINE_TAG,
        "--",
        "README.md",
    )
    forbidden = re.compile(
        r"\b(?:accuracy|success[ -]rate|improved|generali[sz](?:e|ation)|state-of-the-art)\b",
        re.IGNORECASE,
    )
    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    violations = [line for line in added if forbidden.search(line)]
    return {"valid": not violations, "violations": violations}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _package_path(project_root, package_dir):
    root = Path(project_root).resolve()
    package = Path(package_dir)
    if not package.is_absolute():
        package = root / package
    package = package.resolve()
    expected = (root / "delivery_package" / PACKAGE_NAME).resolve()
    if package != expected:
        raise Gate5DeliveryError("invalid_package_path")
    ignored = subprocess.run(
        ["git", "-c", "core.excludesFile=NUL", "check-ignore", "--quiet", str(package)],
        cwd=root,
        capture_output=True,
    ).returncode == 0
    if not ignored:
        raise Gate5DeliveryError("package_not_ignored")
    return root, package


def _mode_assets(mode):
    if mode not in {"preflight", "final"}:
        raise Gate5DeliveryError("invalid_mode")
    return NON_PPT_ASSETS + ((PPT,) if mode == "final" else ())


def _tag_info(root, tag, *, required):
    exists = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"], cwd=root
    ).returncode == 0
    if not exists:
        if required:
            raise Gate5DeliveryError("delivery_tag_missing")
        return {"exists": False, "annotated": False, "commit": None}
    object_type = _run_git(root, "cat-file", "-t", tag)
    if object_type != "tag":
        if required:
            raise Gate5DeliveryError("annotated_tag_required")
        return {"exists": True, "annotated": False, "commit": _run_git(root, "rev-parse", f"{tag}^{{commit}}")}
    return {
        "exists": True,
        "annotated": True,
        "commit": _run_git(root, "rev-parse", f"{tag}^{{commit}}"),
    }


def _asset_metadata(relative, path):
    case_match = re.search(r"demo_0[123]_(?:single_extrusion|through_hole|ambiguity)_v1", relative)
    case_id = None
    if case_match:
        case_id = {"demo_01": "D-S04", "demo_02": "D-H01", "demo_03": "D-S01"}[relative.split("/")[-1][:7]]
    if relative == PPT:
        role = "slide_deck"
    elif relative.startswith("videos/"):
        role = "technical_backup_video"
    elif relative.startswith("screenshots/"):
        role = "verified_demo_screenshot"
    else:
        role = "delivery_readme"
    return {
        "path": relative,
        "role": role,
        "case_id": case_id,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _assert_assets(package, mode):
    expected = set(_mode_assets(mode))
    if mode == "final" and not (package / PPT).is_file():
        raise Gate5DeliveryError("ppt_missing")
    missing = sorted(relative for relative in expected if not (package / relative).is_file())
    if missing:
        raise Gate5DeliveryError("required_asset_missing:" + ",".join(missing))
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.name not in CONTROL_FILES
    }
    extra = sorted(actual - expected)
    if extra:
        raise Gate5DeliveryError("unregistered_asset:" + ",".join(extra))
    return sorted(expected)


def generate_manifest(project_root, package_dir, *, mode):
    """Write canonical manifest and checksums for the fixed local package layout."""

    root, package = _package_path(project_root, package_dir)
    readme_audit = audit_readme_diff(root)
    if not readme_audit["valid"]:
        raise Gate5DeliveryError("readme_claim_violation")
    assets = _assert_assets(package, mode)
    head = _run_git(root, "rev-parse", "HEAD")
    baseline = _tag_info(root, BASELINE_TAG, required=True)
    if not baseline["annotated"]:
        raise Gate5DeliveryError("baseline_annotated_tag_required")
    delivery = _tag_info(root, DELIVERY_TAG, required=mode == "final")
    if mode == "final" and delivery["commit"] != head:
        raise Gate5DeliveryError("tag_target_mismatch")
    try:
        github_url = _run_git(root, "remote", "get-url", "origin")
    except Gate5DeliveryError:
        github_url = None
    manifest = {
        "package_schema": "gate5-delivery-package-0.1",
        "package_id": PACKAGE_NAME,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "github_url": github_url,
        "baseline": {"tag": BASELINE_TAG, "commit": baseline["commit"]},
        "delivery": {
            "tag": DELIVERY_TAG,
            "commit": head,
            "tag_verified": bool(delivery["annotated"] and delivery["commit"] == head),
        },
        "assets": [_asset_metadata(relative, package / relative) for relative in assets],
        "non_duplication": {
            "source_code": "reference_only",
            "benchmark_inputs": "reference_only",
            "formal_result_packages": "reference_only",
        },
    }
    manifest_path = package / "submission_manifest.json"
    _write_json(manifest_path, manifest)
    checksummed = assets + ["submission_manifest.json"]
    lines = [f"{_sha256(package / relative)}  {relative}" for relative in checksummed]
    (package / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def verify_package(project_root, package_dir, *, mode):
    """Read-only verification of package contents, hashes and Git provenance."""

    root, package = _package_path(project_root, package_dir)
    errors = []
    if not audit_readme_diff(root)["valid"]:
        errors.append("readme_claim_violation")
    try:
        expected_assets = set(_mode_assets(mode))
    except Gate5DeliveryError as exc:
        return {"valid": False, "errors": [str(exc)]}
    manifest_path = package / "submission_manifest.json"
    sums_path = package / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        return {"valid": False, "errors": ["control_file_missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"valid": False, "errors": ["manifest_invalid"]}
    actual_files = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
    }
    allowed = expected_assets | CONTROL_FILES
    if actual_files != allowed:
        errors.append("file_inventory_mismatch")
    if any(part in {"benchmarks", "benchmark_results"} for path in actual_files for part in Path(path).parts):
        errors.append("copied_research_artifact")
    entries = manifest.get("assets")
    if not isinstance(entries, list) or {entry.get("path") for entry in entries if isinstance(entry, dict)} != expected_assets:
        errors.append("asset_inventory_mismatch")
        entries = []
    for entry in entries:
        path = package / entry["path"]
        if not path.is_file():
            errors.append(f"missing:{entry['path']}")
        elif _sha256(path) != entry.get("sha256") or path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"hash_or_size:{entry['path']}")
    sums = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if "  " not in line:
            errors.append("checksums_format")
            continue
        digest, relative = line.split("  ", 1)
        sums[relative] = digest
    for relative in sorted(expected_assets | {"submission_manifest.json"}):
        path = package / relative
        if not path.is_file() or sums.get(relative) != _sha256(path):
            errors.append(f"checksums:{relative}")
    if manifest.get("mode") != mode:
        errors.append("mode_mismatch")
    if manifest.get("non_duplication") != {
        "source_code": "reference_only",
        "benchmark_inputs": "reference_only",
        "formal_result_packages": "reference_only",
    }:
        errors.append("non_duplication")
    try:
        baseline = _tag_info(root, BASELINE_TAG, required=True)
        if manifest.get("baseline") != {"tag": BASELINE_TAG, "commit": baseline["commit"]}:
            errors.append("baseline_reference")
        if mode == "final":
            delivery = _tag_info(root, DELIVERY_TAG, required=True)
            head = _run_git(root, "rev-parse", "HEAD")
            if not delivery["annotated"] or delivery["commit"] != head:
                errors.append("delivery_tag")
            if manifest.get("delivery", {}).get("commit") != head:
                errors.append("delivery_commit")
    except Gate5DeliveryError as exc:
        errors.append(str(exc))
    return {"valid": not errors, "mode": mode, "errors": sorted(set(errors))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--mode", choices=("preflight", "final"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_manifest(args.project_root, args.package_dir, mode=args.mode)
        else:
            result = verify_package(args.project_root, args.package_dir, mode=args.mode)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("valid", True) else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
