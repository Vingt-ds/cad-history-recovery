import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = PROJECT_ROOT / "fusion_scripts" / "Gate4SequenceReplay" / "Gate4SequenceReplay.py"


def load_with_fake_adsk(name):
    adsk = types.ModuleType("adsk")
    adsk_core = types.ModuleType("adsk.core")
    adsk.core = adsk_core
    with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": adsk_core}):
        spec = importlib.util.spec_from_file_location(name, ADAPTER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Gate4FusionAdapterTests(unittest.TestCase):
    def test_adapter_and_manifest_exist_without_family_ids(self):
        self.assertTrue(ADAPTER.is_file())
        self.assertTrue(ADAPTER.with_suffix(".manifest").is_file())
        source = ADAPTER.read_text(encoding="utf-8")
        for token in ("D-S", "D-H", "T-S", "T-H", "family"):
            self.assertNotIn(token, source)

    def test_paths_require_exact_manifest_case_order_and_count(self):
        gate4 = load_with_fake_adsk("gate4_adapter_paths")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "benchmark_results" / "gate4-formal"
            run.mkdir(parents=True)
            case_ids = [f"case-{index:02d}" for index in range(15)]
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_schema": "gate4-run-manifest-0.1",
                        "run_id": "gate4-formal",
                        "case_count": 15,
                        "case_ids": case_ids,
                    }
                ),
                encoding="utf-8",
            )
            request = {
                "request_version": "gate4-replay-0.1",
                "run_id": "gate4-formal",
                "run_relative_path": "benchmark_results/gate4-formal",
                "case_ids": case_ids,
            }
            paths = gate4._paths(str(root), request)
            self.assertEqual(paths["case_ids"], case_ids)
            for bad_ids in (case_ids[:-1], list(reversed(case_ids)), case_ids[:-1] + [case_ids[0]]):
                bad = dict(request)
                bad["case_ids"] = bad_ids
                with self.assertRaises(gate4.ReplayError):
                    gate4._paths(str(root), bad)

    def test_adapter_loads_current_gate2_adapter_not_module_cache(self):
        gate4 = load_with_fake_adsk("gate4_adapter_loader")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fusion_scripts" / "Gate2SequenceReplay"
            path.mkdir(parents=True)
            (path / "Gate2SequenceReplay.py").write_text("marker = 'fresh'\n", encoding="utf-8")
            with patch.dict(sys.modules, {"Gate2SequenceReplay": types.SimpleNamespace(marker="stale")}):
                loaded = gate4._load_gate2_adapter(directory)
            self.assertEqual(loaded.marker, "fresh")


if __name__ == "__main__":
    unittest.main()
