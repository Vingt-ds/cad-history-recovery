import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "fusion_scripts" / "Gate6EnvironmentProbe" / "Gate6EnvironmentProbe.py"
MANIFEST = SCRIPT.with_suffix(".manifest")


def load_probe(name="gate6_environment_probe"):
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    adsk.core = core
    with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": core}):
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Collection:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]


class FakeApp:
    version = "2704.1.53"
    scripts = Collection()

    @property
    def documents(self):
        raise AssertionError("environment probe must not access documents")


def challenge(module):
    return {
        "schema_version": module.CHALLENGE_SCHEMA_VERSION,
        "challenge_id": "PFCH-" + "a" * 32,
        "challenge_nonce": "b" * 64,
        "issued_at_utc": "2026-09-20T00:00:00+00:00",
        "specification_commit": module.SPECIFICATION_COMMIT,
        "implementation_commit": "c" * 40,
        "contract_version": "gate6-precheck-0.1",
        "frozen_sha256": dict(module.FROZEN_SHA256),
        "probe_artifacts": {
            module.PROBE_SCRIPT_PATH: hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
            module.PROBE_MANIFEST_PATH: hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        },
        "expected_environment": {
            "fusion": "2704.1.53",
            "fusion_python": "3.14.0",
            "external_python": "3.11.16",
            "cadquery": "2.8.0",
            "ocp": "7.9.3.1",
            "numpy": "2.4.6",
            "scipy": "1.17.1",
            "os": "Windows-10-10.0.22621-SP0",
        },
        "execution_authorization": "not_granted",
        "formal_campaign_requested": False,
        "campaign_status": "NOT_STARTED",
        "oracle_run_count": 0,
        "formal_replay_performed": False,
    }


