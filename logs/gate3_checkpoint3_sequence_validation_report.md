# Gate 3 Checkpoint 3: Four-Operation Sequence and External Reconstruction Validation

## Scope and boundary

- Branch starting point: `gate3-single-through-hole` at `411cb07`.
- Development inputs: `D-H01` through `D-H05` only.
- Recovered scope: one Line-only outer profile, one New distance Extrusion, one circular Sketch on the New Extrusion's `positive_end_cap`, and one through-all Cut Extrusion.
- Held-out geometry inspected: none.
- Fusion replay performed: none.

This checkpoint validates deterministic sequence synthesis and an external CadQuery reconstruction. It is not evidence of Fusion success, it does not freeze final Gate 3 acceptance thresholds, and it does not close Gate 3.

## Implemented construction

`external/through_hole_reconstruction.py` consumes the Checkpoint 2 accepted coupled candidate. The development entry point applies the existing case/path guard before a single STEP import, derives the B-rep summary, adjacency, through-hole facts, and coupled candidates from that import, requires exactly one accepted candidate, and returns those evidence objects with the sequence. It does not read or return `expected_scope`, `expected_behavior`, or `geometry` fields.

The Base Sketch reuses the Gate 2 root-frame rules but explicitly selects the candidate's Line-only outer wire incident to the base face. The circular inner wire is excluded. The support circle is resolved by the actual support-face to inner-wire to circular-edge incidence chain; no positional pairing of candidate lists is used. Its 3D centre is projected into the deterministic hole frame, and its radius is checked against candidate evidence. The hole frame uses an `operation_cap` semantic reference with no `frame_source`.

The external rebuilder first runs `shared/sequence_validator.py` against the supplied sequence. It resolves the hole Sketch specifically against `extrude_base.positive_end_cap`, constructs a one-sided circular tool along the supplied Cut direction for twice the available base distance, and subtracts that tool from the New solid. The Boolean must reduce volume or reconstruction stops with `boolean_no_intersection` before writing output. The rebuilder requires one valid final solid and refuses to overwrite an existing STEP. It receives no summary or candidate and therefore does not generate or select candidates.

## Development sequence evidence

All cases produced exactly one accepted, canonical `cadseq-0.2` sequence with four operations, `replay_mode=automatic`, and `corrections=[]`. Every sequence passed the shared validator.

| Case | Coupled candidate | Base frame source | Base Lines | Support face | Hole centre in cap frame | Radius (mm) | Cut direction |
| --- | --- | --- | ---: | --- | --- | ---: | --- |
| D-H01 | `coupled-face-002-face-003-face-004` | `origin_named` | 4 | `face-003` | `[27.5, 19.0]` | 5.0 | `[0, 0, -1]` |
| D-H02 | `coupled-face-004-face-005-face-006` | `origin_named` | 4 | `face-005` | `[53.0, 10.0]` | 4.0 | `[0, 0, -1]` |
| D-H03 | `coupled-face-000-face-001-face-002` | `origin_named` | 4 | `face-001` | `[10.0, -19.0]` | 4.5 | `[0, -1, 0]` |
| D-H04 | `coupled-face-002-face-003-face-004` | `inferred_brep` | 4 | `face-003` | `[9.29191409, -4.129739596]` | 4.0 | `[-1, 0, 0]` |
| D-H05 | `coupled-face-002-face-003-face-004` | `origin_named` | 4 | `face-003` | `[30.0, 20.0]` | 5.0 | `[0, -1, 0]` |

D-H04 is the offset canonical case requiring an `inferred_brep` root frame. It remains automatic and has no correction or manual fallback.

## External reconstruction metrics

Validation reused `candidate_validation.validate_replay_step` with the checkpoint-local `gate3-checkpoint3-validation-0.1` protocol. Single-solid validity, volume, and each of the six bounding-box coordinates are hard conditions. Surface-distance values are recorded only as diagnostics: `surface.mode=diagnostic_only` and `surface_pass=null`. The frozen Gate 2 surface thresholds were not used as Gate 3 acceptance criteria.

| Case | Valid single solid | Volume error (mm3) | Volume pass | Max bbox-coordinate error (mm) | Bbox pass | Symmetric p95 (mm) | Max-face p95 (mm) | Hard result |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| D-H01 | true | 1.0913936421275139e-10 | true | 0.0 | true | 1.3161719297918708 | 1.4009749572778627 | pass |
| D-H02 | true | 3.2014213502407074e-10 | true | 0.0 | true | 1.527360441872883 | 1.6733782353635245 | pass |
| D-H03 | true | 2.546585164964199e-11 | true | 0.0 | true | 1.2658365202216577 | 1.3663529923596471 | pass |
| D-H04 | true | 1.964508555829525e-10 | true | 0.0 | true | 1.2843611727492126 | 1.3282936643528387 | pass |
| D-H05 | true | 5.820766091346741e-11 | true | 0.0 | true | 1.4983449323077134 | 1.509950825320741 | pass |

All six individual bounding-box coordinate errors were exactly `0.0` for every case. Surface values do not contribute to the hard result at this checkpoint.

A separate D-H01 negative rebuilt only the Base Sketch and New Extrusion, then applied the same final validator. It failed the hard volume check and `geometry_pass=false`; therefore a base-only result cannot be mistaken for successful final reconstruction.

## TDD evidence

Observed RED before production implementation:

1. The initial artifact check failed with `through_hole_reconstruction module is absent`.
2. After the minimal API skeleton was added, sequence tests failed because `sequence_from_summary` was not implemented and `reconstruct_profile` did not accept explicit `outer_wire_id` selection.
3. Development-entry tests failed while `recover_development_sequence` was not implemented.
4. Rebuild and validation tests failed while `rebuild_sequence_step` and `checkpoint3_validation_protocol` were not implemented.
5. A malformed paired-evidence test initially showed that a one-item outer-wire list was accepted and that missing inferred-frame provenance leaked a raw `KeyError`; both now raise structured `ThroughHoleReconstructionError` results.
6. Reversing only `cut_hole.direction` on the positive cap remained valid under the shared schema and initially produced a passing reconstruction because the first implementation used a bidirectional Cut. The direction-sensitive test now receives `boolean_no_intersection`, and no STEP is written.
7. Moving the hole Sketch to `negative_end_cap` and reversing the Cut direction also remained valid under the shared schema and initially produced equivalent geometry. The checkpoint-specific rebuilder now rejects that alternate history with `unsupported_operation_cap_role`.

Final verification after implementation:

- Focused Checkpoint 3 module: 17/17 tests passed.
- Full repository unit suite: 218/218 tests passed.
- Gate 0 read-only verifier: 22/22 checks passed.
- Gate 1 read-only verifier: 8/8 checks passed.
- Immutable Gate 2 formal verifier: `gate_pass=true`, 10/10 automatic success, 10/10 geometry pass, and 10/10 complete packages.

## Checkpoint decision

Checkpoint 3 passes its limited external-validation purpose for `D-H01` through `D-H05`: the accepted coupled evidence can be synthesized into a deterministic four-operation sequence and reconstructed by CadQuery with hard validity, volume, and bounding-box agreement. Fusion execution, Fusion artifacts, final Gate 3 threshold freezing, broader hole families, and Gate 3 closure remain out of scope.
