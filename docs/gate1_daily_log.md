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
