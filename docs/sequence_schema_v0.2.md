# CAD Sequence Schema v0.2

`cadseq-0.2` adds auditable root-frame provenance to the operations already supported by `cadseq-0.1`. It does not add a CAD operation or broaden the feature scope. Existing `cadseq-0.1` documents continue to use their original validation rules.

## Document replay modes

- `automatic`: a v0.2 sequence whose root frame comes from a named Fusion origin plane or deterministic B-rep inference.
- `absolute_fallback`: an absolute frame introduced by an audited manual correction.

## Root Sketch frame sources

`sketch_plane.frame_source` is required for explicit root `origin_plane` and `absolute_frame` references. Its allowed values and combinations are fixed:

| `frame_source` | Semantic reference | Replay mode | Required evidence |
| --- | --- | --- | --- |
| `origin_named` | `origin_plane` with role `XY`, `XZ`, or `YZ` | `automatic` | The explicit right-handed frame remains on the named plane. |
| `inferred_brep` | `absolute_frame` | `automatic` | `frame_provenance` with lowercase source STEP SHA-256, canonical base face ID, and source-face outward normal. |
| `manual_correction` | `absolute_frame` with `correction_id` | `absolute_fallback` | A matching complete correction audit in `corrections`. |

For `inferred_brep`, the frame normal is the unit vector from the base-face centroid to the opposite-face centroid. The Extrude direction must equal this normal and the distance must be positive. The recorded `source_face_outward_normal` must oppose the frame normal. The x-axis is the normalized projection of global X onto the plane, falling back to projected global Y only when required; `y = normal cross x`.

This inferred frame is a deterministic normalized history. It is not a claim about the designer's original Sketch coordinate system.

## Semantic operation caps

`operation_cap` remains a semantic reference and must not contain `frame_source`. A normally resolved operation-cap Sketch may use document `replay_mode=automatic`. Only after semantic resolution fails may a human replace it with `absolute_frame`, `frame_source=manual_correction`, `replay_mode=absolute_fallback`, and a complete correction audit.

## Unchanged operation scope

The v0.2 validator retains the v0.1 Sketch and Extrude structures. It does not introduce Add, blind Cut, Arc, multiple profiles, arbitrary Face references, Move, or Direct Modeling. Supported loops remain Line-only closed loops or one complete Circle; Gate 2 inference applies the narrower frozen profile rules documented by its implementation and result logs.
