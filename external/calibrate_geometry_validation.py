"""Write the Gate 1 deterministic surface-distance calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path

from geometry_validation import calibrate_baseline


def main():
    root = Path(__file__).resolve().parents[1]
    reference = Path("benchmarks") / "inputs" / "development" / "D-S01.step"
    roundtrip = Path("benchmarks") / "calibration" / "D-S01_cadquery_roundtrip.step"
    report_path = root / "logs" / "gate1_geometry_baseline.json"
    report = calibrate_baseline(reference, roundtrip)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(
        "GATE1_GEOMETRY_BASELINE "
        f"same_repeatable={report['repeatability']['same_file_exact']} "
        f"roundtrip_repeatable={report['repeatability']['roundtrip_exact']}"
    )


if __name__ == "__main__":
    main()
