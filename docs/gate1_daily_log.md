# Gate 1 Daily Log

## 2026-09-01

**Daily target:** establish the Gate 1 branch, define the non-random 30-case matrix, and start CadQuery benchmark generation.

### Completed evidence

- Gate 0 commit verified at `b52289b2e61eb3a723f5b1fe4a99e4a433a97a36`.
- Annotated local tag created: `gate0-environment-loop`.
- Development branch created: `gate1-known-sequence`.
- `benchmarks/case_matrix.json` fixes 30 case IDs, split, source, expected scope, expected behavior, geometry parameters, and output paths.
- Partition audit: 15 development, 15 held-out; 27 CadQuery, 3 Fusion-manual.
- Initial generator supports deterministic single-profile extrusion from the fixed frame catalog.
- Generated and re-imported:
  - `D-S01.step`: one valid Solid, six Faces; SHA-256 `B58B5C4886DB8CEB58F72F5224F6BF7783109FF6A7A2384257E8DD7842455048`.
  - `D-S09.step`: one valid Solid, six Faces; SHA-256 `92991300E3BD1395D9E45F4D57E5994D8E137646053B258040E7633BEBE17507`.

### Preserved issue

The first selected-generation command printed absolute Chinese paths through `conda run`. Geometry generation completed, but Conda then raised `UnicodeEncodeError` while encoding captured output with GBK. A minimal reproduction showed ASCII-only output succeeds from the same directory. Subsequent verification therefore prints only ASCII case IDs and counts; no environment, path, or package change was made.

### Next session entry point

Extend the tested generator to through-hole, cube, and filleted-box source geometry, then generate and audit the remaining 25 CadQuery STEP files. Do not start sequence schema or Fusion replay work before the raw benchmark generation task is closed.

## 2026-09-01 — September 2 benchmark task completed ahead of schedule

**Daily target:** finish all 30 raw B-rep inputs, including the two remaining Fusion-manual held-out cases, without starting sequence inference.

### Completed evidence

- The generator now supports straight-profile extrusions, one circular through-hole, cubes, filleted-box source geometry, deterministic SVG thumbnails, a contact sheet, lock refusal, and theoretical-versus-imported volume auditing.
- All 27 CadQuery cases were generated and re-imported as one valid Solid each.
- `D-H05` reuses the Gate 0 Fusion-manual STEP and remains one valid Solid.
- `T-H04` was built manually on the YZ plane as a `50 x 30 mm` profile, extruded `+X` by `18 mm`, with a diameter-`8 mm` through-hole at local `(32, 12)`. STEP audit: one valid Solid, seven Faces, volume `26095.221315766135 mm^3`.
- The first `T-C03` attempt was rejected because its STEP geometry showed an XZ profile and a Y-axis blind hole. It was rebuilt by explicitly selecting Fusion's named XY origin plane; the rejected orientation was not admitted to the benchmark.
- Corrected `T-C03` STEP audit: one valid Solid, eight Faces, bbox `(0, 50) x (0, 35) x (0, 20) mm`, cylinder axis `(0, 0, -1)`, diameter `10 mm`, depth `8 mm`, and volume `34371.68146928204 mm^3`.
- The generator now recognizes existing `manual_pending` STEP outputs only after importing them as one valid Solid. This behavior was added with a failing test first, followed by the minimal implementation.
- Final generation report: 30 cases, 27 `existing_valid`, three `existing_manual`, zero pending.
- Artifact audit: 30 STEP files, 30 SVG thumbnails, 30 contact-sheet cards, and no pending-manual placeholder.
- The largest relative volume error among the 26 analytically auditable generated cases remains approximately `5.60e-13`.

### Scope boundary

The held-out split is assembled but is not yet frozen; the formal hashes, manifest, and lock remain scheduled for September 6. No schema, Fusion replay executor, geometric inference, or threshold tuning was started during this task.

### Next session entry point

Begin the September 3 task: complete the third-party source matrix, freeze schema v0.1, implement the shared standard-library validator, and add valid/invalid JSON fixtures. Do not begin automatic B-rep inference.

## 2026-09-02 — September 3 schema task completed ahead of schedule

**Daily target:** freeze the narrow known-sequence contract and implement one validator shared by external Python and the future Fusion executor.

### Completed evidence

