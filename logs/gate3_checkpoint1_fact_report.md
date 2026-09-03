# Gate 3 Checkpoint 1: Wire Roles and Paired-Circle Facts

## Scope

- Branch: `gate3-single-through-hole`
- Contract: `docs/gate3_coupled_hypothesis_contract.md`
- Development inputs: `D-H01` through `D-H05`, derived from the frozen `case_matrix.json`
- Controlled negative: one temporary CadQuery box with a cylindrical boss; it is not part of the frozen benchmark
- Held-out geometry used: none
- Sequence generation, Cut inference, candidate ranking, Fusion replay, correction, and terminal status: not started

Checkpoint 1 adds `external/through_hole_inference.py`. Its `analyze_through_hole_facts(summary, adjacency)` function consumes an existing single-import B-rep summary and matching adjacency dictionary; it performs no second STEP import.

## Development evidence

| Case | Planar faces with resolved outer/inner roles | Cylinder face | Full-circle edges | Radius (mm) | Kernel axis | Rim adjacency diagnostic | Fact result |
| --- | ---: | --- | --- | ---: | --- | --- | --- |
| D-H01 | 2 | `face-004` | `edge-004`, `edge-005` | 5.0 | `[0, 0, 1]` | convex, convex | accepted |
| D-H02 | 2 | `face-006` | `edge-004`, `edge-005` | 4.0 | `[0, 0, 1]` | convex, convex | accepted |
| D-H03 | 2 | `face-002` | `edge-005`, `edge-006` | 4.5 | `[0, 1, 0]` | convex, convex | accepted |
| D-H04 | 2 | `face-004` | `edge-001`, `edge-011` | 4.0 | `[-1, 0, 0]` | convex, convex | accepted |
| D-H05 | 2 | `face-004` | `edge-004`, `edge-005` | 5.0 | `[0, -1, 0]` | convex, convex | accepted |

Each accepted fact group contains one cylindrical face, two distinct full-circle edges, two different planar faces, two different inner circular wires, finite equal radii, centres on the cylinder axis, and a positive coaxial separation. Line-only outer wires and full-circle inner wires are classified from primitive content and incidence rather than face-wire traversal order.

The axis is preserved as a kernel fact only. D-H04 and D-H05 demonstrate why its sign cannot be treated as the future Cut direction.

## Controlled negative

The temporary cylindrical boss also contains a cylindrical face and two full-circle boundary edges. It is rejected because only one circle belongs to an inner wire on a resolved Line-outer planar face; the other belongs to the boss's circular outer cap. The structured failed check is `circles_on_two_planar_inner_wires`, and the report-level reason is `no_accepted_hole_fact_group`.

This negative proves that `cylinder + two circles` alone is not the implemented acceptance rule. It does not prove rejection of every possible boss topology; broader negative coverage belongs to the later coupled-candidate checkpoint.

## Convexity finding

Both rim relations remain labelled `convex` in every development case. A test relabels adjacency diagnostics between `convex` and `concave` and confirms that fact-group acceptance is unchanged. Convexity is therefore diagnostic-only in Checkpoint 1. No hole-specific material-side convention is claimed.

## TDD evidence

The implementation followed explicit RED-to-GREEN cycles:

1. The missing module test failed before `external/through_hole_inference.py` was created.
2. The missing public API test failed before `analyze_through_hole_facts` was added.
3. The development, wire-order, convexity-independence, boss-negative, and no-cylinder tests failed against the empty implementation before the fact analyzer was written.
4. The structured-error artifact test failed before `ThroughHoleInferenceError` was added.
5. The summary/adjacency mismatch test failed before model ID and source-hash validation was implemented.
6. The unsupported-schema test failed before the analyzer enforced `brep-summary-0.1` and `face-adjacency-0.1`.

Focused result: 11 tests passed, 0 failures.

Repository regression after Checkpoint 1: 180 tests passed, 0 failures. The read-only Gate 0 and Gate 1 verifiers remain 22/22 and 8/8. The immutable Gate 2 formal verifier remains `gate_pass=true` with 10/10 automatic success, 10/10 geometry pass, 10/10 complete packages, and the original two ambiguous histories.

## Checkpoint decision

Checkpoint 1 passes its limited purpose: the existing fact layer can deterministically identify the narrow paired-circle and wire-role evidence in all five development cases while rejecting the controlled boss and ignoring the unvalidated convexity label.

This is not yet automatic through-hole recovery. Checkpoint 2 must jointly identify the base end-face pair from the Line-only outer wires, preserve the paired inner circles as Cut evidence, reject unrelated side-face extrusion explanations, and validate the complete New-plus-Cut reconstruction rather than the base alone.
