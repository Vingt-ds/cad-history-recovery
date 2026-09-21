"""Frozen specification binding and deliberately constrained JCS serialization."""
import hashlib
import json
import math
from pathlib import Path

SPECIFICATION_COMMIT = 'c440aace7306b9d68e2ae6a6ae757f36d8db1d85'
CONTRACT_PATH = 'docs/research_directions/gate6_precheck_v0_1.md'
CONFIG_PATH = 'config/gate6_precheck_v0_1.json'
FROZEN_SHA256 = {
    CONTRACT_PATH: '5356ccef2eb6b8aa7cd52584b2b0990a5690e160654d09427d7f0e260fbc8015',
    CONFIG_PATH: '9e81b6c3d119a53df8735969a29cb6b282539e460b3de22c415d81d71b896a6b',
}


class ContractError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_json_bytes(value):
    """RFC8785-compatible for this contract's restricted numeric domain.

    Integers are safe IEEE754 integers. Floats are ONLY zero, 0.5 and the
    contract's positive powers of ten (1e-12 through 1). Other floats fail
    closed rather than claiming general ECMAScript number serialization.
    Object keys use UTF-16 ordering; lone surrogates and non-JSON types fail.
    """
    def encode(item):
        if item is None:
            return 'null'
        if isinstance(item, bool):
            return 'true' if item else 'false'
        if isinstance(item, str):
            item.encode('utf-8', errors='strict')
            return json.dumps(item, ensure_ascii=False)
        if isinstance(item, int):
            if abs(item) > 2 ** 53 - 1:
                raise ValueError('Integer outside safe IEEE754 range')
            return str(item)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError('Nonfinite number')
            if item == 0:
                return '0'
            if item == 0.5:
                return '0.5'
            for exponent in range(-12, 1):
                if item == 10.0 ** exponent:
                    if exponent == 0:
                        return '1'
                    if exponent >= -6:
                        return '0.' + '0' * (-exponent - 1) + '1'
                    return '1e' + str(exponent)
            raise ValueError('Float outside constrained JCS domain')
        if isinstance(item, list):
            return '[' + ','.join(encode(v) for v in item) + ']'
        if isinstance(item, dict) and all(isinstance(k, str) for k in item):
            keys = sorted(item, key=lambda k: k.encode('utf-16-be'))
            return '{' + ','.join(encode(k) + ':' + encode(item[k]) for k in keys) + '}'
        raise ValueError('Not a JSON value')
    try:
        return encode(value).encode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise ContractError('schema_invalid', str(exc)) from exc


def _read_bound(repo_root):
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    for relative, expected in FROZEN_SHA256.items():
        try:
            actual = sha256_file(root / relative)
        except OSError as exc:
            raise ContractError('specification_binding_failure', str(exc)) from exc
        if actual != expected:
            raise ContractError('specification_binding_failure', f'Frozen bytes differ: {relative}')
    return json.loads((root / CONFIG_PATH).read_text(encoding='utf-8'))


def load_contract(repo_root=None):
    config = _read_bound(repo_root)
    canonical_json_bytes(config)
    return config


def validate_contract(config, repo_root=None):
    if canonical_json_bytes(config) != canonical_json_bytes(_read_bound(repo_root)):
        raise ContractError('specification_binding_failure', 'Parameters differ from frozen contract')
    return True
