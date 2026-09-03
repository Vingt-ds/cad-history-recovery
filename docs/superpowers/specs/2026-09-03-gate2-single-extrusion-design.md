# Gate 2 Single-Extrusion Recovery Design

## Objective and boundary

Recover a deterministic, executable canonical history for frozen development cases D-S01 through D-S10. Gate 2 supports one simple line-only outer loop with 3--8 edges or one standalone full circle, followed by one New distance extrusion. It does not infer holes, Add, blind Cut, arcs, splines, multiple profiles, or arbitrary topology references.

`benchmarks/case_matrix.json` remains the only case-definition source. Gate 2 never reads held-out geometry while developing rules or thresholds. CadQuery validates candidates derived from B-rep facts; it never invents candidates. The output is a normalized executable history, not a claim about the designer's unique original history.

## Fact architecture

STEP is imported once by CadQuery. Solid validity and aggregate volume, area, centroid, and bounding box use the CadQuery wrapper. Face, wire-use, ordered edge-use, edge, vertex, curve, surface, orientation, and parameter facts are read through the same wrapped OCP shape. A canonical serializer produces stable JSON bytes.

`brep_summary.json` is a run-independent fact artifact. It contains `brep_summary_schema`, `model_id`, `source_step_sha256`, units, canonicalization metadata, and B-rep facts. It excludes run IDs, paths, timestamps, expected labels, and environment versions. Run metadata belongs in the run manifest, `input_metadata.json`, and run-level `environment.json`.

## Canonical topology

OCP topology identity is checked before geometric signatures, so geometrically coincident but topologically distinct entities are not merged. IDs are assigned bottom-up: Vertex, Edge, Wire, Face, Solid. Signatures combine quantized geometry with lower-level incidence. A remaining collision raises `topology_id_collision`; traversal order, memory addresses, and random suffixes are forbidden fallbacks.

Wire edge-use order preserves direction while removing only an arbitrary cyclic starting position. Face-to-wire and wire-to-edge orientation is stored on the use. Canonical JSON is UTF-8 without BOM, LF-only, sorted by key and canonical ID, two-space indented, finite-valued, and terminated by one newline.

Planes store origin, geometric normal, and x direction. Cylinders, cones, and spheres use type-specific parameters. Other valid surfaces remain factual `other` records instead of causing early inference rejection. Edges use base types `line`, `circle`, `bspline`, and `other`; full circles and circular arcs are distinguished by derived `circle_form`, closure, and parameter span. Curved faces do not receive a false global normal.

## Adjacency and candidates

Adjacency is a plain dictionary keyed by canonical face ID. At a shared-edge parameter, both locally oriented outward face normals and the F1 edge-use-oriented tangent are evaluated. With F1 chosen by canonical face ID, the provisional turn is `theta = atan2(t dot (n1 cross n2), n1 dot n2)`. The sign convention becomes usable only after D-S01 classifies all box edges as convex and D-S04 contains expected convex and concave edges. Failed tests require orientation correction, not label changes. Unreliable evaluations are `unknown`; seam edges never create self-adjacency.

Pre-validation hypotheses are unordered planar end-face pairs. Hard checks cover opposite normals, positive separation, centroid displacement along the extrusion axis, area agreement, translated boundary agreement, and complete side-face connectivity. Every measurement and rejection reason is retained. Pre-validation ordering uses facts and candidate ID only.

After CadQuery reconstruction, final ranking uses validation outcome, volume and bounding-box errors, diagnostic surface metrics, primitive count, extrusion distance, and candidate ID. `ambiguous=true` is assigned only when at least two candidates satisfy final acceptance; one deterministic candidate is still emitted.

## Profile, frame, and schema

The selected base face is canonical. Its outward normal remains provenance. For an inferred absolute frame, frame normal and extrusion direction are the unit vector from the base-face centroid to the opposite-face centroid, and distance is positive. For named origin planes, Fusion's fixed plane frame remains unchanged and the independent extrusion direction records the sign.

The absolute-frame x axis is the projection of global X into the plane, falling back to global Y; `y = normal cross x`. A line profile is projected to 2D, checked for closure, simplicity, non-degeneracy, and 3--8 edges, then normalized by signed area. A circle profile must be one complete circle.

`cadseq-0.2` only distinguishes frame provenance. Root `origin_plane` uses `frame_source=origin_named`; automatically inferred `absolute_frame` uses `frame_source=inferred_brep` with `replay_mode=automatic`; human replacement uses `frame_source=manual_correction`, `absolute_fallback`, and a full correction record. `operation_cap` remains a semantic reference without `frame_source`. The `cadseq-0.1` dispatch path and Gate 1 evidence remain unchanged.

## Validation and completion

Validity, one-solid output, volume, and all six bounding-box coordinates are hard checks. Surface distances remain diagnostic until calibration compares D-S01--D-S10 round trips with controlled non-benchmark perturbations. Before the formal run, the protocol and its SHA-256 are frozen. A surface threshold is used only if normalized round-trip and perturbation intervals do not overlap; otherwise surface distance is frozen as `diagnostic_only`.

Formal results live under a unique `benchmark_results/<run_id>/` with `manifest.json`, one `environment.json`, and conditional case artifacts. `git_dirty_at_start` is sampled immediately before execution. D-S01--D-S10 remain supported; inability to recover one is `failed`, never relabeled `unsupported`.

Gate 2 passes only when at least eight cases are automatic successes, every success passes the frozen geometry protocol, and all ten packages pass the separate completeness audit. The implementation branch is `gate2-single-extrusion`; the completion tag is `gate2-forward-path`.
