# Gate 5 Media Index

## Current delivery boundary

The PPT is tracked at `presentations/gate5/gate5_technical_briefing.pptx`. See `docs/gate5_stage_delivery.md`. The source project description requires a live demo but does not require submitted recordings. The original static MP4s and their historical checksums are archived locally under `delivery_package/supplementary_artifact_walkthroughs_20260906/`; they are **supplementary / non-authoritative** and must not be described as Fusion operation recordings. If recorded backups are later requested, use the exact source commit identified by the recording provenance record.

## Optional recorded-backup asset names

The table specifies fixed names and roles only if a recorded backup package is requested. Earlier static walkthroughs are preserved separately. None of these assets is formal experimental evidence.

| Asset | Case | Role | Git policy |
| --- | --- | --- | --- |
| `videos/demo_01_single_extrusion_v1.mp4` | D-S04 | complete development-case technical path | local package only |
| `videos/demo_02_through_hole_v1.mp4` | D-H01 | frozen base-plus-through-hole path | local package only |
| `videos/demo_03_ambiguity_v1.mp4` | D-S01 | read-only sealed ambiguity evidence | local package only |
| `screenshots/demo_01_single_extrusion_v1.png` | D-S04 | verified final replay/validation view | local package only |
| `screenshots/demo_02_through_hole_v1.png` | D-H01 | verified final replay/validation view | local package only |
| `screenshots/demo_03_ambiguity_v1.png` | D-S01 | sealed candidate and ambiguity view | local package only |
| `slides/gate5_delivery_v1.pptx` | n/a | eventual final package copy of the stage presentation | stage PPT tracked separately; final package pending |

The authoritative size and SHA-256 of each present asset are recorded in the local `submission_manifest.json` and `SHA256SUMS.txt`. The Git document fixes names and roles but does not assert that a local file exists.

Videos must show the evidence chain only. They must not contain code edits, threshold changes, parameter tuning, reruns of the held-out split, or manual JSON repair.

Historical Checkpoint A videos are silent, artifact-derived technical walkthroughs rendered from JSON and replay STEP outputs. They are supplementary explanation assets, not real operation recordings or substitutes for the final backup-video requirement.
