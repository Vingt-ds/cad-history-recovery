import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

try:
    import gate4_freeze
except ImportError:
    gate4_freeze = None


class Gate4FreezeTests(unittest.TestCase):
    def test_freeze_records_are_label_free_complete_and_self_reference_free(self):
        records = gate4_freeze.build_freeze_records(PROJECT_ROOT)

        self.assertEqual(
            set(records),
            {
                "gate4_input_inventory.json",
                "gate4_routing_policy.json",
                "gate4_evaluation_protocol.json",
                "gate4_retry_policy.json",
                "gate4_semantic_hash_inventory.json",
                "gate4_freeze_lock.json",
            },
        )
        inventory = records["gate4_input_inventory.json"]
        self.assertEqual(len(inventory["cases"]), 30)
        serialized = json.dumps(inventory, sort_keys=True)
        for forbidden in ("family", "expected_scope", "expected_behavior", "geometry"):
            self.assertNotIn(forbidden, serialized)

        semantic = records["gate4_semantic_hash_inventory.json"]
        self.assertEqual(semantic["hash_mode"], "sha256_lf_normalized_text")
        self.assertIn(".gitattributes", semantic["files"])
        self.assertIn("external/gate4_inference.py", semantic["files"])
        self.assertIn("external/gate4_reporting.py", semantic["files"])
        self.assertIn("external/verify_gate4.py", semantic["files"])
        self.assertIn(
            "fusion_scripts/Gate4SequenceReplay/Gate4SequenceReplay.py",
            semantic["files"],
        )
        for relative, digest in semantic["files"].items():
            self.assertEqual(
                digest,
                gate4_freeze.semantic_sha256(PROJECT_ROOT / relative),
            )

        lock = records["gate4_freeze_lock.json"]
        self.assertEqual(
            lock["evaluation_commit_binding"], "containing_git_commit"
        )
        self.assertNotIn("evaluation_commit", lock)
        self.assertNotIn("config/gate4_freeze_lock.json", lock["files"])
        self.assertEqual(len(lock["files"]), 5)

    def test_freeze_writer_is_deterministic_and_refuses_any_overwrite(self):
        records = gate4_freeze.build_freeze_records(PROJECT_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            written = gate4_freeze.write_freeze_records(root, records)
            first = {path.name: path.read_bytes() for path in written}
            self.assertEqual(
                json.loads((root / "config" / "gate4_freeze_lock.json").read_text()),
                records["gate4_freeze_lock.json"],
            )
            with self.assertRaisesRegex(
                gate4_freeze.Gate4FreezeError, "freeze_artifact_exists"
            ):
                gate4_freeze.write_freeze_records(root, records)
            self.assertEqual(
                first,
                {path.name: path.read_bytes() for path in written},
            )

    def test_semantic_hash_is_invariant_to_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.py"
            path.write_bytes(b"first\nsecond\n")
            lf_hash = gate4_freeze.semantic_sha256(path)
            path.write_bytes(b"first\r\nsecond\r\n")
            crlf_hash = gate4_freeze.semantic_sha256(path)

        self.assertEqual(lf_hash, crlf_hash)


if __name__ == "__main__":
    unittest.main()
