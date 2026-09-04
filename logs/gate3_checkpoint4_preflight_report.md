# Gate 3 Checkpoint 4: Fusion Pre-flight and Validation Freeze

## Evidence boundary

- Development cases: `D-H01` through `D-H05`, derived only from the frozen matrix.
- Held-out geometry inspected: none.
- Fusion replay performed at this checkpoint: none.
- Debug evidence: `logs/gate3/debug_runs/gate3-cp4-preflight/`.
- Validation protocol: `config/gate3_validation_protocol.json`.
- Protocol SHA-256: `d0372098d2403d8cf96eb5c269354cf5c936b9fdef09b52878a91acc3f99c662`.

This checkpoint prepares the non-GUI analysis, result-package, Fusion adapter, and final verifier. It does not claim Gate 3 completion.

## Adversarial validation finding

The Gate 2 hard conditions cannot by themselves establish correct hole recovery. A controlled negative moved the reconstructed D-H01 hole centre by 1 mm while preserving a valid single solid, volume, and all six bounding-box coordinates. The generic validator therefore returned `geometry_pass=true` for the wrong hole location.

Gate 3 consequently adds feature-specific hard checks after STEP re-import:

- hole radius agreement;
- undirected cylinder-axis angular agreement;
- cylinder-axis line offset;
- both opening-centre positions;
- opening-to-opening span.

Each tolerance is `1e-6` in its stated linear unit, except the angular tolerance of `1e-8 rad`. These are comparisons of explicit STEP-derived analytic circle/cylinder facts, not sampled surface estimates. The 1 mm shifted-hole negative fails the axis-line and opening-centre checks and receives final `geometry_pass=false` even though the generic volume/bbox conditions pass.

Surface p95 remains `diagnostic_only`. A 3 mm controlled shift produced separation in `max_face_p95_ratio` for the five current cases, but that limited experiment does not justify a general surface threshold, especially for smaller offsets. No Gate 2 threshold is reused as a Gate 3 acceptance rule.

## Five-case non-GUI pre-flight

The immutable debug run selected exactly D-H01--D-H05. All five cases completed input validation, one STEP import, B-rep inspection, through-hole fact analysis, coupled candidate generation, complete external `New + Cut` reconstruction, Gate 3 validation, and sequence generation.

| Case | Selected candidate | Pre-Fusion geometry | Feature match | Axis offset (mm) | Opening-centre error (mm) | Awaiting Fusion |
| --- | --- | --- | --- | ---: | ---: | --- |
| D-H01 | `coupled-face-002-face-003-face-004` | pass | pass | 0.0 | 0.0 | yes |
| D-H02 | `coupled-face-004-face-005-face-006` | pass | pass | 0.0 | 0.0 | yes |
| D-H03 | `coupled-face-000-face-001-face-002` | pass | pass | 0.0 | 0.0 | yes |
| D-H04 | `coupled-face-002-face-003-face-004` | pass | pass | 0.0 | 0.0 | yes |
| D-H05 | `coupled-face-002-face-003-face-004` | pass | pass | 0.0 | 0.0 | yes |

No debug case has a formal terminal status. Formal status is written only after Fusion replay and independent replay STEP validation.

## Fusion adapter boundary

`Gate3SequenceReplay` is a thin adapter. It enforces the exact D-H01--D-H05 set with D-H04 first, refuses existing outputs, and dynamically loads the current Gate 2 adapter. The Gate 2 adapter in turn loads the validated Gate 1 replay core. Gate 3 does not introduce a second Sketch/New/Cut implementation.

The next valid step is to commit this pre-flight implementation from a clean branch, create one formal run with `git_dirty_at_start=false`, and then execute the Gate 3 batch once inside Fusion.
