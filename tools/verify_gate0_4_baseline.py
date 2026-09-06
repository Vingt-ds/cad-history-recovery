import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


TECHNICAL_BASELINE_COMMIT = "aafd082ccb296584364227ebc9203e44c7d13832"
GATE4_EVALUATION_COMMIT = "3d04273301cdacb8936707164f492427aab3273c"
BASELINE_ID = "gate0-4-frozen-baseline-v1"
MANIFEST_PATH = "config/gate0_4_baseline_manifest.json"
SCHEMA = "gate0-4-baseline-manifest-0.1"
TAG_MESSAGE_SHA256 = "f965d43b3aa3bc2d7cce528b42a833269e9fb24cd8790a50377292578d619ffe"
ALLOWED_PACK_PATHS = {
    "README.md",
    MANIFEST_PATH,
    "tools/verify_gate0_4_baseline.py",
    "tests/test_baseline_verifier.py",
    "docs/gate0_4_research_baseline.md",
    "docs/benchmark_v1_card.md",
    "docs/dr_li_gate0_4_technical_brief.md",
    "docs/superpowers/specs/2026-09-06-gate0-4-research-baseline-pack-design.md",
}
SELF_REFERENCE_KEYS = {
    "baseline_pack_commit",
    "containing_commit",
    "containing_git_commit",
    "tag_object_sha",
    "tag_object_sha256",
}


def validate_relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("invalid_relative_path")
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("invalid_relative_path")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("invalid_relative_path")
    return value


def git_blob_bytes(project_root, commit, relative_path):
    relative_path = validate_relative_path(relative_path)
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=Path(project_root),
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"git_blob_missing:{relative_path}")
    return completed.stdout


def normalize_tag_message(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes):
        raise TypeError("tag_message_must_be_text_or_bytes")
    normalized = value.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def _git(project_root, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=Path(project_root),
        capture_output=True,
        check=False,
    )


def _git_text(project_root, *arguments):
    completed = _git(project_root, *arguments)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout.decode("utf-8").strip()


def _canonical_json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def _artifact_entries(manifest):
    for section in (
        "benchmark_artifacts",
        "frozen_protocols",
        "verification_reports",
        "interpretation_documents",
        "design_provenance",
    ):
        entries = manifest.get(section, [])
        if isinstance(entries, list):
            yield from entries
    for run in manifest.get("formal_runs", []):
        if isinstance(run, dict):
            yield from run.get("artifacts", [])


def _add_check(checks, name, passed, detail):
    checks[name] = {"detail": detail, "pass": bool(passed)}


def _load_gate4_pipeline(project_root):
    external = str(Path(project_root) / "external")
    if external not in sys.path:
        sys.path.insert(0, external)
    import gate4_pipeline

    return gate4_pipeline


def _verify_report(entry, blob):
    gate = entry.get("gate")
    report_format = entry.get("format")
    if report_format == "markdown":
        text = blob.decode("utf-8")
        if gate == "gate0":
            return "Overall automated status: **PASS**" in text
        if gate == "gate1":
            return "Overall status: **PASS**" in text
        return False
    if report_format == "json":
        return json.loads(blob.decode("utf-8")).get("gate_pass") is True
    return False


def _tag_message_bytes(project_root, tag_name):
    raw = _git(project_root, "cat-file", "tag", tag_name)
    if raw.returncode != 0:
        raise ValueError("tag_missing")
    _, separator, message = raw.stdout.partition(b"\n\n")
    if not separator:
        raise ValueError("tag_message_missing")
    return message


