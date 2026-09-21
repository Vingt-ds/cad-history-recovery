"""Append-only qualification packages; formal campaigns remain disabled."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

from .contract import ContractError, sha256_file, validate_contract


def package_relative_path(value):
    """Validate one normalized, package-relative POSIX evidence reference."""
    if (not isinstance(value, str) or not value
            or any(part in ('', '.', '..') for part in value.split('/'))
            or any(c in value for c in ('\\', ':'))
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        raise ContractError('evidence_integrity_failure', 'Expected normalized package-relative POSIX path')
    return value


class FailureLedger:
    def __init__(self, config):
        validate_contract(config)
        self._stages = MappingProxyType(dict(config['failure_stages']))
        self._failures = []

    @property
    def stages(self):
        return self._stages

    @property
    def failures(self):
        """Detached JSON-ready snapshot; callers cannot edit ledger history."""
        return deepcopy(self._failures)

    def add(self, code, message, evidence_paths=(), primary=None):
        if primary is not None and type(primary) is not bool:
            raise ContractError('schema_invalid', 'primary must be None, True, or False')
        if code not in self.stages:
            raise ContractError('schema_invalid', f'Unknown failure code: {code}')
        first = len(self._failures) == 0
        if first and primary is False:
            raise ContractError('schema_invalid', 'The first blocking failure must be primary')
        if primary is True and not first:
            raise ContractError('schema_invalid', 'Only the first blocking failure may be primary')
        if isinstance(evidence_paths, (str, bytes)):
            raise ContractError('schema_invalid', 'evidence_paths must be a sequence of paths')
        record = {'code': code, 'stage': self.stages[code], 'message': str(message),
                  'evidence_paths': [package_relative_path(p) for p in evidence_paths],
                  'primary': first if primary is None else bool(primary)}
        self._failures.append(record)
        return deepcopy(record)


class EvidencePackage:
    """No-overwrite writer, with hash seal detecting subsequent external edits.

    A seal is integrity detection, not filesystem access control. No path or
    boolean grant enables a formal campaign in this qualification build.
    """
    def __init__(self, path, mode='qualification', execution_grant=None):
        self.root = Path(path).resolve()
        lowered = [p.casefold() for p in self.root.parts]
        formal = any(lowered[i:i + 3] == ['runs', 'gate6', 'precheck'] for i in range(len(lowered) - 2))
        run_id = any(p.startswith(('os_jc_r', 'os_cj_r', 'de_jc_r', 'de_cj_r')) for p in lowered)
        if mode != 'qualification' or execution_grant is not None or formal or run_id:
            raise ContractError('specification_binding_failure', 'Formal campaign creation is not authorized in this qualification build')
        self.root.mkdir(parents=True, exist_ok=False)
        self.sealed = False
        self._seal_digest = None

    @property
    def seal_digest(self):
        """SHA-256 of SHA256SUMS; retain this externally to anchor later reads."""
        return self._seal_digest

    def _path(self, relative):
        relative = Path(package_relative_path(relative))
        destination = self.root / relative
        if not destination.resolve().is_relative_to(self.root):
            raise ContractError('evidence_integrity_failure', 'Evidence path escapes package')
        return destination

    def write_bytes(self, relative, data):
        if self.sealed or (self.root / 'SHA256SUMS').exists():
            raise ContractError('evidence_integrity_failure', 'Package is sealed')
        if str(relative).replace('\\', '/') == 'SHA256SUMS':
            raise ContractError('evidence_integrity_failure', 'SHA256SUMS is reserved for sealing')
        destination = self._path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
        return destination

    def write_json(self, relative, value):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        return self.write_bytes(relative, data)

    @staticmethod
    def _hashes_at(root):
        hashes = {}
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ContractError('evidence_integrity_failure', 'Linked evidence is forbidden')
            if path.is_file() and path != root / 'SHA256SUMS':
                name = package_relative_path(path.relative_to(root).as_posix())
                hashes[name] = sha256_file(path)
        return hashes

    def seal(self):
        if self.sealed:
            raise ContractError('evidence_integrity_failure', 'Package already sealed')
        hashes = self._hashes_at(self.root)
        content = ''.join(f'{digest}  {name}\n' for name, digest in hashes.items()).encode('utf-8')
        with (self.root / 'SHA256SUMS').open('xb') as stream:
            stream.write(content)
        self.sealed = True
        self._seal_digest = hashlib.sha256(content).hexdigest()
        return hashes

    def verify(self):
        return self.verify_existing(self.root, self.seal_digest)

    @staticmethod
    def verify_existing(path, expected_seal_sha256):
        """Read-only verification against a caller-retained external seal hash.

        Never creates a package or trusts a freshly calculated seal as its own
        anchor. This detects integrity loss, not unauthorized filesystem access.
        """
        try:
            if (not isinstance(expected_seal_sha256, str) or len(expected_seal_sha256) != 64
                    or any(c not in '0123456789abcdef' for c in expected_seal_sha256)):
                raise ValueError('External SHA-256 anchor must be 64 lowercase hexadecimal characters')
            root = Path(path).resolve()
            content = (root / 'SHA256SUMS').read_bytes()
            if hashlib.sha256(content).hexdigest() != expected_seal_sha256:
                raise ValueError('Seal differs from external anchor')
            lines = [line.split('  ', 1) for line in content.decode('utf-8').splitlines()]
            expected = {package_relative_path(name): digest for digest, name in lines}
            if len(expected) != len(lines) or expected != EvidencePackage._hashes_at(root):
                raise ValueError('Files missing, added, or changed after seal')
        except (OSError, ValueError) as exc:
            raise ContractError('evidence_integrity_failure', str(exc)) from exc
        return True
