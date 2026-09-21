import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    PROJECT_ROOT
    / "fusion_scripts"
    / "Gate6QualificationReplay"
    / "Gate6QualificationReplay.py"
)


def load_executor(name="gate6_qualification_executor"):
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    adsk.core = core
    adsk.fusion = fusion
    with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion}):
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Collection:
    def __init__(self, values=None):
        self.values = list(values or [])

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]


class FakeBody:
    next_id = 1

    def __init__(self, parent, volume=1.0, name="body"):
        self.parentComponent = parent
        self.volume = volume
        self.name = name
        self.entityToken = "body-{}".format(FakeBody.next_id)
        FakeBody.next_id += 1
        self.isSolid = True
        self.isValid = True
        self.lumps = Collection([object()])
        self.faces = Collection([object()] * 6)
        self.boundingBox = types.SimpleNamespace(
            minPoint=types.SimpleNamespace(x=0.0, y=0.0, z=0.0),
            maxPoint=types.SimpleNamespace(x=1.0, y=1.0, z=1.0),
        )
        self.physicalProperties = types.SimpleNamespace(volume=volume)

    def copyToComponent(self, occurrence):
        if not hasattr(occurrence, "component"):
            raise TypeError("child-component copy requires an occurrence target")
        component = occurrence.component
        component.events.append(("copy", self.parentComponent.name, component.name))
        copied = FakeBody(component, self.volume, self.name + "_copy")
        # Insert first so code that incorrectly resolves the target after the
        # copy would select the tool, not the pre-copy current result.
        component.bRepBodies.values.insert(0, copied)
        return copied


class FakeProfiles(Collection):
    pass


class FakeLines:
    def __init__(self, events):
        self.events = events

    def addTwoPointRectangle(self, first, second):
        self.events.append(("rectangle", first, second))


class FakeSketch:
    def __init__(self, events):
        self.profiles = FakeProfiles([object()])
        self.sketchCurves = types.SimpleNamespace(sketchLines=FakeLines(events))


class FakeSketches:
    def __init__(self, events):
        self.events = events

    def add(self, plane):
        self.events.append(("sketch", plane))
        return FakeSketch(self.events)


class FakePlaneInput:
    def __init__(self, events):
        self.events = events
        self.definition = None

    def setByOffset(self, base, offset):
        self.definition = (base, offset)
        self.events.append(("plane_offset", base, offset))
        return True


class FakePlanes:
    def __init__(self, events):
        self.events = events

    def createInput(self):
        return FakePlaneInput(self.events)

    def add(self, plane_input):
        self.events.append(("plane_add", plane_input.definition))
        return ("plane", plane_input.definition)


class FakeExtrudes:
    def __init__(self, component):
        self.component = component

    def addSimple(self, profile, distance, operation):
        self.component.events.append(("extrude", self.component.name, distance, operation))
        body = FakeBody(self.component, abs(distance), self.component.name + "_body")
        self.component.bRepBodies.values.append(body)
        return types.SimpleNamespace(bodies=Collection([body]))


class FakeCombineInput:
    def __init__(self, target, tools):
        self.targetBody = target
        self.toolBodies = tools
        self.operation = None
        self.isKeepToolBodies = True


class FakeCombines:
    def __init__(self, component):
        self.component = component

    def createInput(self, target, tools):
        self.component.events.append(
            ("combine_input", self.component.name, target.entityToken, tools.count)
        )
        return FakeCombineInput(target, tools)

    def add(self, combine_input):
        tool = combine_input.toolBodies.item(0)
        self.component.events.append(
            (
                "combine_add",
                combine_input.targetBody.entityToken,
                tool.entityToken,
                combine_input.operation,
                combine_input.isKeepToolBodies,
            )
        )
        self.component.bRepBodies.values.remove(tool)
        return types.SimpleNamespace(bodies=Collection([combine_input.targetBody]))


class FakeComponent:
    def __init__(self, name, events):
        self.name = name
        self.events = events
        self.bRepBodies = Collection()
        self.xYConstructionPlane = "{}_XY".format(name)
        self.constructionPlanes = FakePlanes(events)
        self.sketches = FakeSketches(events)
        self.features = types.SimpleNamespace(
            extrudeFeatures=FakeExtrudes(self), combineFeatures=FakeCombines(self)
        )


