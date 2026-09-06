import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import gate5_delivery


def run_git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def create_repo(directory):
    root = Path(directory)
    run_git(root, "init", "-b", "main")
    run_git(root, "config", "user.name", "Gate 5 Test")
    run_git(root, "config", "user.email", "gate5@example.invalid")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text("delivery_package/\n", encoding="utf-8")
    run_git(root, "add", "README.md", ".gitignore")
    run_git(root, "commit", "-m", "baseline")
    baseline = run_git(root, "rev-parse", "HEAD")
    run_git(root, "tag", "-a", "gate0-4-frozen-baseline-v1", "-m", "baseline")
    run_git(root, "remote", "add", "origin", "https://example.invalid/private/cad.git")
    return root, baseline


def create_package(root, *, include_ppt=False):
    package = root / "delivery_package" / "gate5-delivery-v1_20260924"
    files = {
        "README_DELIVERY.md": b"Gate 5 local delivery package.\n",
        "videos/demo_01_single_extrusion_v1.mp4": b"video-1",
        "videos/demo_02_through_hole_v1.mp4": b"video-2",
        "videos/demo_03_ambiguity_v1.mp4": b"video-3",
        "screenshots/demo_01_single_extrusion_v1.png": b"png-1",
        "screenshots/demo_02_through_hole_v1.png": b"png-2",
        "screenshots/demo_03_ambiguity_v1.png": b"png-3",
    }
    if include_ppt:
        files["slides/gate5_delivery_v1.pptx"] = b"pptx"
    for relative, data in files.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return package


class Gate5DeliveryTests(unittest.TestCase):
    def test_readme_diff_audit_rejects_new_delivery_overclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            (root / "README.md").write_text(
                "baseline\nGate 5 improved accuracy and generalization.\n",
                encoding="utf-8",
            )

            report = gate5_delivery.audit_readme_diff(root)

        self.assertFalse(report["valid"])
        self.assertEqual(
            report["violations"],
            ["Gate 5 improved accuracy and generalization."],
        )

    def test_preflight_rejects_readme_overclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            package = create_package(root)
            (root / "README.md").write_text(
                "baseline\nGate 5 has a new success rate.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                gate5_delivery.Gate5DeliveryError, "readme_claim_violation"
            ):
                gate5_delivery.generate_manifest(root, package, mode="preflight")

    def test_preflight_verifier_rejects_readme_overclaim_added_after_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            package = create_package(root)
            gate5_delivery.generate_manifest(root, package, mode="preflight")
            (root / "README.md").write_text(
                "baseline\nState-of-the-art delivery result.\n",
                encoding="utf-8",
            )

            report = gate5_delivery.verify_package(root, package, mode="preflight")

        self.assertFalse(report["valid"])
        self.assertIn("readme_claim_violation", report["errors"])

    def test_preflight_generates_and_verifies_non_ppt_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root, baseline = create_repo(directory)
            package = create_package(root)
            manifest = gate5_delivery.generate_manifest(root, package, mode="preflight")
            report = gate5_delivery.verify_package(root, package, mode="preflight")
            sums_exists = (package / "SHA256SUMS.txt").is_file()

        self.assertEqual(manifest["baseline"]["commit"], baseline)
        self.assertEqual(manifest["baseline"]["tag"], "gate0-4-frozen-baseline-v1")
        self.assertEqual(manifest["delivery"]["tag"], "gate5-delivery-v1")
        self.assertFalse(manifest["delivery"]["tag_verified"])
        self.assertEqual(manifest["non_duplication"]["benchmark_inputs"], "reference_only")
        self.assertTrue(report["valid"])
        self.assertTrue(sums_exists)

    def test_final_requires_ppt_and_annotated_delivery_tag_at_manifest_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            package = create_package(root, include_ppt=True)
            run_git(root, "tag", "-a", "gate5-delivery-v1", "-m", "delivery")
            manifest = gate5_delivery.generate_manifest(root, package, mode="final")
            report = gate5_delivery.verify_package(root, package, mode="final")

        self.assertTrue(manifest["delivery"]["tag_verified"])
        self.assertTrue(report["valid"])

    def test_final_rejects_missing_ppt_lightweight_tag_and_wrong_tag_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            package = create_package(root)
            run_git(root, "tag", "gate5-delivery-v1")
            with self.assertRaisesRegex(gate5_delivery.Gate5DeliveryError, "ppt_missing"):
                gate5_delivery.generate_manifest(root, package, mode="final")
            (package / "slides").mkdir()
            (package / "slides" / "gate5_delivery_v1.pptx").write_bytes(b"pptx")
            with self.assertRaisesRegex(gate5_delivery.Gate5DeliveryError, "annotated_tag_required"):
                gate5_delivery.generate_manifest(root, package, mode="final")
            run_git(root, "tag", "-d", "gate5-delivery-v1")
            run_git(root, "tag", "-a", "gate5-delivery-v1", "-m", "old")
            (root / "README.md").write_text("new commit\n", encoding="utf-8")
            run_git(root, "add", "README.md")
            run_git(root, "commit", "-m", "delivery candidate")
            with self.assertRaisesRegex(gate5_delivery.Gate5DeliveryError, "tag_target_mismatch"):
                gate5_delivery.generate_manifest(root, package, mode="final")

    def test_verifier_rejects_bad_hash_missing_asset_extra_file_and_copied_results(self):
        mutators = (
            lambda package: (package / "videos" / "demo_01_single_extrusion_v1.mp4").write_bytes(b"changed"),
            lambda package: (package / "videos" / "demo_02_through_hole_v1.mp4").unlink(),
            lambda package: (package / "unexpected.txt").write_text("extra", encoding="utf-8"),
            lambda package: (
                (package / "benchmark_results" / "copied.json").parent.mkdir(),
                (package / "benchmark_results" / "copied.json").write_text("{}", encoding="utf-8"),
            ),
        )
        for mutate in mutators:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                root, _ = create_repo(directory)
                package = create_package(root)
                gate5_delivery.generate_manifest(root, package, mode="preflight")
                mutate(package)
                report = gate5_delivery.verify_package(root, package, mode="preflight")
                self.assertFalse(report["valid"])

    def test_package_path_must_be_ignored_delivery_package_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            unsafe = root / "other" / "gate5-delivery-v1_20260924"
            unsafe.mkdir(parents=True)
            with self.assertRaisesRegex(gate5_delivery.Gate5DeliveryError, "invalid_package_path"):
                gate5_delivery.generate_manifest(root, unsafe, mode="preflight")

    def test_package_generation_rejects_unignored_delivery_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = create_repo(directory)
            (root / ".gitignore").write_text("", encoding="utf-8")
            package = create_package(root)
            with self.assertRaisesRegex(gate5_delivery.Gate5DeliveryError, "package_not_ignored"):
                gate5_delivery.generate_manifest(root, package, mode="preflight")

    def test_project_declares_generated_run_and_delivery_directories_ignored(self):
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("runs/", ignore.splitlines())
        self.assertIn("delivery_package/", ignore.splitlines())


if __name__ == "__main__":
    unittest.main()