def verify_baseline(project_root, require_tag=False):
    root = Path(project_root).resolve()
    checks = {}
    manifest = None
    head = None
    manifest_bytes = None

    try:
        head = _git_text(root, "rev-parse", "HEAD")
        manifest_bytes = git_blob_bytes(root, head, MANIFEST_PATH)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        canonical = manifest_bytes == _canonical_json_bytes(manifest)
        _add_check(checks, "canonical_manifest", canonical, "canonical JSON bytes")
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _add_check(checks, "canonical_manifest", False, str(exc))

    if manifest is not None:
        commit_pattern = re.compile(r"^[0-9a-f]{40}$")
        identity_ok = (
            manifest.get("baseline_manifest_schema") == SCHEMA
            and manifest.get("baseline_id") == BASELINE_ID
            and manifest.get("tag_name") == BASELINE_ID
            and manifest.get("tag_target_binding") == "containing_git_commit"
            and manifest.get("technical_baseline_commit") == TECHNICAL_BASELINE_COMMIT
            and manifest.get("gate4_evaluation_commit") == GATE4_EVALUATION_COMMIT
            and commit_pattern.fullmatch(
                str(manifest.get("technical_baseline_commit", ""))
            )
            and commit_pattern.fullmatch(
                str(manifest.get("gate4_evaluation_commit", ""))
            )
        )
        _add_check(checks, "manifest_identity", identity_ok, "fixed identities and commits")

        keys = set(_all_keys(manifest))
        offending_keys = sorted(keys & SELF_REFERENCE_KEYS)
        _add_check(
            checks,
            "self_reference_free",
            not offending_keys,
            offending_keys or "no self-reference fields",
        )

        entries = list(_artifact_entries(manifest))
        path_errors = []
        hash_errors = []
        blobs = {}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                path_errors.append(f"entry_{index}:not_object")
                continue
            path = entry.get("path")
            try:
                validate_relative_path(path)
            except ValueError:
                path_errors.append(str(path))
                continue
            source = entry.get("hash_source")
            if source == "technical_baseline_commit":
                commit = TECHNICAL_BASELINE_COMMIT
            elif source == "containing_git_commit":
                commit = head
            else:
                hash_errors.append(f"{path}:invalid_hash_source")
                continue
            try:
                blob = git_blob_bytes(root, commit, path)
                blobs[path] = blob
            except ValueError:
                path_errors.append(path)
                continue
            actual = hashlib.sha256(blob).hexdigest()
            expected = entry.get("sha256")
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                hash_errors.append(f"{path}:invalid_sha256")
            elif actual != expected:
                hash_errors.append(path)
        for run in manifest.get("formal_runs", []):
            directory = run.get("directory") if isinstance(run, dict) else None
            try:
                validate_relative_path(directory)
            except ValueError:
                path_errors.append(str(directory))
        _add_check(checks, "artifact_paths", not path_errors, path_errors or "all paths exist")
        _add_check(checks, "artifact_hashes", not hash_errors, hash_errors or "all hashes match")

        report_errors = []
        reports = manifest.get("verification_reports", [])
        seen_gates = set()
        for entry in reports if isinstance(reports, list) else []:
            path = entry.get("path") if isinstance(entry, dict) else None
            gate = entry.get("gate") if isinstance(entry, dict) else None
            seen_gates.add(gate)
            try:
                if path not in blobs or not _verify_report(entry, blobs[path]):
                    report_errors.append(str(gate))
            except (UnicodeDecodeError, json.JSONDecodeError):
                report_errors.append(str(gate))
        if seen_gates != {"gate0", "gate1", "gate2", "gate3", "gate4"}:
            report_errors.append("gate_set")
        _add_check(
            checks,
            "saved_gate_reports",
            not report_errors,
            report_errors or "Gate 0-4 saved reports PASS",
        )

        seal_errors = []
        try:
            gate4_pipeline = _load_gate4_pipeline(root)
            for run in manifest.get("formal_runs", []):
                if run.get("seal_required"):
                    directory = run.get("directory")
                    try:
                        validate_relative_path(directory)
                    except ValueError:
                        seal_errors.append(str(directory))
                        continue
                    result = gate4_pipeline.verify_seal(root / directory)
                    if not result.get("valid"):
                        seal_errors.append(f"{directory}:{result.get('reason')}")
        except (ImportError, OSError, ValueError) as exc:
            seal_errors.append(str(exc))
        _add_check(checks, "gate4_seals", not seal_errors, seal_errors or "both seals valid")

        non_duplication = manifest.get("non_duplication")
        expected_non_duplication = {
            "benchmark_inputs": "reference_only",
            "environment_snapshots": "reference_only",
            "result_packages": "reference_only",
        }
        _add_check(
            checks,
            "non_duplication",
            non_duplication == expected_non_duplication,
            "reference-only policy",
        )

        allowed_manifest = manifest.get("allowed_pack_paths")
        allowed_ok = isinstance(allowed_manifest, list) and set(allowed_manifest) == ALLOWED_PACK_PATHS
        try:
            changed = set(
                filter(
                    None,
                    _git_text(
                        root,
                        "diff",
                        "--name-only",
                        f"{TECHNICAL_BASELINE_COMMIT}..{head}",
                    ).splitlines(),
                )
            )
            diff_ok = changed == ALLOWED_PACK_PATHS
            unexpected = sorted(changed - ALLOWED_PACK_PATHS)
            missing = sorted(ALLOWED_PACK_PATHS - changed)
        except ValueError as exc:
            diff_ok = False
            unexpected = [str(exc)]
            missing = []
        _add_check(
            checks,
            "approved_diff_only",
            allowed_ok and diff_ok,
            {"unexpected": unexpected, "missing": missing}
            if unexpected or missing
            else "exact approved path set",
        )

        ancestor = _git(root, "merge-base", "--is-ancestor", TECHNICAL_BASELINE_COMMIT, head)
        _add_check(checks, "technical_ancestry", ancestor.returncode == 0, "HEAD descends from technical baseline")

        tag_info = manifest.get("tag_message", {})
        tag_contract_ok = (
            tag_info.get("normalization") == "utf8_lf_single_trailing_newline"
            and tag_info.get("sha256") == TAG_MESSAGE_SHA256
        )
        _add_check(checks, "tag_message_contract", tag_contract_ok, "fixed normalized message digest")

    status = _git(root, "status", "--porcelain")
    clean = status.returncode == 0 and not status.stdout.strip()
    _add_check(checks, "clean_worktree", clean, "clean Git worktree")

    tag_target = None
    if require_tag:
        tag_name = manifest.get("tag_name", BASELINE_ID) if manifest else BASELINE_ID
        tag_type = _git(root, "cat-file", "-t", f"refs/tags/{tag_name}")
        annotated = tag_type.returncode == 0 and tag_type.stdout.strip() == b"tag"
        _add_check(checks, "annotated_tag", annotated, "direct tag object type is tag")
        if annotated:
            try:
                tag_target = _git_text(root, "rev-parse", f"refs/tags/{tag_name}^{{commit}}")
                target_type = _git_text(root, "cat-file", "-t", tag_target)
                same_manifest = git_blob_bytes(root, tag_target, MANIFEST_PATH) == manifest_bytes
                _add_check(
                    checks,
                    "tag_contains_manifest",
                    target_type == "commit" and same_manifest and tag_target == head,
                    "tag peels to HEAD containing the same manifest",
                )
            except ValueError as exc:
                _add_check(checks, "tag_contains_manifest", False, str(exc))
            try:
                actual_tag_hash = hashlib.sha256(
                    normalize_tag_message(_tag_message_bytes(root, tag_name))
                ).hexdigest()
                expected_tag_hash = manifest.get("tag_message", {}).get("sha256")
                _add_check(
                    checks,
                    "tag_message",
                    actual_tag_hash == expected_tag_hash == TAG_MESSAGE_SHA256,
                    actual_tag_hash,
                )
            except (TypeError, UnicodeDecodeError, ValueError) as exc:
                _add_check(checks, "tag_message", False, str(exc))
        else:
            _add_check(checks, "tag_contains_manifest", False, "annotated tag unavailable")
            _add_check(checks, "tag_message", False, "annotated tag unavailable")

    failed = [name for name, result in checks.items() if not result["pass"]]
    return {
        "baseline_id": BASELINE_ID,
        "baseline_pass": not failed,
        "checks": checks,
        "failed_checks": failed,
        "manifest_path": MANIFEST_PATH,
        "tag_required": bool(require_tag),
        "tag_target_commit": tag_target,
        "verification_schema": "gate0-4-baseline-verification-0.1",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify the Gate 0-4 research baseline pack")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--require-tag", action="store_true")
    arguments = parser.parse_args(argv)
    report = verify_baseline(arguments.project_root, require_tag=arguments.require_tag)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["baseline_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