class FakeOccurrences:
    def __init__(self, events):
        self.events = events
        self.components = []

    def addNewComponent(self, matrix):
        component = FakeComponent("unnamed", self.events)
        occurrence = types.SimpleNamespace(component=component)
        self.components.append(occurrence)
        self.events.append(("component_add", matrix))
        return occurrence


class FakeUnits:
    internalUnits = "cm"

    def __init__(self, events):
        self.events = events

    def convert(self, value, source, target):
        self.events.append(("convert", value, source, target))
        return value / 10.0


class FakeExportManager:
    def __init__(self, events):
        self.events = events

    def createSTEPExportOptions(self, path, component):
        self.events.append(("step_options", Path(path).name, component.name))
        return types.SimpleNamespace(kind="step", path=path, component=component)

    def createFusionArchiveExportOptions(self, path):
        self.events.append(("f3d_options", Path(path).name))
        return types.SimpleNamespace(kind="f3d", path=path)

    def execute(self, options):
        self.events.append(("export", options.kind, Path(options.path).name))
        Path(options.path).write_bytes(options.kind.encode("ascii"))
        return True


class FakeDocument:
    def __init__(self, app, close_raises=False):
        self.app = app
        self.name = "Gate6 qualification"
        self.id = "doc-qualification-1"
        self.close_raises = close_raises

    def close(self, save_changes):
        self.app.events.append(("close", save_changes))
        if self.close_raises:
            raise RuntimeError("close failed")


class FakeDocuments:
    def __init__(self, app, close_raises=False):
        self.app = app
        self.add_calls = 0
        self.close_raises = close_raises

    def add(self, document_type):
        self.add_calls += 1
        self.app.events.append(("documents_add", document_type))
        document = FakeDocument(self.app, self.close_raises)
        self.app.activeDocument = document
        return document


class FakeDesign:
    def __init__(self, events):
        self.rootComponent = types.SimpleNamespace(occurrences=FakeOccurrences(events))
        self.unitsManager = FakeUnits(events)
        self.exportManager = FakeExportManager(events)


class FakeApp:
    def __init__(self, close_raises=False):
        self.events = []
        self.version = "2704.1.53"
        self.documents = FakeDocuments(self, close_raises)
        self.activeProduct = FakeDesign(self.events)
        self.activeDocument = None
        self.scripts = Collection(
            [
                types.SimpleNamespace(
                    id="z-script", name="Z", manifestPath=None, version="1"
                ),
                types.SimpleNamespace(
                    id="a-script", name="A", manifestPath=None, version="2"
                ),
            ]
        )


def install_fake_api(module):
    module.adsk.core.DocumentTypes = types.SimpleNamespace(
        FusionDesignDocumentType="fusion-document"
    )
    module.adsk.core.Matrix3D = types.SimpleNamespace(create=lambda: "identity")
    module.adsk.core.Point3D = types.SimpleNamespace(
        create=lambda x, y, z: (x, y, z)
    )
    module.adsk.core.ValueInput = types.SimpleNamespace(createByReal=lambda value: value)

    class ObjectCollection(Collection):
        @classmethod
        def create(cls):
            return cls()

        def add(self, value):
            self.values.append(value)

    module.adsk.core.ObjectCollection = ObjectCollection
    module.adsk.fusion.Design = types.SimpleNamespace(cast=lambda product: product)
    module.adsk.fusion.FeatureOperations = types.SimpleNamespace(
        NewBodyFeatureOperation="new_body",
        JoinFeatureOperation="join",
        CutFeatureOperation="cut",
    )


