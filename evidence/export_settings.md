# Gate 0 Manual Fusion Export Record

Status: **FUSION MANUAL LOOP PASS**

- Fusion version: `2704.1.53`
- Login status: signed in (user confirmed)
- Workspace: Design available (user confirmed)
- Model units: `mm`
- Base sketch: XY plane, rectangle from `(0, 0)` to `(60, 40)`
- Base extrusion: New, `20 mm`
- Hole sketch: top end face, centre `(30, 20)`, diameter `10 mm`
- Hole operation: Cut, Through All
- Native archive: `models/manual_box_hole.f3d`
- STEP export: `models/manual_box_hole.step`
- Reimported archive: `models/manual_box_hole_reimported.f3d`
- STEP export format/options: Fusion local export, STEP (`.step`), no additional options shown
- Original timeline visual review: PASS
  - Evidence: `evidence/01_original_timeline.png`
  - Verified visible sequence: Sketch -> Extrude (New Body) -> Sketch -> Extrude (Cut, All)
  - Verified visible geometry: one rectangular solid with one centered circular opening
- Reimported timeline visual review: PASS
  - Evidence: `evidence/02_reimported_timeline.png`
  - Verified geometry retained: one rectangular solid with centered circular opening
  - Verified construction history lost: no original Sketch/Extrude feature sequence in the timeline
