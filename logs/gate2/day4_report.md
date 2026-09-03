# Gate 2 Day 4: Profile Reconstruction and cadseq-0.2

## Frozen profile scope

- one simple Line-only outer loop with 3--8 edges; or
- one standalone complete Circle.

The implementation explicitly rejects multiple/inner loops, mixed Line/Circle loops, circular arcs, BSplines, unsupported edge-use orientation, open chains, degenerate edges/area, and self-intersection. Line loops are projected into a deterministic right-handed frame and normalized to positive signed area.

## Frame contract

- A cap on a global zero-offset XY/XZ/YZ plane uses `frame_source=origin_named`, the Fusion named-plane normal/x-axis, and an independent signed Extrude direction.
- Every other root plane uses `frame_source=inferred_brep` and `semantic_reference.type=absolute_frame` with `replay_mode=automatic`.
- The inferred frame normal equals the base-to-opposite centroid direction; distance is positive.
- `source_face_outward_normal` is retained separately and must oppose the inferred frame normal.
- The inferred x-axis is projected global X, with projected global Y as the defined degeneracy fallback.
- No automatically inferred frame creates a correction record.
- `operation_cap` remains exempt from `frame_source`; manual absolute fallback still requires a complete correction audit.

## Required offset-frame evidence

| Case | Frame source | Canonical frame normal | Profile primitives | Distance (mm) | Corrections |
| --- | --- | --- | ---: | ---: | ---: |
| D-S03 | `inferred_brep` | `[0, 0, 1]` | 5 Line | 14 | 0 |
| D-S05 | `inferred_brep` | `[0, -1, 0]` | 8 Line | 15 | 0 |
| D-S06 | `inferred_brep` | `[-1, 0, 0]` | 8 Line | 22 | 0 |
| D-S08 | `inferred_brep` | `[0, -1, 0]` | 6 Line | 17 | 0 |
| D-S10 | `inferred_brep` | `[1, 0, 0]` | 7 Line | 13 | 0 |

These directions describe canonical normalized histories and are not labels copied from the matrix generator. Their sign may differ from the historical generator direction while producing the same solid.

Canonical inferred sequences are preserved under `logs/gate2/day4/<case_id>/sequence/inferred_sequence.json`.

## Schema verification

- cadseq-0.2 focused schema/profile suite: 15 tests, 0 failures.
- cadseq-0.1 focused regression: 24 tests, 0 failures.
- v0.2 adds only frame provenance and `automatic` replay semantics; it adds no CAD operation.
