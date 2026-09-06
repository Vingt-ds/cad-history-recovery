import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

try:
    import verify_gate0_4_baseline as baseline
except ImportError:
    baseline = None

import gate4_pipeline


TAG_MESSAGE = """Gate 0-4 frozen research baseline v1.

Contains:
- Gate 0-3 validated reconstruction pipeline
- Gate 4 frozen held-out evaluation
- sealed benchmark evidence references
- baseline manifest and research interpretation documents

This tag does not indicate general CAD-history recovery.
It represents a reproducible research baseline.
"""


def run_git(root, *arguments, input_bytes=None):
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        check=True,
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def commit_all(root, message):
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.name=Baseline Test",
        "-c",
        "user.email=baseline@example.invalid",
        "commit",
        "-m",
        message,
    )
    return run_git(root, "rev-parse", "HEAD").stdout.decode().strip()


def artifact_entry(root, commit, relative_path, role):
    blob = run_git(root, "show", f"{commit}:{relative_path}").stdout
    return {
        "hash_source": "technical_baseline_commit",
        "path": relative_path,
        "role": role,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def containing_entry(root, relative_path, role):
    return {
        "hash_source": "containing_git_commit",
        "path": relative_path,
        "role": role,
        "sha256": hashlib.sha256((root / relative_path).read_bytes()).hexdigest(),
    }


def create_sealed_run(root, run_id, split, commit):
    run_dir = root / "benchmark_results" / run_id
    case_ids = [f"{split}-{index:02d}" for index in range(15)]
    write_json(
        run_dir / "manifest.json",
        {
            "case_ids": case_ids,
            "evaluation_split": split,
            "git_commit": commit,
            "run_id": run_id,
        },
    )
    write_json(run_dir / "environment.json", {"fixture": True})
    for case_id in case_ids:
        case_dir = run_dir / "cases" / case_id
        write_json(
            case_dir / "metadata" / "input_metadata.json", {"valid_step": True}
        )
        write_json(case_dir / "analysis" / "brep_summary.json", {})
        write_json(case_dir / "analysis" / "inference_log.json", {})
        write_json(
            case_dir / "final_status.json",
            {
                "ambiguous": False,
                "not_applicable_reason": "fixture",
                "scope_rule": "fixture",
                "terminal_status": "unsupported",
            },
        )
    gate4_pipeline.seal_run(run_dir)


def build_repository(directory, manifest_mutator=None, tag_mode=None):
    root = Path(directory)
    run_git(root, "init")
    run_git(root, "config", "core.autocrlf", "false")

    technical_files = {
        "benchmarks/case_matrix.json": {"matrix": "fixture"},
        "benchmarks/manifest.json": {"manifest": "fixture"},
        "benchmarks/freeze.lock.json": {"frozen": True},
        "config/gate2_validation_protocol.json": {"gate": 2},
        "config/gate3_validation_protocol.json": {"gate": 3},
        "config/gate4_evaluation_protocol.json": {"gate": 4},
        "config/gate4_routing_policy.json": {"routing": "fixture"},
        "config/gate4_retry_policy.json": {"retry": "fixture"},
        "config/gate4_input_inventory.json": {"inputs": []},
        "config/gate4_semantic_hash_inventory.json": {"files": {}},
        "config/gate4_freeze_lock.json": {"frozen": True},
    }
    for relative_path, value in technical_files.items():
        write_json(root / relative_path, value)

    reports = {
        "logs/gate0_report.md": "Overall automated status: **PASS** (22/22 checks passed)\n",
        "logs/gate1_report.md": "Overall status: **PASS** (8/8 checks passed)\n",
        "benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json": json.dumps(
            {"gate_pass": True}, indent=2, sort_keys=True
        )
        + "\n",
        "benchmark_results/gate3-formal-20260904-8e8ae63/gate3_verification_report.json": json.dumps(
            {"gate_pass": True}, indent=2, sort_keys=True
        )
        + "\n",
        "logs/gate4/gate4_verification_report.json": json.dumps(
            {"failed_checks": [], "gate_pass": True}, indent=2, sort_keys=True
        )
        + "\n",
    }
    for relative_path, text in reports.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    technical = commit_all(root, "technical baseline seed")

    write_json(
        root
        / "benchmark_results/gate2-formal-20260903-e93dc2f/manifest.json",
        {"git_commit": technical, "run_id": "gate2-formal-20260903-e93dc2f"},
    )
    write_json(
        root
        / "benchmark_results/gate2-formal-20260903-e93dc2f/environment.json",
        {"fixture": True},
    )
    write_json(
        root
        / "benchmark_results/gate3-formal-20260904-8e8ae63/manifest.json",
        {"git_commit": technical, "run_id": "gate3-formal-20260904-8e8ae63"},
    )
    write_json(
        root
        / "benchmark_results/gate3-formal-20260904-8e8ae63/environment.json",
        {"fixture": True},
    )
    create_sealed_run(root, "gate4-development-formal-20260905", "development", technical)
    create_sealed_run(root, "gate4-held-out-formal-20260905", "held_out", technical)
    technical = commit_all(root, "complete technical baseline")

    design_path = (
        "docs/superpowers/specs/2026-09-06-gate0-4-research-baseline-pack-design.md"
    )
    design = root / design_path
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("# Baseline design\n", encoding="utf-8")
    commit_all(root, "design")

    pack_files = {
        "README.md": "# Baseline fixture\n",
        "tools/verify_gate0_4_baseline.py": "# fixture\n",
        "tests/test_baseline_verifier.py": "# fixture\n",
        "docs/gate0_4_research_baseline.md": "# Research baseline\n",
        "docs/benchmark_v1_card.md": "# Benchmark card\n",
        "docs/dr_li_gate0_4_technical_brief.md": "# Technical brief\n",
    }
    for relative_path, text in pack_files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    benchmark_paths = [
        "benchmarks/case_matrix.json",
        "benchmarks/manifest.json",
        "benchmarks/freeze.lock.json",
    ]
    protocol_paths = [
        "config/gate2_validation_protocol.json",
        "config/gate3_validation_protocol.json",
        "config/gate4_evaluation_protocol.json",
        "config/gate4_routing_policy.json",
        "config/gate4_retry_policy.json",
        "config/gate4_input_inventory.json",
        "config/gate4_semantic_hash_inventory.json",
        "config/gate4_freeze_lock.json",
    ]
    formal_runs = []
    run_specs = (
        ("gate2", "gate2-formal-20260903-e93dc2f", False),
        ("gate3", "gate3-formal-20260904-8e8ae63", False),
        ("gate4-development", "gate4-development-formal-20260905", True),
        ("gate4-held-out", "gate4-held-out-formal-20260905", True),
    )
    for gate, run_id, seal_required in run_specs:
        names = ["manifest.json", "environment.json"]
        if seal_required:
            names.append("seal.json")
        artifacts = [
            artifact_entry(
                root,
                technical,
                f"benchmark_results/{run_id}/{name}",
                f"{gate}_{name.replace('.', '_')}",
            )
            for name in names
        ]
        formal_runs.append(
            {
                "artifacts": artifacts,
                "directory": f"benchmark_results/{run_id}",
                "gate": gate,
                "run_id": run_id,
                "seal_required": seal_required,
            }
        )

    report_specs = (
        ("gate0", "logs/gate0_report.md", "markdown"),
        ("gate1", "logs/gate1_report.md", "markdown"),
        (
            "gate2",
            "benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json",
            "json",
        ),
        (
            "gate3",
            "benchmark_results/gate3-formal-20260904-8e8ae63/gate3_verification_report.json",
            "json",
        ),
        ("gate4", "logs/gate4/gate4_verification_report.json", "json"),
    )
    interpretation_paths = [
        "docs/gate0_4_research_baseline.md",
        "docs/benchmark_v1_card.md",
        "docs/dr_li_gate0_4_technical_brief.md",
    ]
    manifest = {
        "allowed_pack_paths": sorted(
            ["config/gate0_4_baseline_manifest.json", design_path, *pack_files]
        ),
        "baseline_id": "gate0-4-frozen-baseline-v1",
        "baseline_manifest_schema": "gate0-4-baseline-manifest-0.1",
        "benchmark_artifacts": [
            artifact_entry(root, technical, path, "frozen_benchmark")
            for path in benchmark_paths
        ],
        "design_provenance": [
            containing_entry(root, design_path, "baseline_pack_design")
        ],
        "formal_runs": formal_runs,
        "frozen_protocols": [
            artifact_entry(root, technical, path, "frozen_protocol")
            for path in protocol_paths
        ],
        "gate4_evaluation_commit": technical,
        "interpretation_documents": [
            containing_entry(root, path, "research_interpretation")
            for path in interpretation_paths
        ],
        "non_duplication": {
            "benchmark_inputs": "reference_only",
            "environment_snapshots": "reference_only",
            "result_packages": "reference_only",
        },
        "tag_message": {
            "normalization": "utf8_lf_single_trailing_newline",
            "sha256": hashlib.sha256(TAG_MESSAGE.encode("utf-8")).hexdigest(),
        },
        "tag_name": "gate0-4-frozen-baseline-v1",
        "tag_target_binding": "containing_git_commit",
        "technical_baseline_commit": technical,
        "verification_reports": [
            {
                **artifact_entry(root, technical, path, f"{gate}_verification"),
                "format": report_format,
                "gate": gate,
            }
            for gate, path, report_format in report_specs
        ],
    }
    if manifest_mutator is not None:
        manifest_mutator(manifest)
    write_json(root / "config/gate0_4_baseline_manifest.json", manifest)
    pack = commit_all(root, "baseline pack")

    if tag_mode == "annotated":
        run_git(
            root,
            "-c",
            "user.name=Baseline Test",
            "-c",
            "user.email=baseline@example.invalid",
            "tag",
            "-a",
            "gate0-4-frozen-baseline-v1",
            "-F",
            "-",
            pack,
            input_bytes=TAG_MESSAGE.encode("utf-8"),
        )
    elif tag_mode == "lightweight":
        run_git(root, "tag", "gate0-4-frozen-baseline-v1", pack)
    elif tag_mode == "wrong-target":
        run_git(
            root,
            "-c",
            "user.name=Baseline Test",
            "-c",
            "user.email=baseline@example.invalid",
            "tag",
            "-a",
            "gate0-4-frozen-baseline-v1",
            "-F",
            "-",
            technical,
            input_bytes=TAG_MESSAGE.encode("utf-8"),
        )
    elif tag_mode == "wrong-message":
        run_git(
            root,
            "-c",
            "user.name=Baseline Test",
            "-c",
            "user.email=baseline@example.invalid",
            "tag",
            "-a",
            "gate0-4-frozen-baseline-v1",
            "-m",
            "Gate 0-4 frozen research baseline v1.",
            pack,
        )
    return root, technical, pack


class BaselineVerifierArtifactTests(unittest.TestCase):
    def test_module_and_public_api_exist(self):
        self.assertIsNotNone(baseline)
        self.assertTrue(callable(baseline.validate_relative_path))
        self.assertTrue(callable(baseline.git_blob_bytes))
        self.assertTrue(callable(baseline.normalize_tag_message))
        self.assertTrue(callable(baseline.verify_baseline))


class BaselineVerifierPrimitiveTests(unittest.TestCase):
    def test_safe_relative_path_is_returned_unchanged(self):
        self.assertEqual(
            baseline.validate_relative_path("logs/gate4/report.json"),
            "logs/gate4/report.json",
        )

    def test_unsafe_paths_are_rejected(self):
        unsafe = (
            "../report.json",
            "logs/../report.json",
            "/absolute/report.json",
            "C:/absolute/report.json",
            "logs\\report.json",
            "logs//report.json",
            "./report.json",
            "logs/./report.json",
            "logs/report.json/",
            "",
        )
        for value in unsafe:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    baseline.validate_relative_path(value)

    def test_tag_message_normalization_is_utf8_lf_with_one_trailing_newline(self):
        self.assertEqual(
            baseline.normalize_tag_message(b"first\r\nsecond\r\n\r\n"),
            b"first\nsecond\n",
        )
        self.assertEqual(
            baseline.normalize_tag_message("first\nsecond"),
            b"first\nsecond\n",
        )

    def test_git_blob_bytes_ignore_working_tree_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "core.autocrlf", "false"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            evidence = root / "evidence.txt"
            evidence.write_bytes(b"first\nsecond\n")
            subprocess.run(
                ["git", "add", "evidence.txt"], cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Baseline Test",
                    "-c",
                    "user.email=baseline@example.invalid",
                    "commit",
                    "-m",
                    "technical baseline",
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            evidence.write_bytes(b"first\r\nsecond\r\n")

            blob = baseline.git_blob_bytes(root, commit, "evidence.txt")

        self.assertEqual(blob, b"first\nsecond\n")


class BaselineVerifierRepositoryTests(unittest.TestCase):
    def verify_fixture(self, root, technical, require_tag=False):
        with patch.object(baseline, "TECHNICAL_BASELINE_COMMIT", technical), patch.object(
            baseline, "GATE4_EVALUATION_COMMIT", technical
        ):
            return baseline.verify_baseline(root, require_tag=require_tag)

    def test_valid_pack_commit_passes_pre_tag_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory)
            report = self.verify_fixture(root, technical)

        self.assertTrue(report["baseline_pass"])
        self.assertEqual(report["failed_checks"], [])
        self.assertFalse(report["tag_required"])

    def test_wrong_artifact_sha_is_rejected(self):
        def mutate(manifest):
            manifest["benchmark_artifacts"][0]["sha256"] = "0" * 64

        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, mutate)
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("artifact_hashes", report["failed_checks"])

    def test_missing_evidence_is_rejected(self):
        def mutate(manifest):
            manifest["benchmark_artifacts"][0]["path"] = "benchmarks/missing.json"

        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, mutate)
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("artifact_paths", report["failed_checks"])

    def test_unsafe_formal_run_directory_is_rejected(self):
        def mutate(manifest):
            manifest["formal_runs"][0]["directory"] = "../outside"

        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, mutate)
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("artifact_paths", report["failed_checks"])

    def test_manifest_self_reference_is_rejected(self):
        def mutate(manifest):
            manifest["baseline_pack_commit"] = "f" * 40

        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, mutate)
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("self_reference_free", report["failed_checks"])

    def test_change_to_frozen_protocol_after_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory)
            write_json(root / "config/gate2_validation_protocol.json", {"changed": True})
            commit_all(root, "illegal protocol change")
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("approved_diff_only", report["failed_checks"])

    def test_missing_required_pack_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory)
            (root / "README.md").unlink()
            commit_all(root, "remove required baseline entry")
            report = self.verify_fixture(root, technical)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("approved_diff_only", report["failed_checks"])

    def test_lightweight_tag_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, tag_mode="lightweight")
            report = self.verify_fixture(root, technical, require_tag=True)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("annotated_tag", report["failed_checks"])

    def test_annotated_tag_with_wrong_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, tag_mode="wrong-target")
            report = self.verify_fixture(root, technical, require_tag=True)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("tag_contains_manifest", report["failed_checks"])

    def test_annotated_tag_with_partial_message_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, _ = build_repository(directory, tag_mode="wrong-message")
            report = self.verify_fixture(root, technical, require_tag=True)

        self.assertFalse(report["baseline_pass"])
        self.assertIn("tag_message", report["failed_checks"])

    def test_exact_annotated_tag_passes_post_tag_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root, technical, pack = build_repository(directory, tag_mode="annotated")
            report = self.verify_fixture(root, technical, require_tag=True)

        self.assertTrue(report["baseline_pass"])
        self.assertEqual(report["tag_target_commit"], pack)
        self.assertEqual(report["failed_checks"], [])


if __name__ == "__main__":
    unittest.main()
