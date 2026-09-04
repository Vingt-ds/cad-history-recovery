# Gate 3 closure report

- Formal run: `gate3-formal-20260904-8e8ae63`
- Code commit at run start: `8e8ae6333ae77c5c4d91053855398adfaf077833`
- Frozen validation protocol SHA-256: `d0372098d2403d8cf96eb5c269354cf5c936b9fdef09b52878a91acc3f99c662`
- Verification report SHA-256: `cdfcc563bbe1fed601c1ab17b8d9e290c5cc9f660024c5244ebfbb085d1a2210`
- Fusion replay: 5 success, 0 failure
- Automatic terminal success: 5/5
- Frozen geometry protocol pass: 5/5
- Analytic hole-feature match pass: 5/5
- Complete result packages: 5/5
- Ambiguous accepted histories: 0
- Manual success: 0
- Failed: 0
- Unsupported: 0
- Stop-loss triggered: no
- Gate decision: PASS

Gate 3 recovers one normalized `Base Sketch -> New Extrusion -> Circle Sketch on operation_cap -> Through-all Cut` construction explanation. The inference is coupled: it matches the two planar base end faces by their Line-only outer wires while preserving paired circular inner wires and their shared cylindrical face as Cut evidence. It does not run the Gate 2 base-only acceptance rule and append a Cut afterward.

The formal result is limited to the five frozen development cases `D-H01` through `D-H05`. Each case was inferred without manual correction, replayed in a fresh Fusion document, exported to native F3D and STEP, and finalized independently. Fusion reported version `2704.1.53`, embedded Python `3.14.0`, one body and seven faces for every replay, with `world_frame_max_error_mm=0.0`.

## Validation evidence

The frozen Gate 3 protocol requires one valid solid, volume agreement, six-coordinate bounding-box agreement, and analytic agreement of the recovered through-hole radius, undirected axis, axis-line position, two opening centres, and span. These feature checks were added because validity, volume and bounding box alone cannot distinguish a translated hole with unchanged radius and span. All five formal replays pass both the base geometry checks and the analytic hole-feature checks. Surface p95 remains `diagnostic_only`; no uncalibrated universal surface threshold is claimed.

The independent `gate3-verifier-0.2` report records the geometry and feature-match outcomes separately. It also confirms the frozen case set and benchmark hashes, clean Git state at run start, validation-protocol hash, absence of post-hoc unsupported relabelling, and 5/5 conditional result-package completeness.

Primary evidence:

- `benchmark_results/gate3-formal-20260904-8e8ae63/gate3_verification_report.json`
- `benchmark_results/gate3-formal-20260904-8e8ae63/finalization_summary.json`
- `benchmark_results/gate3-formal-20260904-8e8ae63/batch_replay_log.json`
- `benchmark_results/gate3-formal-20260904-8e8ae63/evidence/fusion_batch_success.png`
- `benchmark_results/gate3-formal-20260904-8e8ae63/replay_request_used.json`

## Scientific boundary

This Gate supports exactly one straight through cylindrical Cut normal to the paired planar caps of one simple Line-only base extrusion, with two explicit circular openings and one connecting cylindrical face. Convexity is retained only as diagnostic evidence. CadQuery validates complete hypotheses and does not invent them.

The result does not establish blind, tapered, stepped, counterbored, countersunk, threaded, multiple, patterned, intersecting or non-circular hole recovery. It does not use the held-out split, does not claim generalization to arbitrary B-reps, and does not claim recovery of the designer's unique original history. It demonstrates a deterministic, plausible and Fusion-replayable construction explanation within the frozen development scope.
