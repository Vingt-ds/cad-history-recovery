# Gate 5 Media Index

## Current stage boundary

The PPT is now tracked at `presentations/gate5/gate5_technical_briefing.pptx` by explicit user approval. See `docs/gate5_stage_delivery.md`. The original static MP4s and their historical package/checksums are archived locally under `delivery_package/supplementary_artifact_walkthroughs_20260906/`; they are **supplementary / non-authoritative** and must not populate the final `videos/` entries below. Real recordings are pending and will use the exact Commit A identified by the follow-up recording provenance record.

## Historical Checkpoint A and final asset names

The table specifies final required asset roles, not the completion of recordings. Earlier Checkpoint A static walkthroughs are preserved separately. None of these assets is formal experimental evidence.

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
