# Gate 2 Day 3: Fact-Derived Extrusion Candidates

## Scope and ordering

- Every unordered planar face pair is retained exactly once.
- Candidate generation consumes only the canonical B-rep summary and minimal adjacency derived from the same single STEP import.
- No case-matrix expectation, held-out input, CadQuery reconstruction metric, or Fusion result enters inference.
- Each candidate records six hard checks, their measurements and tolerances, an unweighted passed-check count, and structured rejection reasons.
- Pre-validation order is `passed_hard_checks` descending, then canonical candidate ID.
- `ambiguous` is intentionally absent before post-CadQuery acceptance and final ranking.

## Development evidence

| Case | Planar-pair candidates | Accepted | Accepted canonical distances (mm) |
| --- | ---: | ---: | --- |
| D-S01 | 15 | 3 | 40, 20, 60 |
| D-S04 | 28 | 1 | 18 |
| D-S07 | 1 | 1 | 28 |
| D-S09 | 15 | 3 | 19, 48, 26 |
| D-S10 | 36 | 1 | 13 |

D-S01 and D-S09 correctly retain three geometrically valid cuboid histories. They are not prematurely collapsed to the generator's historical plane. D-S04 and D-S10 admit only the translated polygon-cap pair. D-S07 admits the translated full-circle caps and never treats the cylindrical side face as a planar end face.

Canonical `candidates.json` evidence is preserved under `logs/gate2/day3/<case_id>/analysis/` for all five required development cases. Rejected candidates remain in those files.

## Hard checks

1. opposite local outward normals;
2. positive centroid separation;
3. centroid displacement aligned with the face normal;
4. end-face area match;
5. translated Line endpoints or translated full-circle parameters;
6. matched cap edges connected through the same side faces.

## Verification

- Focused inference suite: 7 tests, 0 failures.
- Deterministic repeated inference is byte-serializable through the canonical JSON writer.
