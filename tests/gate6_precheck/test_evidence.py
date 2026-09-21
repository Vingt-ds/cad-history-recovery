from pathlib import Path
import hashlib
import tempfile
import unittest

from tools.gate6_precheck.evidence import EvidencePackage, FailureLedger
from tools.gate6_precheck.contract import ContractError, load_contract


class EvidenceTests(unittest.TestCase):
    def test_reopen_with_external_anchor_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            package = EvidencePackage(Path(folder) / 'qualification')
            package.write_json('nested/result.json', {'pass': True})
            package.seal()
            anchor = package.seal_digest
            with self.assertRaises(AttributeError):
                package.seal_digest = '0' * 64
            before = {p.relative_to(package.root): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in package.root.rglob('*') if p.is_file()}
            self.assertTrue(EvidencePackage.verify_existing(package.root, anchor))
            after = {p.relative_to(package.root): (p.read_bytes(), p.stat().st_mtime_ns)
                     for p in package.root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            missing = Path(folder) / 'nonexistent'
            with self.assertRaises(ContractError):
                EvidencePackage.verify_existing(missing, anchor)
            self.assertFalse(missing.exists())

    def test_reopen_rejects_each_tamper_and_wrong_anchor(self):
        for change in ('asset', 'added', 'manifest', 'anchor', 'rewritten_manifest'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                package = EvidencePackage(Path(folder) / 'qualification')
                package.write_bytes('asset.txt', b'original')
                package.seal()
                anchor = package.seal_digest
                if change in ('asset', 'rewritten_manifest'):
                    (package.root / 'asset.txt').write_bytes(b'changed')
                if change == 'added':
                    (package.root / 'extra.txt').write_bytes(b'extra')
                if change == 'manifest':
                    (package.root / 'SHA256SUMS').write_bytes(b'')
                if change == 'rewritten_manifest':
                    digest = hashlib.sha256(b'changed').hexdigest()
                    (package.root / 'SHA256SUMS').write_text(f'{digest}  asset.txt\n')
                if change == 'anchor':
                    anchor = '0' * 64
                with self.assertRaises(ContractError):
                    EvidencePackage.verify_existing(package.root, anchor)

    def test_ledger_rejects_noncanonical_evidence_paths(self):
        invalid = ('', '.', './asset', 'folder/../asset', '../asset', '/absolute',
                   'C:/absolute', 'folder\\asset', 'folder//asset', 'folder/',
                   'a\nb', 'a\tb', 'a\x00b', 'a\x7fb', Path('asset'))
        ledger = FailureLedger(load_contract())
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(ContractError):
                ledger.add('tool_identity_failure', 'bad path', [path])
        self.assertEqual(ledger.failures, [])
        record = ledger.add('tool_identity_failure', 'valid', ['nested/asset.step'])
        self.assertEqual(record['evidence_paths'], ['nested/asset.step'])

    def test_writer_uses_same_relative_path_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            package = EvidencePackage(Path(folder) / 'qualification')
            for path in ('folder\\asset', './asset', 'folder//asset', 'a\tb'):
                with self.subTest(path=path), self.assertRaises(ContractError):
                    package.write_bytes(path, b'data')

    def test_ledger_rejects_mutated_contract(self):
        config = load_contract()
        config['failure_stages']['invented_failure'] = 'execution'
        with self.assertRaises(ContractError) as caught:
            FailureLedger(config)
        self.assertEqual(caught.exception.code, 'specification_binding_failure')

    def test_returned_record_cannot_mutate_ledger(self):
        ledger = FailureLedger(load_contract())
        record = ledger.add('tool_identity_failure', 'first', ['original.json'])
        record['primary'] = False
        record['evidence_paths'].append('invented.json')
        ledger.add('comparison_indeterminate', 'diagnostic')
        self.assertEqual([item['primary'] for item in ledger.failures], [True, False])
        self.assertEqual(ledger.failures[0]['evidence_paths'], ['original.json'])

    def test_failures_snapshot_cannot_mutate_ledger(self):
        ledger = FailureLedger(load_contract())
        ledger.add('tool_identity_failure', 'first', ['original.json'])
        snapshot = ledger.failures
        snapshot[0]['primary'] = False
        snapshot[0]['evidence_paths'].clear()
        snapshot.clear()
        ledger.add('comparison_indeterminate', 'diagnostic')
        self.assertEqual([item['primary'] for item in ledger.failures], [True, False])
        self.assertEqual(ledger.failures[0]['evidence_paths'], ['original.json'])
        with self.assertRaises(AttributeError):
            ledger.failures = []

    def test_failure_stages_cannot_be_replaced_or_mutated(self):
        ledger = FailureLedger(load_contract())
        with self.assertRaises(TypeError):
            ledger.stages['tool_identity_failure'] = 'execution'
        with self.assertRaises(AttributeError):
            ledger.stages = {}

    def test_primary_requires_boolean_or_none(self):
        for primary in (0, 1, 'x', [], {}):
            with self.subTest(primary=primary):
                ledger = FailureLedger(load_contract())
                with self.assertRaises(ContractError):
                    ledger.add('tool_identity_failure', 'first', primary=primary)
                self.assertEqual(ledger.failures, [])

    def test_seal_no_overwrite_and_detect_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            package = EvidencePackage(Path(folder) / 'qualification')
            package.write_json('result.json', {'pass': True})
            with self.assertRaises(FileExistsError):
                package.write_json('result.json', {})
            package.seal()
            self.assertTrue(package.verify())
            with self.assertRaises(ContractError):
                package.write_json('late.json', {})
            (package.root / 'result.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ContractError):
                package.verify()

    def test_no_campaign_creation_and_no_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            forbidden = Path(folder) / 'runs/gate6/precheck/gate6-precheck-0.1/x'
            with self.assertRaises(ContractError):
                EvidencePackage(forbidden)
            self.assertFalse(forbidden.exists())
            package = EvidencePackage(Path(folder) / 'qualification')
            with self.assertRaises(ContractError):
                package.write_json('../escape.json', {})

    def test_first_failure_primary_later_diagnostic(self):
        ledger = FailureLedger(load_contract())
        ledger.add('tool_identity_failure', 'mismatch')
        ledger.add('comparison_indeterminate', 'read-only diagnostic')
        self.assertEqual([f['stage'] for f in ledger.failures], ['tool_identity', 'comparison'])
        self.assertEqual([f['primary'] for f in ledger.failures], [True, False])
        with self.assertRaises(ContractError):
            ledger.add('unknown', 'bad code')

    def test_first_blocking_failure_cannot_be_secondary(self):
        ledger = FailureLedger(load_contract())
        with self.assertRaises(ContractError) as caught:
            ledger.add('tool_identity_failure', 'first blocking failure', primary=False)
        self.assertEqual(caught.exception.code, 'schema_invalid')
        self.assertEqual(ledger.failures, [])
        ledger.add('tool_identity_failure', 'first blocking failure')
        ledger.add('comparison_indeterminate', 'diagnostic', primary=False)
        self.assertEqual([item['primary'] for item in ledger.failures], [True, False])

    def test_nested_manifest_named_asset_is_hashed(self):
        with tempfile.TemporaryDirectory() as folder:
            package = EvidencePackage(Path(folder) / 'qualification')
            package.write_bytes('nested/SHA256SUMS', b'asset')
            hashes = package.seal()
            self.assertIn('nested/SHA256SUMS', hashes)

    def test_added_file_and_modified_seal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            package = EvidencePackage(Path(folder) / 'qualification')
            package.write_json('result.json', {})
            package.seal()
            (package.root / 'added.txt').write_text('added')
            with self.assertRaises(ContractError):
                package.verify()
            (package.root / 'SHA256SUMS').write_text('')
            with self.assertRaises(ContractError):
                package.verify()
