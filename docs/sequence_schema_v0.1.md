# CAD Sequence Schema v0.1

## Scope

Schema version `cadseq-0.1` represents a deterministic candidate construction history. It does not claim to recover the designer's unique original timeline.

| Boolean | Extent | v0.1 status |
| --- | --- | --- |
| `new` | `distance` | supported |
| `cut` | `through_all` | supported |
| `add` | `distance` | excluded until the optional P1 replay test passes |
| `new` | `through_all` | invalid |
| `add` | `through_all` | unsupported |
| `cut` | `distance` | unsupported |

The validator accepts only `new + distance` and `cut + through_all`. A blind hole may exist as an input benchmark, but it is not a valid v0.1 replay sequence.

## Document structure

Every document contains `schema_version`, `model_id`, `units`, positive length/angular tolerances, replay status/mode, correction records, and an ordered operation list. Operation IDs are unique, and dependencies must refer to earlier operations.

## Sketch operation

A Sketch contains an explicit world frame and a semantic reference. The right-handed frame uses `y_axis = normal x x_axis`. The validator never silently normalizes vectors: `normal` and `x_axis` must already be unit vectors and orthogonal.

The only plane references are:

```json
{"type": "origin_plane", "role": "XY"}
```

```json
{"type": "operation_cap", "operation_id": "extrude_base", "role": "positive_end_cap", "offset_mm": 0.0}
```

```json
{"type": "absolute_frame", "correction_id": "correction_001"}
```

`operation_cap` may reference only an earlier `new + distance` Extrude. In v0.1 its `offset_mm` must be zero, its frame normal must follow the parent Extrude direction, and its frame origin must lie on the selected positive or negative cap plane. Runtime replay must additionally prove that the Extrude succeeded and that the cap resolves. `absolute_frame` requires `replay_mode: "absolute_fallback"` and a matching human-correction record containing `correction_id`, positive `correction_number`, target `operation_id`, non-empty `reason`, and explicit `before`/`after` objects.

Each loop has a unique ID, an `outer` or `inner` role, and non-empty primitives. A line loop is a closed chain of lines. A circular loop contains exactly one complete circle with positive radius. General arcs, splines, and mixed line/curve loops are outside v0.1.

## Extrude operation

An Extrude profile references a previous Sketch, one real outer loop, and distinct inner loops from that Sketch. Its unit direction must be parallel or antiparallel to the Sketch normal. The Extrude dependencies must include the profile Sketch.

`distance_mm` is always positive. Direction is expressed by the direction vector; Fusion's signed UI distance is not copied into the schema.

Static validation checks that a Cut follows an earlier body-generating New Extrude. It does not claim that the Cut profile geometrically intersects the body. Fusion runtime validation must reject a Cut whose volume does not decrease with `boolean_no_intersection`.

## Validation response

The shared pure-standard-library function returns `{"valid": true, "errors": []}` or one structured error containing `code`, `path`, and `message`. Both external Python and Fusion must import this same module; Fusion runtime errors remain a separate layer.
