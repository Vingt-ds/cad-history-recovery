# Gate 3 Checkpoint 2: Pre-Validation Coupled Base-and-Hole Candidates

## Scope

- Branch: `gate3-single-through-hole`
- Input facts: `through-hole-facts-0.1`
- Candidate schema: `coupled-through-hole-candidates-0.1`
- Development cases: `D-H01` through `D-H05`
- Controlled negative: temporary cylindrical boss, outside the frozen benchmark
- Held-out geometry used: none
- Downstream CAD execution and geometric validation: not performed

Checkpoint 2 generates candidates only from accepted paired-hole fact groups. It does not call the Gate 2 all-planar-face-pair generator. The two planar faces associated with the paired circular inner wires are the only allowed base end-face pair, and their Line-only outer wires are matched independently of the circular inner wires.

The Gate 3 development entry point derives exactly `D-H01` through `D-H05` from the frozen matrix using only `case_id`, `split`, `family`, `output_step`, `source`, and top-level `units`. It returns no expected labels or geometry fields. Before any STEP inspection, its path guard rejects held-out paths with `held_out_input_forbidden`, rejects paths outside the five frozen development inputs, and rejects case-ID/path mismatches. The core fact-analysis and candidate-generation functions remain independent of this development-only guard.

## Development result

| Case | Coupled candidate | Base end faces | Outer wires | Matched outer edges | Base direction | Distance (mm) | Cut direction | Status |
| --- | --- | --- | --- | ---: | --- | ---: | --- | --- |
| D-H01 | `coupled-face-002-face-003-face-004` | `face-002`, `face-003` | `wire-002`, `wire-003` | 4 | `[0, 0, 1]` | 20.0 | `[0, 0, -1]` | accepted |
| D-H02 | `coupled-face-004-face-005-face-006` | `face-004`, `face-005` | `wire-002`, `wire-003` | 4 | `[0, 0, 1]` | 24.0 | `[0, 0, -1]` | accepted |
| D-H03 | `coupled-face-000-face-001-face-002` | `face-000`, `face-001` | `wire-001`, `wire-004` | 4 | `[0, 1, 0]` | 18.0 | `[0, -1, 0]` | accepted |
| D-H04 | `coupled-face-002-face-003-face-004` | `face-002`, `face-003` | `wire-001`, `wire-007` | 4 | `[1, 0, 0]` | 21.0 | `[-1, 0, 0]` | accepted |
| D-H05 | `coupled-face-002-face-003-face-004` | `face-002`, `face-003` | `wire-001`, `wire-004` | 4 | `[0, 1, 0]` | 20.0 | `[0, -1, 0]` | accepted |

Every development candidate passes ten recorded hard checks:

1. accepted paired-hole fact group;
2. both end-face orientations are explicitly `forward` or `reversed`;
3. opposite end-face outward normals;
4. positive base distance;
5. measured Cut direction into material from the selected support face, requiring the support-face outward-normal dot Cut-direction to be approximately `-1`;
6. end-face centroid alignment;
7. outer-wire translation match;
8. corresponding outer-side-face coverage;
9. undirected hole-axis alignment with the base extrusion;
10. cylinder span equal to base distance.

The selected base face is the lower canonical face ID. The base direction points from that face to the opposite face, distance is positive, the semantic support target is the candidate base operation's `positive_end_cap`, and the prospective Cut direction points from that cap back into the body. This is a deterministic pre-validation construction hypothesis, not evidence of the original modeling direction or feature history.

## Rejected routes

- The unrelated rectangular side-face pairs previously accepted by Gate 2 are never generated because they are not the two planar faces incident to the paired circular inner wires.
- Circular inner edges are excluded from `matched_outer_edge_pairs`; all five development cases match exactly four Line edges.
- The controlled cylindrical boss produces no coupled candidate because its Checkpoint 1 hole fact group is rejected.
- Changing adjacency diagnostics between `convex` and `concave` does not change candidate acceptance.
- A zero end-face centroid separation returns a rejected candidate without division by zero; `positive_base_distance` fails with reason code `base_distance_not_positive`, and all recorded numeric measurements remain finite.
- Candidate and hole-fact-group `rejection_reasons` contain the failed checks' structured reason codes rather than check names.
- An end face labelled `internal`, `external`, or any other unsupported orientation is not treated as `forward`: `supported_end_face_orientations` fails with `unsupported_end_face_orientation`, and dependent normal/Cut measurements remain finite and fail where appropriate.
- Accepted fact groups are checked structurally before construction: paired IDs must be distinct strings, axis/radius measurements must be finite and physically valid, and referenced cylinder/planar faces, circular/Line edges, and inner/outer wires must resolve with the required face-wire incidence. Malformed artifacts fail with `malformed_candidate_facts`.

## TDD evidence

1. The public API test failed before `generate_coupled_candidates` existed.
2. Five development-case, outer-wire isolation, semantic-cap direction, convexity-independence, and boss-negative tests failed against the empty candidate implementation.
3. The artifact-mismatch test failed before schema, model ID, and source STEP hash checks were added.
4. A negative-zero serialization test failed on the initial Cut direction and passed only after vector sign normalization was added.
5. The Gate 3 selector test failed before the development-only matrix selector existed. Separate guard tests then failed before held-out, outside-frozen-input, and ID/path-mismatch rejection were implemented.
6. The zero-centroid test reproduced a `ZeroDivisionError` before the guarded direction calculation and structured candidate rejection were implemented.
7. The support-normal linkage test failed because no measured hard check existed; it passed after candidate acceptance included the selected support face's outward-normal dot Cut-direction measurement.
8. The controlled-boss reason assertion failed while group rejection reasons still contained check names; it passed after reason-code propagation.
9. Summary- and adjacency-schema mutation tests failed because candidate generation accepted both unsupported tags; they passed after explicit public-boundary schema checks were added ahead of construction.
10. Removing a required planar role from an accepted group produced a raw `KeyError`; it passed after the accepted-group and planar-role structure was validated explicitly with stable code `malformed_candidate_facts`.
11. `internal`, `external`, and `unknown` end-face orientations initially had no hard check and were treated as forward; they passed after explicit orientation measurement and safe zero-normal handling were added.
12. A patched `_coupled_candidate` raising `TypeError("internal regression")` was initially masked as `malformed_candidate_facts`; it passed after removing the broad construction catch so internal runtime regressions propagate unchanged.
13. A missing circle-edge reference produced a raw `KeyError`, a nonnumeric measured axis produced a raw `TypeError`, and a circular inner wire substituted as an outer wire was not rejected at the public boundary. All three passed after explicit canonical-reference, primitive-type, measurement, and incidence validation; the internal-regression propagation test remained green.

Baseline focused module before these review fixes: 19/19 tests passed.

Final verification:

- focused Gate 3 module: 32/32 tests passed;
- full repository unit suite: 201/201 tests passed;
- Gate 0 verifier: 22/22 checks passed;
- Gate 1 verifier: 8/8 checks passed;
- immutable Gate 2 formal verifier: `gate_pass=true`, 10/10 automatic success, 10/10 geometry pass, and 10/10 complete packages.

## Checkpoint decision

Checkpoint 2 deterministically identifies one pre-validation coupled base-and-through-hole candidate for each of `D-H01` through `D-H05`. Matched outer wires support the base portion of the hypothesis, while the circular inner wires remain separate Cut evidence. This checkpoint does not establish an executable construction or validate the candidate's final geometry.
