"""Gate 0 CadQuery generation, STEP import, and topology smoke checks."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import traceback
from pathlib import Path
from typing import Any

from gate0_common import load_gate0_config, sha256_file


def distribution_version(*names: str) -> str:
    """Return the first installed distribution version among equivalent names."""
    last_error: importlib.metadata.PackageNotFoundError | None = None
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("at least one distribution name is required")


def ocp_version() -> str:
    try:
        return distribution_version("cadquery-ocp", "ocp")
    except importlib.metadata.PackageNotFoundError:
        import OCP

        return str(OCP.__version__)


def inspect_step(cq: Any, path: Path) -> dict[str, Any]:
    imported = cq.importers.importStep(str(path))
    shape = imported.val()
    return {
        "path": str(path),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "valid": bool(shape.isValid()),
    }


def run(project_root: Path) -> dict[str, Any]:
    import cadquery as cq

    config_path = project_root / "config" / "gate0_box.json"
    config = load_gate0_config(config_path)
    model = config["model"]
    models = project_root / "models"
    models.mkdir(parents=True, exist_ok=True)

    generated_path = models / "cadquery_box.step"
    box = cq.Workplane("XY").box(
        model["width"],
        model["depth"],
        model["height"],
        centered=(False, False, False),
    )
    cq.exporters.export(box, str(generated_path))

    paths = {
        "cadquery_box": generated_path,
        "fusion_run01": models / "fusion_script_box_run01.step",
        "fusion_run02": models / "fusion_script_box_run02.step",
        "manual_box_hole": models / "manual_box_hole.step",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("required STEP file(s) missing: " + ", ".join(missing))

    checks = {name: inspect_step(cq, path) for name, path in paths.items()}
    expected = {
        "cadquery_box": (1, 6, 12),
        "fusion_run01": (1, 6, None),
        "fusion_run02": (1, 6, None),
        "manual_box_hole": (1, None, None),
    }
    failures: list[str] = []
    for name, (solid_count, face_count, edge_count) in expected.items():
        item = checks[name]
        if not item["valid"] or item["solid_count"] != solid_count:
            failures.append(f"{name}: invalid or solid_count != {solid_count}")
        if face_count is not None and item["face_count"] != face_count:
            failures.append(f"{name}: face_count != {face_count}")
        if edge_count is not None and item["edge_count"] != edge_count:
            failures.append(f"{name}: edge_count != {edge_count}")

    return {
        "status": "success" if not failures else "failure",
        "json_sha256": sha256_file(config_path),
        "versions": {
            "python": platform.python_version(),
            "cadquery": importlib.metadata.version("cadquery"),
            "cadquery_ocp": ocp_version(),
        },
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    log_path = args.project_root / "logs" / "external_python.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = run(args.project_root.resolve())
    except Exception as exc:
        result = {
            "status": "failure",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    log_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
