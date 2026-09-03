# Gate 2 Task 8: Fusion Replay Adapter

## Reuse decision

The Gate 1 executor remains the single Sketch/New Extrude replay core. Its `_run_sequence` function gained one optional `plane_resolver=None` parameter; the default Gate 1 path and all existing Gate 1 semantics remain unchanged. The bounded copy fallback was not used.

## Gate 2 adapter contract

- Reads one `gate2-replay-0.1` batch request.
- Requires D-S01 through D-S10 exactly once, with non-rectangular D-S04 first.
- Rejects project-path escape and refuses to overwrite any F3D, STEP, case replay log, or batch replay log.
- Opens a fresh Fusion document per case and closes it without saving after exports.
- Uses `ConstructionPlaneInput.setByOffset` for axis-aligned inferred frames and `ConstructionPlaneInput.setByAngle` about a parametric construction axis for rotated inferred frames.
- Reuses the Gate 1 world-to-sketch and sketch-to-world checks for every declared point.
- Preserves structured errors raised by the reused Gate 1 core and isolates failures by case.
- Records Fusion and Fusion-Python versions in the run-level environment snapshot.

The original checkpoint preceded Fusion runtime execution. The first parametric-environment attempt exposed that `setByPlane` was direct-modeling-only; that failed run remains preserved under `benchmark_results/gate2-formal-20260903-ed117e8/`. The final adapter no longer uses `setByPlane`, and the completed formal batch `gate2-formal-20260903-e93dc2f` records 10 successes and 0 failures.

## Automated verification

- Gate 2 adapter focused tests: 7 tests, 0 failures.
- Gate 2 adapter, pipeline, and Gate 1 executor focused regression: 22 tests, 0 failures.
- Full repository regression: 151 tests, 0 failures.
