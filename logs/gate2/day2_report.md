# Gate 2 Day 2: Minimal Attributed Adjacency

## Scope

- Shared canonical edge IDs are the only source of face-face adjacency.
- The implementation uses ordinary dictionaries and does not introduce a graph library.
- Face 1 is the lower canonical face ID.
- Both local outward normals are evaluated at the same point on the shared edge.
- The tangent is corrected by the edge-use orientation in Face 1.
- Seam uses that reference only one distinct face do not create self-adjacency.
- Kernel local-evaluation failures are recorded as `unknown`; unexpected programming errors propagate.

## Frozen sign convention evidence

The evaluated angle is:

`atan2(t dot (n1 cross n2), n1 dot n2)`

The following development evidence fixes the sign mapping for later candidate work:

| Case | Relations | Convex | Concave | Observed signed angles |
| --- | ---: | ---: | ---: | --- |
| D-S01 | 12 | 12 | 0 | all `+1.570796326795` rad |
| D-S04 | 18 | 17 | 1 | 17 at `+1.570796326795`; 1 at `-1.570796326795` rad |
| D-S07 | 2 | 2 | 0 | both `+1.570796326795` rad |

Therefore, within the tested convention:

- positive angle: `convex`
- negative angle: `concave`
- absolute angle at or below `1e-8` rad: `smooth`
- unreliable local evaluation: `unknown`

D-S07 has three unique edges, but only its two circular cap boundaries produce distinct face pairs. The repeated cylindrical seam edge remains a single-face use and is excluded.

## Verification

- Focused adjacency suite: 6 tests, 0 failures.
- Required geometry assertions cover box convexity, L-shape concavity, cylindrical local normals, seam exclusion, symmetric references, the structured unknown path, and propagation of unexpected errors.
