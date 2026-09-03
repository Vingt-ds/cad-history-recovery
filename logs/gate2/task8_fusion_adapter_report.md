# Gate 2 Task 8: Fusion Replay Adapter

## Reuse decision

The Gate 1 executor remains the single Sketch/New Extrude replay core. Its `_run_sequence` function gained one optional `plane_resolver=None` parameter; the default Gate 1 path and all existing Gate 1 semantics remain unchanged. The bounded copy fallback was not used.

## Gate 2 adapter contract

- Reads one `gate2-replay-0.1` batch request.
- Requires D-S01 through D-S10 exactly once, with non-rectangular D-S04 first.
- Rejects project-path escape and refuses to overwrite any F3D, STEP, case replay log, or batch replay log.
- Opens a fresh Fusion document per case and closes it without saving after exports.
- Uses `Plane.create` and `ConstructionPlaneInput.setByPlane` for arbitrary inferred B-rep absolute frames.
- Reuses the Gate 1 world-to-sketch and sketch-to-world checks for every declared point.
- Preserves structured errors raised by the reused Gate 1 core and isolates failures by case.
- Records Fusion and Fusion-Python versions in the run-level environment snapshot.

No actual Fusion replay success is claimed by this checkpoint. Fusion runtime evidence must be produced by the single formal batch launch.

## Automated verification

- Gate 2 adapter focused tests: 7 tests, 0 failures.
- Gate 2 adapter, pipeline, and Gate 1 executor focused regression: 22 tests, 0 failures.
- Full repository regression: 151 tests, 0 failures.