def write_challenge(path, value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    Path(path).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def seal_challenge(path, challenge_sha256):
    manifest = f"{challenge_sha256}  {Path(path).name}\n".encode("utf-8")
    (Path(path).parent / "SHA256SUMS").write_bytes(manifest)
    return hashlib.sha256(manifest).hexdigest()


class FusionEnvironmentProbeTests(unittest.TestCase):
    def setUp(self):
        self.module = load_probe(self.id().replace(".", "_"))
        self.runtime = patch.multiple(
            self.module,
            _fusion_python_version=lambda: "3.14.0",
            _platform_string=lambda: "Windows-10-10.0.22621-SP0",
            _process_creation_time=lambda: "2026-09-20T00:00:00Z",
        )

    def test_manifest_is_a_windows_fusion_script(self):
        value = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        self.assertEqual(value["autodeskProduct"], "Fusion")
        self.assertEqual(value["type"], "script")
        self.assertEqual(value["supportedOS"], "windows")
        self.assertIn("environment", value["description"][""].lower())

    def test_probe_writes_one_exclusive_bound_response_without_documents(self):
        with tempfile.TemporaryDirectory(prefix="qualification-") as folder, self.runtime:
            challenge_path = Path(folder) / "preflight_challenge.json"
            expected_hash = write_challenge(challenge_path, challenge(self.module))
            seal_hash = seal_challenge(challenge_path, expected_hash)
            response_path = Path(folder) / "fusion_environment_response.json"
            response = self.module._execute_probe(
                FakeApp(), str(challenge_path), expected_hash, seal_hash,
                str(response_path), str(PROJECT_ROOT)
            )
            self.assertEqual(response["challenge_sha256"], expected_hash)
            self.assertEqual(response["live_environment"]["fusion"], "2704.1.53")
            self.assertGreater(response["live_environment"]["pid"], 0)
            self.assertEqual(response["campaign"]["status"], "NOT_STARTED")
            self.assertFalse(response["campaign"]["authorized"])
            self.assertEqual(json.loads(response_path.read_text(encoding="utf-8")), response)
            with self.assertRaises(self.module.ProbeError) as caught:
                self.module._execute_probe(
                    FakeApp(), str(challenge_path), expected_hash, seal_hash,
                    str(response_path), str(PROJECT_ROOT)
                )
            self.assertEqual(caught.exception.code, "PF_RESPONSE_EXISTS")

    def test_probe_rejects_hash_binding_environment_and_missing_process_start(self):
        with tempfile.TemporaryDirectory(prefix="qualification-") as folder, self.runtime:
            challenge_path = Path(folder) / "preflight_challenge.json"
            expected_hash = write_challenge(challenge_path, challenge(self.module))
            seal_hash = seal_challenge(challenge_path, expected_hash)
            for label, app, digest in (
                ("hash", FakeApp(), "0" * 64),
                ("environment", types.SimpleNamespace(version="wrong", scripts=Collection()), expected_hash),
            ):
                with self.subTest(label=label), self.assertRaises(self.module.ProbeError):
                    self.module._execute_probe(
                        app, str(challenge_path), digest, seal_hash,
                        str(Path(folder) / (label + "-response.json")), str(PROJECT_ROOT),
                    )

        with tempfile.TemporaryDirectory(prefix="qualification-") as folder:
            challenge_path = Path(folder) / "preflight_challenge.json"
            expected_hash = write_challenge(challenge_path, challenge(self.module))
            seal_hash = seal_challenge(challenge_path, expected_hash)
            with patch.multiple(
                self.module,
                _fusion_python_version=lambda: "3.14.0",
                _platform_string=lambda: "Windows-10-10.0.22621-SP0",
                _process_creation_time=lambda: None,
            ), self.assertRaises(self.module.ProbeError) as caught:
                self.module._execute_probe(
                    FakeApp(), str(challenge_path), expected_hash, seal_hash,
                    str(Path(folder) / "response.json"), str(PROJECT_ROOT),
                )
            self.assertEqual(caught.exception.code, "PF_PROCESS_IDENTITY_UNAVAILABLE")

    def test_probe_rejects_challenge_with_wrong_bound_probe_hash(self):
        with tempfile.TemporaryDirectory(prefix="qualification-") as folder, self.runtime:
            challenge_path = Path(folder) / "preflight_challenge.json"
            value = challenge(self.module)
            value["probe_artifacts"][self.module.PROBE_SCRIPT_PATH] = "0" * 64
            expected_hash = write_challenge(challenge_path, value)
            seal_hash = seal_challenge(challenge_path, expected_hash)
            with self.assertRaises(self.module.ProbeError) as caught:
                self.module._execute_probe(
                    FakeApp(), str(challenge_path), expected_hash, seal_hash,
                    str(Path(folder) / "response.json"), str(PROJECT_ROOT),
                )
            self.assertEqual(caught.exception.code, "PF_CHALLENGE_INVALID")

    def test_probe_rejects_formal_or_repo_paths_before_app_access(self):
        class ExplosiveApp:
            @property
            def version(self):
                raise AssertionError("app must not be touched")

        with tempfile.TemporaryDirectory(prefix="qualification-") as folder:
            challenge_path = Path(folder) / "preflight_challenge.json"
            expected_hash = write_challenge(challenge_path, challenge(self.module))
            seal_hash = seal_challenge(challenge_path, expected_hash)
            for destination in (
                PROJECT_ROOT / "probe-response.json",
                Path(folder) / "runs" / "gate6" / "precheck" / "response.json",
            ):
                with self.subTest(destination=destination), self.assertRaises(self.module.ProbeError) as caught:
                    self.module._execute_probe(
                        ExplosiveApp(), str(challenge_path), expected_hash, seal_hash,
                        str(destination), str(PROJECT_ROOT),
                    )
                self.assertEqual(caught.exception.code, "PF_UNSAFE_PATH")

    def test_run_uses_environment_and_inferred_repo_root_not_context(self):
        class UI:
            messages = []

            def messageBox(self, message):
                self.messages.append(message)

        with tempfile.TemporaryDirectory(prefix="qualification-") as folder, self.runtime:
            challenge_path = Path(folder) / "preflight_challenge.json"
            expected_hash = write_challenge(challenge_path, challenge(self.module))
            seal_hash = seal_challenge(challenge_path, expected_hash)
            response_path = Path(folder) / "fusion_environment_response.json"
            app = FakeApp()
            app.userInterface = UI()
            self.module.adsk.core.Application = types.SimpleNamespace(get=lambda: app)
            environment = {
                "GATE6_PREFLIGHT_CHALLENGE_PATH": str(challenge_path),
                "GATE6_PREFLIGHT_CHALLENGE_SHA256": expected_hash,
                "GATE6_PREFLIGHT_CHALLENGE_SEAL_SHA256": seal_hash,
                "GATE6_PREFLIGHT_RESPONSE_PATH": str(response_path),
            }
            with patch.dict(self.module.os.environ, environment, clear=False):
                self.module.run({"project_root": str(Path(folder) / "wrong-root")})
            self.assertTrue(response_path.is_file())
            self.assertIn("succeeded", app.userInterface.messages[-1].lower())
            self.assertEqual(self.module._project_root(), str(PROJECT_ROOT))


if __name__ == "__main__":
    unittest.main()
