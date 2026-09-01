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
