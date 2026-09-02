# Gate 1 Verification Report

Overall status: **PASS** (8/8 checks passed)

| Status | Check | Detail |
| --- | --- | --- |
| PASS | `required_artifacts` | all present |
| PASS | `schema_validation` | known_valid=7/7; invalid_rejected=4/4 |
| PASS | `frame_replays` | success=6/6; max_world_error_mm=4.440892098500626e-15 |
| PASS | `semantic_and_failure_evidence` | semantic Cut reduced volume; explicit absolute fallback succeeded; first profile failure preserved |
| PASS | `box_stability` | 3/3 artifacts audited; geometry_signatures=1; volume_mm3=48000.0 |
| PASS | `box_hole_stability` | 3/3 artifacts audited; geometry_signatures=1; volume_mm3=46429.203673205106 |
| PASS | `benchmark_freeze` | 30 cases; 15 development; 15 held_out; all hashes match |
| PASS | `geometry_baseline` | self and roundtrip repeatable; calibration symmetric_p95_mm=1.4268324398403818; no general threshold |