- Added a third-party source matrix that separates architectural reference, direct API use, licence uncertainty, and prohibited neural/search components. No third-party source code was copied.
- Defined `cadseq-0.1` with millimetres, explicit tolerances, ordered operation IDs/dependencies, Line/Circle loops, semantic/world frames, replay state, and correction audit fields.
- Frozen compatibility matrix: only `new + distance` and `cut + through_all` are accepted. `add` remains excluded until the optional P1 Fusion test passes; `cut + distance` remains unsupported.
- Added known fixtures for a `60 x 40 x 20 mm` box and the normalized `base New Extrusion -> circle Sketch on positive operation cap -> through-all Cut` history.
- Added named invalid fixtures for Cut distance, missing loop reference, invalid operation-cap reference, and non-unit frame.
- Implemented `shared/sequence_validator.py` using only the Python standard library. It returns structured `code`, `path`, and `message` errors and never normalizes vectors silently.
- Static validation covers unique IDs, earlier-only dependencies, profile/loop references, outer/inner role consistency, closed line loops, positive circle radii/distances, unit and orthogonal frames, named-plane origins, operation-cap frame/plane consistency, Extrude direction alignment, compatibility rules, prior-body Cut checks, and explicit absolute-frame correction records.
- TDD evidence: missing artifacts failed first; valid fixtures failed against the validator stub; invalid/cross-reference cases then failed against the permissive validator before the minimal rules were implemented.
- Full regression result: 55 tests passed. Six sequence JSON files parsed successfully, the validator imports only `math`, and Gate 0 remains 22/22 PASS.

### Scope boundary

This checkpoint performs static schema validation only. It does not resolve Fusion faces, prove Cut intersection, replay operations, tune thresholds, inspect held-out labels for rule development, or infer any history from B-rep.

### Next session entry point

Begin the September 4 task: implement the Fusion executor for Line/Circle Sketches, outer-loop profiles, and `new + distance`, then test XY/XZ/YZ plus the fixed 30-degree and 45-degree frames. Do not implement Cut or automatic inference in that session.

## 2026-09-02 — September 4 Fusion New-Extrude task completed ahead of schedule

**Daily target:** replay known Line/Circle outer-loop sketches and `new + distance` extrusions in Fusion on the three origin planes and two fixed rotated frames.

### Completed evidence

- Added a single-request Fusion executor that imports the shared standard-library validator, creates a fresh design document, refuses to overwrite evidence, replays one outer loop, and exports native F3D, STEP, and a structured JSON log.
- JSON sketch coordinates are transformed through the declared right-handed world frame, converted with Fusion's unit manager, written with `modelToSketchSpace`, and checked with `sketchToModelSpace` after forcing the sketch-space point onto the actual plane.
- The executor checks the actual Fusion sketch-plane normal against the declared frame and chooses the Extrude sign from the actual plane normal rather than assuming that all origin planes share one orientation.
- TDD evidence: the executor API contract failed against the initial script stub; frame conversion functions failed before implementation; explicit plane-alignment and point-on-plane checks were then added through a second red-green cycle.
- Six Fusion replays completed in fresh documents and produced non-empty F3D, STEP, and success logs:
  - `box_xy_run01`: volume `48000 mm^3`, bbox `(0, 60) x (0, 40) x (0, 20) mm`.
  - `box_xz_run01`: volume `27000 mm^3`, bbox `(0, 50) x (0, 18) x (-30, 0) mm`.
  - `box_yz_run01`: volume `21504 mm^3`, bbox `(0, 16) x (0, 48) x (0, 28) mm`.
  - `box_rx30_run01`: volume approximately `23712 mm^3`, bbox `(0, 48) x (-9.5, 22.5166604984) x (0, 29.4544826719) mm`.
  - `box_ry45_run01`: volume approximately `22176 mm^3`, bbox approximately `(0, 43.8406204336) x (0, 28) x (-31.1126983722, 12.7279220614) mm`.
  - `cylinder_xy_run01`: volume `11309.733552923255 mm^3`, bbox `(-12, 12) x (-12, 12) x (0, 25) mm`.
- Independent CadQuery re-import found one valid Solid in every STEP. Box cases have six Faces and 12 Edges; the cylinder has three Faces and three Edges.
- Fusion reported `world_frame_max_error_mm` between `0.0` and `4.440892098500626e-15` across all six cases.
- Full Python regression reached 67 tests passing; Gate 0 remained 22/22 PASS and all 21 JSON files parsed.

### Preserved issue

Two simultaneous `conda run` processes competed for Conda's temporary activation file and one command failed before starting Python. The same full test command passed when run serially. Gate commands will therefore remain serial; no project code or environment package was changed for this external tool race.

### Scope boundary

This checkpoint supports only one outer loop followed by `new + distance`. `operation_cap`, Cut, Add, automatic inference, and held-out threshold development remain unimplemented. Rotated frames are deliberately limited to the fixed RX30 and RY45 fixtures.

### Next session entry point

Implement `operation_cap` resolution and `cut + through_all`, verify that Cut reduces body volume, and preserve explicit `semantic_reference_failed` and `boolean_no_intersection` failures. Do not add blind-hole Cut, multiple holes, Add, or automatic B-rep inference.

## 2026-09-02 — September 5 semantic-cap and through-all Cut task completed ahead of schedule

**Daily target:** resolve a parent New Extrude cap without persistent face IDs, replay one circular through-all Cut, and preserve explicit failure and fallback semantics.

### Completed evidence

