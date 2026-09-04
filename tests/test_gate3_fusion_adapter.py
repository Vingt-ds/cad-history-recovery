import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = PROJECT_ROOT / "fusion_scripts" / "Gate3SequenceReplay" / "Gate3SequenceReplay.py"


def load_with_fake_adsk(name):
    adsk = types.ModuleType("adsk")
    adsk_core = types.ModuleType("adsk.core")
    adsk_fusion = types.ModuleType("adsk.fusion")
    adsk.core = adsk_core
    adsk.fusion = adsk_fusion
    with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": adsk_core, "adsk.fusion": adsk_fusion}):
        spec = importlib.util.spec_from_file_location(name, ADAPTER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Gate3FusionAdapterTests(unittest.TestCase):
    def test_adapter_and_manifest_exist(self):
        self.assertTrue(ADAPTER.is_file())
        self.assertTrue(ADAPTER.with_suffix(".manifest").is_file())

    def test_paths_require_exact_development_holes_with_offset_case_first(self):
        gate3 = load_with_fake_adsk("gate3_adapter_paths")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "benchmark_results" / "gate3-formal"
            run.mkdir(parents=True)
            request = {
                "request_version": "gate3-replay-0.1",
                "run_id": "gate3-formal",
                "run_relative_path": "benchmark_results/gate3-formal",
                "case_ids": ["D-H04", "D-H01", "D-H02", "D-H03", "D-H05"],
            }
            paths = gate3._paths(str(root), request)
            self.assertEqual(paths["case_ids"], request["case_ids"])
            bad = dict(request)
            bad["case_ids"] = list(reversed(request["case_ids"]))
            with self.assertRaises(gate3.ReplayError):
                gate3._paths(str(root), bad)

    def test_adapter_loads_current_gate2_thin_adapter_not_module_cache(self):
        gate3 = load_with_fake_adsk("gate3_adapter_loader")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fusion_scripts" / "Gate2SequenceReplay"
            path.mkdir(parents=True)
            (path / "Gate2SequenceReplay.py").write_text("marker = 'fresh'\n", encoding="utf-8")
            with patch.dict(sys.modules, {"Gate2SequenceReplay": types.SimpleNamespace(marker="stale")}):
                loaded = gate3._load_gate2_adapter(directory)
            self.assertEqual(loaded.marker, "fresh")


if __name__ == "__main__":
    unittest.main()