def qualification_request(output_dir):
    output_dir = Path(output_dir)
    config = json.loads(
        (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    challenge = {
        "schema_version": "gate6-fusion-qualification-challenge-0.1",
        "challenge_id": "QCH-SYNTHETIC-001",
        "challenge_nonce": "b" * 32,
        "specification_commit": "c440aace7306b9d68e2ae6a6ae757f36d8db1d85",
        "contract_version": "gate6-precheck-0.1",
        "expected_environment": config["environment"],
    }
    challenge_path = output_dir.parent / "qualification-challenge.json"
    challenge_path.parent.mkdir(parents=True, exist_ok=True)
    challenge_bytes = (json.dumps(challenge, sort_keys=True) + "\n").encode("utf-8")
    challenge_path.write_bytes(challenge_bytes)
    return {
        "request_version": "gate6-qualification-replay-0.1",
        "mode": "qualification",
        "qualification_id": "Q-SYNTHETIC-BOX-JC",
        "output_dir": str(output_dir),
        "challenge_id": challenge["challenge_id"],
        "challenge_nonce": challenge["challenge_nonce"],
        "external_preflight_record_path": str(challenge_path),
        "external_preflight_record_sha256": hashlib.sha256(challenge_bytes).hexdigest(),
        "order": ["J", "C"],
        "solids": {
            "B": {"min": [0, 0, 0], "max": [5, 4, 3]},
            "J": {"min": [4, 1, 1], "max": [6, 3, 2]},
            "C": {"min": [1, 1, 1], "max": [2, 2, 2]},
        },
    }


class FusionQualificationExecutorTests(unittest.TestCase):
    def setUp(self):
        self.module = load_executor(self.id())
        install_fake_api(self.module)

    def execute(self, app, request, project_root=PROJECT_ROOT):
        with patch.object(self.module.platform, "python_version", return_value="3.14.0"), patch.object(
            self.module.platform,
            "platform",
            return_value="Windows-10-10.0.22621-SP0",
        ), patch.object(
            self.module, "_process_creation_time", return_value="2026-09-20T01:02:03Z"
        ):
            return self.module.execute_qualification(app, request, project_root)

    def test_manifest_declares_a_windows_fusion_qualification_script(self):
        manifest = json.loads(SCRIPT.with_suffix(".manifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["autodeskProduct"], "Fusion")
        self.assertEqual(manifest["type"], "script")
        self.assertIn("windows", manifest["supportedOS"])
        self.assertIn("qualification", manifest["description"][""].lower())

    def test_guard_rejects_formal_and_unsafe_requests_before_document_or_path_creation(self):
        cases = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = qualification_request(root / "qualification" / "out")
            for mutate in (
                lambda r: r.update(mode="formal"),
                lambda r: r.update(qualification_id="OS_JC_R1"),
                lambda r: r.update(output_dir=str(root / "runs" / "gate6" / "precheck" / "x")),
                lambda r: r.update(rounds=[["OS_JC_R1"]]),
            ):
                request = json.loads(json.dumps(base))
                mutate(request)
                cases.append(request)

            for index, request in enumerate(cases):
                app = FakeApp()
                with self.subTest(index=index):
                    with self.assertRaises(self.module.ReplayError):
                        self.execute(app, request)
                    self.assertEqual(app.documents.add_calls, 0)
                    self.assertFalse(Path(request["output_dir"]).exists())

    def test_guard_rejects_complete_frozen_formal_geometry_even_with_qualification_label(self):
        config = json.loads(
            (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            request = qualification_request(Path(directory) / "out")
            request["solids"] = {
                "B": config["solids"]["B"],
                "J": config["solids"]["J"],
                "C": config["solids"]["C_OS"],
            }
            app = FakeApp()
            with self.assertRaisesRegex(self.module.ReplayError, "formal geometry"):
                self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(Path(request["output_dir"]).exists())

    def test_guard_rejects_near_frozen_formal_geometry_for_both_orders_and_groups(self):
        config = json.loads(
            (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        for perturbation in (1e-9, 1e-4):
            for cut_name in ("C_OS", "C_DE"):
                for order in (["J", "C"], ["C", "J"]):
                    with self.subTest(
                        perturbation=perturbation, cut=cut_name, order=order
                    ), tempfile.TemporaryDirectory(prefix="qualification-") as directory:
                        request = qualification_request(Path(directory) / "out")
                        request["order"] = order
                        request["solids"] = {
                            "B": json.loads(json.dumps(config["solids"]["B"])),
                            "J": json.loads(json.dumps(config["solids"]["J"])),
                            "C": json.loads(json.dumps(config["solids"][cut_name])),
                        }
                        request["solids"]["B"]["max"][0] += perturbation
                        app = FakeApp()
                        with self.assertRaisesRegex(self.module.ReplayError, "formal geometry"):
                            self.execute(app, request)
                        self.assertEqual(app.documents.add_calls, 0)
                        self.assertFalse(Path(request["output_dir"]).exists())

    def test_guard_accepts_geometry_just_outside_frozen_tolerance(self):
        config = json.loads(
            (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            request = qualification_request(Path(directory) / "out")
            request["solids"] = {
                "B": json.loads(json.dumps(config["solids"]["B"])),
                "J": json.loads(json.dumps(config["solids"]["J"])),
                "C": json.loads(json.dumps(config["solids"]["C_OS"])),
            }
            request["solids"]["B"]["max"][0] += 0.000100001
            app = FakeApp()
            record = self.execute(app, request)
            self.assertEqual(record["status"], "success")
            self.assertEqual(app.documents.add_calls, 1)

    def test_guard_rejects_semantically_equal_config_with_mutated_frozen_bytes(self):
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            root = Path(directory)
            request = qualification_request(root / "out")
            project_root = root / "project"
            config_dir = project_root / "config"
            config_dir.mkdir(parents=True)
            frozen = (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_bytes()
            (config_dir / "gate6_precheck_v0_1.json").write_bytes(frozen + b"\n")
            app = FakeApp()
            with self.assertRaisesRegex(self.module.ReplayError, "config SHA-256"):
                self.execute(app, request, project_root)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(Path(request["output_dir"]).exists())

    def test_guard_requires_frozen_config_to_remain_not_granted(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            request = qualification_request(Path(directory) / "out")
            changed = json.loads(
                (PROJECT_ROOT / "config" / "gate6_precheck_v0_1.json").read_text(
                    encoding="utf-8"
                )
            )
            changed["execution_authorization"] = "granted"
            with patch.object(self.module, "_load_frozen_config", return_value=(changed, "b" * 64)):
                with self.assertRaisesRegex(self.module.ReplayError, "not_granted"):
                    self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)

    def test_guard_rejects_nonfinite_box_coordinates_before_opening_document(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            request = qualification_request(Path(directory) / "out")
            request["solids"]["B"]["max"][0] = float("nan")
            with self.assertRaisesRegex(self.module.ReplayError, "finite"):
                self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(Path(request["output_dir"]).exists())

    def test_guard_verifies_challenge_bytes_schema_binding_and_live_environment(self):
        mutations = (
            ("hash", lambda request, challenge: request.update(external_preflight_record_sha256="0" * 64)),
            ("nonce", lambda request, challenge: request.update(challenge_nonce="c" * 32)),
            ("spec", lambda request, challenge: challenge.update(specification_commit="0" * 40)),
            ("contract", lambda request, challenge: challenge.update(contract_version="gate6-precheck-9.9")),
            ("environment", lambda request, challenge: challenge["expected_environment"].update(fusion="wrong")),
            ("schema", lambda request, challenge: challenge.update(schema_version="wrong")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="qualification-") as directory:
                output = Path(directory) / "out"
                request = qualification_request(output)
                challenge_path = Path(request["external_preflight_record_path"])
                challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
                mutate(request, challenge)
                if label not in {"hash", "nonce"}:
                    payload = (json.dumps(challenge, sort_keys=True) + "\n").encode("utf-8")
                    challenge_path.write_bytes(payload)
                    request["external_preflight_record_sha256"] = hashlib.sha256(payload).hexdigest()
                app = FakeApp()
                with self.assertRaises(self.module.ReplayError):
                    self.execute(app, request)
                self.assertEqual(app.documents.add_calls, 0)
                self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "out"
            request = qualification_request(output)
            Path(request["external_preflight_record_path"]).write_bytes(b"not json")
            request["external_preflight_record_sha256"] = hashlib.sha256(b"not json").hexdigest()
            app = FakeApp()
            with self.assertRaisesRegex(self.module.ReplayError, "JSON"):
                self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(output.exists())

    def test_guard_rejects_unsafe_challenge_path_live_mismatch_and_missing_process_time(self):
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            root = Path(directory)
            output = root / "out"
            request = qualification_request(output)
            unsafe = root / "OS_JC_R1.json"
            source = Path(request["external_preflight_record_path"])
            unsafe.write_bytes(source.read_bytes())
            request["external_preflight_record_path"] = str(unsafe)
            app = FakeApp()
            with self.assertRaises(self.module.ReplayError):
                self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "out"
            request = qualification_request(output)
            app = FakeApp()
            app.version = "wrong"
            with self.assertRaisesRegex(self.module.ReplayError, "environment"):
                self.execute(app, request)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "out"
            request = qualification_request(output)
            app = FakeApp()
            with patch.object(self.module.platform, "python_version", return_value="3.14.0"), patch.object(
                self.module.platform, "platform", return_value="Windows-10-10.0.22621-SP0"
            ), patch.object(self.module, "_process_creation_time", return_value=None):
                with self.assertRaisesRegex(self.module.ReplayError, "process creation"):
                    self.module.execute_qualification(app, request, PROJECT_ROOT)
            self.assertEqual(app.documents.add_calls, 0)
            self.assertFalse(output.exists())

    def test_executes_isolated_components_explicit_combines_and_exact_export_order(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "result"
            request = qualification_request(output)
            record = self.execute(app, request)

            component_names = [
                occurrence.component.name
                for occurrence in app.activeProduct.rootComponent.occurrences.components
            ]
            self.assertEqual(
                component_names, ["B_SOURCE", "J_SOURCE", "C_SOURCE", "RESULT"]
            )
            conversions = [event for event in app.events if event[0] == "convert"]
            self.assertEqual(len(conversions), 18)
            self.assertTrue(all(event[2:] == ("mm", "cm") for event in conversions))

            combine_inputs = [event for event in app.events if event[0] == "combine_input"]
            combine_adds = [event for event in app.events if event[0] == "combine_add"]
            self.assertEqual([event[3] for event in combine_inputs], [1, 1])
            self.assertEqual([event[3] for event in combine_adds], ["join", "cut"])
            self.assertEqual([event[4] for event in combine_adds], [False, False])
            self.assertNotEqual(combine_adds[0][1], combine_adds[1][2])
            first_copy_index = next(
                index
                for index, event in enumerate(app.events)
                if event[:3] == ("copy", "J_SOURCE", "RESULT")
            )
            first_combine_input_index = next(
                index for index, event in enumerate(app.events) if event[0] == "combine_input"
            )
            self.assertLess(first_copy_index, first_combine_input_index)

            step_options = [event for event in app.events if event[0] == "step_options"]
            self.assertEqual(
                step_options,
                [
                    ("step_options", "base.step", "B_SOURCE"),
                    ("step_options", "join_tool.step", "J_SOURCE"),
                    ("step_options", "cut_tool.step", "C_SOURCE"),
                    ("step_options", "after_modifier_1.step", "RESULT"),
                    ("step_options", "final.step", "RESULT"),
                ],
            )

            export_events = [event for event in app.events if event[0] == "export"]
            self.assertEqual(
                export_events,
                [
                    ("export", "step", "base.step"),
                    ("export", "step", "join_tool.step"),
                    ("export", "step", "cut_tool.step"),
                    ("export", "step", "after_modifier_1.step"),
                    ("export", "step", "final.step"),
                    ("export", "f3d", "construction.f3d"),
                ],
            )
            for name in (
                "base.step",
                "join_tool.step",
                "cut_tool.step",
                "after_modifier_1.step",
                "final.step",
                "construction.f3d",
                "qualification_log.json",
            ):
                self.assertGreater((output / name).stat().st_size, 0)
            self.assertEqual(record["status"], "success")

    def test_sources_are_preserved_and_target_is_reacquired_after_each_combine(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            self.execute(app, qualification_request(Path(directory) / "result"))
        components = {
            occurrence.component.name: occurrence.component
            for occurrence in app.activeProduct.rootComponent.occurrences.components
        }
        for name in ("B_SOURCE", "J_SOURCE", "C_SOURCE"):
            self.assertEqual(components[name].bRepBodies.count, 1)
            self.assertTrue(components[name].bRepBodies.item(0).isValid)
        combine_adds = [event for event in app.events if event[0] == "combine_add"]
        self.assertEqual(combine_adds[0][1], combine_adds[1][1])

    def test_refuses_overwrite_before_opening_document(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "result"
            output.mkdir()
            existing = output / "base.step"
            existing.write_bytes(b"keep")
            with self.assertRaisesRegex(self.module.ReplayError, "overwrite"):
                self.execute(app, qualification_request(output))
            self.assertEqual(app.documents.add_calls, 0)
            self.assertEqual(existing.read_bytes(), b"keep")

    def test_failure_closes_without_save_and_keeps_primary_when_close_also_fails(self):
        app = FakeApp(close_raises=True)
        app.activeProduct.exportManager.execute = lambda options: False
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "result"
            with self.assertRaises(self.module.ReplayError) as caught:
                self.execute(app, qualification_request(output))
            self.assertEqual(caught.exception.code, "step_export_failed")
            self.assertTrue(
                any(item["code"] == "document_close_failed" for item in caught.exception.diagnostics)
            )
            self.assertIn(("close", False), app.events)
            log = json.loads((output / "qualification_log.json").read_text(encoding="utf-8"))
            self.assertEqual(log["primary_error"]["code"], "step_export_failed")
            self.assertEqual(log["secondary_diagnostics"][0]["code"], "document_close_failed")

    def test_close_only_failure_is_primary_and_preserves_exported_assets(self):
        app = FakeApp(close_raises=True)
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            output = Path(directory) / "result"
            with self.assertRaises(self.module.ReplayError) as caught:
                self.execute(app, qualification_request(output))
            self.assertEqual(caught.exception.code, "document_close_failed")
            self.assertEqual(caught.exception.diagnostics, [
                {"code": "document_close_failed", "message": "close failed"}
            ])
            for name in (
                "base.step",
                "join_tool.step",
                "cut_tool.step",
                "after_modifier_1.step",
                "final.step",
                "construction.f3d",
            ):
                self.assertGreater((output / name).stat().st_size, 0)
            log = json.loads((output / "qualification_log.json").read_text(encoding="utf-8"))
            self.assertEqual(log["primary_error"]["code"], "document_close_failed")
            self.assertEqual(log["secondary_diagnostics"], caught.exception.diagnostics)

    def test_environment_fingerprint_binds_request_config_script_preflight_and_sorted_scripts(self):
        app = FakeApp()
        with tempfile.TemporaryDirectory(prefix="qualification-") as directory:
            request = qualification_request(Path(directory) / "result")
            record = self.execute(app, request)
            environment = record["environment"]
            self.assertEqual(environment["fusion_version"], "2704.1.53")
            self.assertEqual(environment["process_creation_time"], "2026-09-20T01:02:03Z")
            self.assertEqual(
                environment["external_preflight_record_sha256"],
                request["external_preflight_record_sha256"],
            )
            self.assertEqual(environment["challenge_id"], request["challenge_id"])
            self.assertEqual(environment["challenge_nonce"], request["challenge_nonce"])
            self.assertRegex(environment["request_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(environment["config_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                environment["script_sha256"], hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
            )
            script_ids = [item["id"] for item in environment["fusion_scripts"]]
            self.assertEqual(script_ids, sorted(script_ids))
            self.assertIn("Gate6QualificationReplay", script_ids)
            current = next(
                item
                for item in environment["fusion_scripts"]
                if item["id"] == "Gate6QualificationReplay"
            )
            self.assertEqual(
                current["manifest_sha256"],
                hashlib.sha256(SCRIPT.with_suffix(".manifest").read_bytes()).hexdigest(),
            )
            self.assertTrue(
                all(set(item) <= {"id", "name", "version", "manifest_sha256"} for item in environment["fusion_scripts"])
            )


if __name__ == "__main__":
    unittest.main()
