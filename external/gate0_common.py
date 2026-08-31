"""Shared Gate 0 configuration and hashing helpers."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when the shared Gate 0 JSON violates the fixed contract."""


def load_gate0_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read valid JSON from {config_path}: {exc}") from exc

    if data.get("schema_version") != "gate0-0.1":
        raise ConfigError("schema_version must be 'gate0-0.1'")
    if data.get("units") != "mm":
        raise ConfigError("units must be 'mm'")

    model = data.get("model")
    if not isinstance(model, dict) or model.get("type") != "box":
        raise ConfigError("model.type must be 'box'")

    for field in ("width", "depth", "height"):
        value = model.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"model.{field} must be numeric")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ConfigError(f"model.{field} must be finite and positive")

    return data


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
