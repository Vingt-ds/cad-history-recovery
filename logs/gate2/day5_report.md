# Gate 2 Day 5: CadQuery Validation and Frozen Threshold Protocol

## Calibration outcome

- Active protocol SHA-256: `8656e3882ee8c71c310b3ad5afe85177cf8e1d2e67d1bff6d03e13d64148c05a`
- Sampling: 4096 total points, at least 32 per face, common seed derived from the frozen reference STEP SHA-256.
- Hard volume limit: `1e-6 mm3 + 1e-9 * reference_volume_mm3`.
- Hard six-coordinate bbox tolerance: `1e-6 mm`.
- Controlled perturbation: `+5 mm` global X translation for D-S01, D-S04, D-S07, and D-S09; these artifacts are not benchmark members.
- All repeated surface calculations were numerically identical.

The normalized round-trip and controlled-perturbation intervals were disjoint for both surface metrics. The active protocol therefore freezes calibrated midpoint thresholds:

- `symmetric_p95_ratio <= 0.04029243657040586`
- `max_face_p95_ratio <= 0.04092444541325745`

Both ratios use the reference bbox diagonal in millimetres. These values come from Gate 2 calibration evidence and are not a multiple of the Gate 1 D-S01 baseline.

The first independent-file-seed protocol was preserved and explicitly superseded after a RED test demonstrated nondeterministic candidate ordering across byte-different exports of identical geometry. See `logs/gate2/calibration/revision_log.md`.

## Post-CadQuery final ranking

| Case | Qualified | Ambiguous | Selected candidate | Distance (mm) | Geometry pass |
| --- | ---: | --- | --- | ---: | --- |
| D-S01 | 3 | true | `extrusion-face-002-face-003` | 20 | true |
| D-S02 | 1 | false | `extrusion-face-001-face-002` | 16 | true |
| D-S03 | 1 | false | `extrusion-face-000-face-001` | 14 | true |
| D-S04 | 1 | false | `extrusion-face-006-face-007` | 18 | true |
| D-S05 | 1 | false | `extrusion-face-008-face-009` | 15 | true |
| D-S06 | 1 | false | `extrusion-face-001-face-002` | 22 | true |
| D-S07 | 1 | false | `extrusion-face-001-face-002` | 28 | true |
| D-S08 | 1 | false | `extrusion-face-000-face-001` | 17 | true |
| D-S09 | 3 | true | `extrusion-face-004-face-005` | 26 | true |
| D-S10 | 1 | false | `extrusion-face-000-face-001` | 13 | true |

All selected candidates have zero reported volume error, zero six-coordinate bbox error, and pass both frozen surface thresholds. D-S01 and D-S09 remain explicitly ambiguous because three candidate histories pass. The deterministic ranking does not force the original generator history; D-S09 selects the 26 mm canonical alternative under the frozen ranking order.

Candidate STEP files, per-candidate metrics, final ranking, and selected sequences are preserved under `logs/gate2/day5/<case_id>/`.

## Verification

- Focused validation/calibration suite: 9 tests, 0 failures.
- Full repository regression: 137 tests, 0 failures.
- The cross-export determinism regression compares exact surface sort values from two independent candidate exports.
