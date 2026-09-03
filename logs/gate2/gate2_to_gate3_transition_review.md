# Gate 2 to Gate 3 Transition Review

## Review status and evidence boundary

- Review baseline: `main@37b28f10b159c045dfd0882cabe93541372d0b6b`
- Gate 2 formal run: `gate2-formal-20260903-e93dc2f`
- Gate 2 completion tag: `gate2-forward-path` at commit `5f755d6ba92bd47e48553209ac55c71b41485099`
- Gate 2 decision: closed and unchanged
- Gate 3 pre-check inputs: development cases `D-H01` through `D-H05` selected from the frozen `case_matrix.json`
- Held-out geometry used in this review: none

This is a forward transition review, not a second Gate 2 pass/fail review. It must not reopen the frozen Gate 2 case set, schemas, threshold protocol, formal result packages, accepted histories, ambiguity records, or completion tag.

## Assets that Gate 3 must preserve

The following are architectural invariants rather than optional implementation preferences:

1. STEP-derived facts remain separate from feature hypotheses.
2. CadQuery validates fact-derived candidates; it does not invent candidates by searching construction programs.
3. Pre-validation ordering uses only available B-rep evidence. Reconstruction metrics enter only after a candidate has been built.
4. Canonical serialization, topology identity, input hashes, run manifests, and non-overwriting result directories remain auditable.
5. `terminal_status` and `ambiguous` remain independent fields.
6. Failed runs and failed cases remain preserved; labels are not changed after results are observed.
7. Fusion replay uses the shared, validated Sketch/New Extrude/Cut core and isolates failures by case.
8. Package completeness and geometric success remain separate measurements.
9. The output remains a deterministic, executable construction explanation, not a claim to recover the designer's unique original history.

## Reuse classification

### Direct reuse

- Single-import B-rep inspection and `brep-summary-0.1` serialization.
- Canonical Vertex, Edge, Wire, Face, and Solid identities and incidence references.
- Surface and curve facts, including cylinder axes/radii and full-circle edge parameters.
- Run-level environment snapshots, input metadata, immutable result-package layout, and completeness auditing.
- `cadseq-0.1`/`cadseq-0.2` dispatch and validation behavior.
- Gate 1 semantic `operation_cap` resolution and `cut + through_all` Fusion execution.
- Fusion fresh-document execution, world/sketch coordinate round-trip checks, exports, and structured replay logs.
- Geometric validity, volume, six-coordinate bounding-box, and frozen surface-diagnostic infrastructure.

### Reuse only as infrastructure

- Face-edge adjacency supplies incidence and local differential geometry, but its Gate 2 convex/concave label is not yet valid hole evidence.
- Gate 2 profile/frame code may construct the base outer profile and deterministic frame only after Gate 3 identifies which wires represent the retained base and which circles represent removed material.
- Gate 2 extrusion candidates provide reusable measurements, but the existing acceptance rules cannot recover the base extrusion directly from a perforated final solid.
- Cylinder `axis_direction` is an oriented kernel parameter, not the final Cut direction. Gate 3 must treat the hole axis as an undirected line until it selects a support cap and the direction into material.
- Gate 1 `operation_cap` replay is already implemented, but Gate 3 must infer and audit the semantic cap selection from the recovered base operation.

### Do not extend during Gate 3

- Blind holes, counterbores, countersinks, threads, tapered holes, or stepped holes.
- Multiple, intersecting, patterned, or coaxial multi-stage holes.
- Pockets, slots, arbitrary Cut profiles, Add/Join, fillets, or chamfers.
- Mixed Line/Circle base profiles, arcs, splines, or arbitrary face references.
- General feature graphs, graph search, graph neural networks, or a general CAD parser.
- Changes to the frozen benchmark, held-out labels, Gate 2 validation protocol, or Gate 2 formal evidence.

## Proposed narrow Gate 3 scope

Gate 3 may target one fact-derived construction explanation consisting of one supported base `new + distance` extrusion followed by one circular `cut + through_all`. The final B-rep must contain one straight cylindrical void whose two full-circle boundary edges lie on the two opposite planar end faces of the base extrusion. The two circles must have equal radii, coaxial centres, and a separation consistent with the base thickness.

This wording deliberately does not use "a cylinder implies a hole" or require the current adjacency layer to label the rim as concave. Material-removal interpretation must be established from topology, orientation, incidence, paired openings, and validation of the complete New-plus-Cut reconstruction.

## Gate 3 fact-layer sufficiency pre-check

The pre-check inspected only `D-H01` through `D-H05`. Each case produced one valid solid with the same high-level observable structure:

- 7 faces, 15 edges, 10 vertices, and 9 wires;
- 6 planar faces and 1 cylindrical face;
- 2 full-circle edges and 13 line edges;
- one reversed cylindrical face with a finite axis and radius;
- two planar faces with two wire uses each, representing an outer boundary plus a circular opening;
- no adjacency measurement recorded as `unknown`.

The fact layer is therefore sufficient to represent the required raw evidence. It is not yet sufficient to justify a through-hole history without new interpretation rules.

### Blocking findings before implementation

1. Both cylinder-to-planar-rim relations are currently classified as `convex` in all five development cases. A rule requiring `concave connection` would reject every intended case. Gate 3 must validate a hole-specific material-side convention or avoid using this label as a hard condition; expected labels must not be changed to fit the implementation.
2. The current Gate 2 inference rejects the physically intended base end-face pair in all five cases with `boundary_translation_match` and `side_connection_coverage`. The circular inner wires alter those checks.
3. The same inference accepts two unrelated pairs of opposite rectangular side faces in every case. Calling the current recovery path returns `ambiguous_prevalidation_candidates` for all five cases.
4. Consequently, Gate 3 cannot be implemented as "run Gate 2, then append Cut." It needs a separate coupled base-plus-hole hypothesis that matches the outer end-face wires as the base profile while preserving the paired inner circles as Cut evidence.
5. The base-only reconstruction must not be compared directly with the final perforated STEP as if they should have equal volume or surface geometry. Candidate acceptance must validate the complete New-plus-Cut reconstruction.

## Minimum new Gate 3 reasoning and evidence

Before Fusion replay, every candidate must preserve measured evidence for:

1. one cylindrical face with two distinct full-circle boundary edges;
2. equality of circle radii within a frozen numerical tolerance;
3. circle centres lying on one common undirected axis;
4. each circle belonging to an inner wire of a different planar end face;
5. parallel, opposite end faces and outer-wire translation consistent with one base extrusion;
6. cylinder span consistent with end-face separation;
7. deterministic selection of base face, positive operation cap, sketch frame, and Cut direction into the body;
8. explicit accepted and rejected reasons for all candidate hypotheses;
9. reconstruction and validation of the complete Sketch -> New Extrusion -> Sketch -> Through-all Cut sequence;
10. ambiguity, failure stage/code, replay evidence, geometry metrics, and conditional package artifacts.

The inner/outer wire classification, hole-specific orientation convention, tolerances, candidate ranking, and Gate 3 pass threshold are not frozen by this transition review. They require a separate Gate 3 implementation plan and development-only calibration before code changes. No Gate 3 success claim is made here.

## Transition decision

Gate 3 is ready for a bounded technical design, not immediate feature coding. The first design task is to specify and test the coupled base-extrusion plus single-through-hole hypothesis against `D-H01` through `D-H05`, beginning with wire-role and material-side conventions. Gate 2 remains closed regardless of the Gate 3 outcome.