- `operation_cap` now resolves only a previously successful New Extrude stored in the current replay. `positive_end_cap` uses that feature's end cap and `negative_end_cap` its start cap; missing or non-unique caps return `semantic_reference_failed`.
- `cut + through_all` uses Fusion's through-all extent and the declared world direction relative to the actual sketch normal. The executor requires one body before and after Cut and returns `boolean_no_intersection` if body volume does not decrease.
- The first `box_hole_run01` was preserved as a real failure: sketching a circle on a body face produced two Fusion profiles, invalidating the executor's earlier assumption that every Sketch must have exactly one profile.
- A red test reproduced the selection problem with two profile regions. The fix selects the unique single-outer-loop profile whose boundary curve count matches the declared JSON loop; it does not silently select Fusion profile index zero.
- `box_hole_run02` completed with the normalized four-operation history. Fusion volume decreased from `48.0 cm^3` to `46.42920367320504 cm^3`.
- Independent STEP re-import for `box_hole_run02` found one valid Solid, seven Faces, 15 Edges including the periodic cylinder seam, volume `46429.203673205106 mm^3`, and bbox `(0, 60) x (0, 40) x (0, 20) mm`.
- The success log records `profile_count=2` for the cap Sketch and `replay_mode=semantic`, so the repaired behavior remains auditable.
- `box_rx30_run02` repeated the fixed rotated case after logging was extended. Its log records `replay_mode=absolute_fallback`, its sequence SHA-256 matches the correction-bearing JSON, and its STEP volume and six-coordinate bbox match run01.
- Automated coverage includes a missing-parent unit case that returns `semantic_reference_failed`. A natural Fusion runtime cap-resolution failure was not manufactured because all supported single-profile New Extrusions resolve one cap face.

### Scope boundary

Only one isolated circular through-hole is implemented. The executor still rejects inner-loop base extrusion, blind Cut, multiple holes, Add, arbitrary face references, and automatic inference. The `boolean_no_intersection` volume guard is implemented but has not yet been exercised by a deliberately non-intersecting Fusion fixture.

### Next session entry point

Implement the Gate 1 geometry-validation baseline and benchmark freeze. Do not tune final acceptance thresholds from held-out results, and do not start B-rep history inference.

## 2026-09-02 — September 6 validation and freeze task completed ahead of schedule

**Daily target:** establish deterministic Gate 1 geometry diagnostics, calibrate STEP round-trip sampling behavior, and freeze the 30-case benchmark before any inference-rule development.

### Completed evidence

- Pre-freeze import audit confirmed all 30 STEP files are one valid Solid. The two completed Fusion-manual cases are now marked `manual_completed`, not the stale `manual_pending` state.
- Added deterministic STEP inspection for Solid count, validity, volume, surface area, and all six bounding-box coordinates.
- Surface sampling guarantees at least 32 points per Face and at least 4096 points per model. Remaining samples are distributed by Face area; directional global means are explicitly weighted by source-Face area.
- The random seed is the first eight bytes of each file's SHA-256. Python's process-randomized `hash()` is not used.
- Surface diagnostics report A-to-B and B-to-A mean and p95 distances, `symmetric_p95_mm`, and the worst p95 over every source Face in both directions. No Face correspondence algorithm was introduced.
- Self-comparison of `D-S01.step` produced zero distance because it reuses identical deterministic samples.
- CadQuery STEP round-trip calibration remained geometrically identical in volume, area, and six-coordinate bbox. Independent deterministic samples produced `symmetric_p95_mm = 1.4007279107850243` and `max_face_p95_mm = 1.4559122410622107`.
- Repeating both self and round-trip comparisons reproduced the saved metrics exactly in the current environment.
- These values are calibration evidence for the current sampling budget, not general geometric acceptance thresholds.
- The benchmark was frozen as `gate1-frozen-0.1`: 15 development and 15 held-out cases, with path, source, expected labels, size, and SHA-256 for every STEP.
- Freeze manifest SHA-256: `c92ac078a5feccce3f7fd53fe4c67a5fbd30c276bb27418948ad46c1a62c8e30`.
- `benchmarks/freeze.lock.json` now blocks benchmark regeneration and overwrite through the generator.
- Full regression: 81 tests passed; the frozen-manifest verifier passed; all 34 repository JSON files parsed; Gate 0 remained 22/22 PASS.

### Preserved warning

Importing CadQuery currently emits upstream `ezdxf`/`pyparsing` deprecation warnings. They did not change test outcomes or geometry, and no dependency version was changed during this Gate. The warning remains visible rather than being globally suppressed.

### Scope boundary

The held-out set is now excluded from rule and threshold development. This checkpoint did not run automatic history inference, tune a final acceptance threshold, add Face matching, or implement Add, blind-hole recovery, multiple holes, or Fillet recovery.

### Next session entry point

Begin the September 7 Gate 1 closure audit: verify the required three consecutive box and box-hole replays from preserved Fusion evidence, assemble the unified Gate report, and only then decide whether the optional 45-minute Add test is justified. Do not start Gate 2 before Gate 1 is formally tagged.
