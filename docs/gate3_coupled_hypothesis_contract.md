# Gate 3 Coupled Base-and-Through-Hole Contract

## Frozen purpose of the first implementation checkpoint

Gate 3 targets a normalized construction explanation containing one supported Line-only base Sketch, one `new + distance` Extrusion, one circular Sketch on a semantic `operation_cap`, and one `cut + through_all` Extrusion.

The first checkpoint does not generate a CAD sequence or call Fusion. It establishes whether a final perforated B-rep contains the topology facts required for a later coupled base-plus-hole hypothesis. Development inputs are derived only from the frozen `case_matrix.json` entries `D-H01` through `D-H05`; inference code must not receive expected labels or geometry parameters from the matrix. Held-out inputs are rejected by the Gate 3 development entry point.

## Checkpoint 1 API

Add one module, `external/through_hole_inference.py`, with this public function:

```python
analyze_through_hole_facts(summary, adjacency) -> dict
```

The function accepts an existing canonical `brep-summary-0.1` dictionary and its matching `face-adjacency-0.1` dictionary. It performs no STEP import and no reconstruction. Its return value uses `through-hole-facts-0.1` and contains:

```text
model_id
source_step_sha256
planar_wire_roles[]
  face_id
  outer_wire_id
  inner_circle_wire_ids[]
  checks[] {name, measurement, passed, reason}
hole_fact_groups[]
  cylinder_face_id
  circle_edge_ids[2]
  inner_wire_ids[2]
  planar_face_ids[2]
  measured_axis
  measured_radius_mm
  diagnostic_adjacency[]
  checks[] {name, measurement, passed, reason}
  status: accepted | rejected
rejection_reasons[]
```

Lists and IDs use canonical ordering. JSON serialization, when written as evidence, uses the repository's canonical sorted-key encoding.

## Narrow wire-role rule

Checkpoint 1 supports only a planar end face with exactly:

- one simple Line-only closed wire containing 3--8 distinct edges, classified as the base outer wire; and
- one single-edge `full_circle` wire, classified as the hole inner wire.

The role is derived from wire primitives and face incidence, not OCP traversal order. A face with two circular wires, mixed curves, multiple circular inner wires, a circular-only outer face, or an otherwise unresolved role is rejected explicitly. Support for an annular circular base is not claimed because no frozen Gate 3 development case exercises it.

## Narrow cylinder-and-circle pairing rule

A Checkpoint 1 accepted fact group requires:

1. one cylindrical face with finite axis and positive radius;
2. exactly two distinct `full_circle` boundary edges used by that cylindrical face;
3. each circle edge is also used by a different planar face;
4. each circle edge belongs to the planar face's classified inner circular wire;
5. the two circle radii are equal within the explicitly recorded check tolerance;
6. both circle centres lie on the same undirected cylinder axis within the explicitly recorded check tolerance;
7. the centre-to-centre vector is parallel to that axis and has positive length.

The current `convex`/`concave` classification is copied only into `diagnostic_adjacency`; it is not an acceptance check. Cylinder axis sign is not interpreted as Cut direction.

## Deferred coupled-candidate API

Checkpoint 2 will add a separate function:

```python
generate_coupled_candidates(summary, adjacency, hole_facts) -> dict
```

Its candidate schema must preserve the selected base end faces and outer wires, the paired inner circles and cylinder, the normalized base direction, the semantic operation cap, the Cut direction into material, every measured hard check, and every rejection reason. It must compare outer end-face wires without allowing the circular inner wires to invalidate the base translation check.

The complete New-plus-Cut reconstruction is the unit of geometric validation. A base-only solid is expected to differ in volume and surface geometry from the perforated reference and must not be rejected for that expected difference.

## Test contract

Tests are written and observed failing before production implementation.

1. `D-H01` through `D-H05` each yield exactly one accepted hole fact group with two distinct circles, two different planar faces, two inner circular wires, one cylinder, and deterministic canonical ordering.
2. The planar wire roles identify a Line-only outer wire and a separate full-circle inner wire without using traversal position.
3. A development-only controlled cylindrical boss yields no accepted through-hole group because one circular boundary belongs to a circular outer cap rather than an inner wire on a second base end face.
4. A solid without a cylindrical face yields no accepted group with a structured rejection reason.
5. Changing adjacency `convex` labels to `concave`, or vice versa, does not change acceptance.
6. Mismatched summary/adjacency model IDs or source hashes are rejected before analysis.
7. Checkpoint 1 output contains no sequence, Cut, candidate ranking, Fusion, correction, or final-status fields.
8. Existing Gate 0--2 tests and the immutable Gate 2 formal verifier remain unchanged and passing.

## Scope exclusions

Blind, tapered, stepped, countersunk, counterbored, threaded, multiple, patterned, intersecting, or non-circular holes remain outside this checkpoint. No benchmark file, frozen protocol, held-out label, Gate 2 result package, or `gate2-forward-path` reference may be modified.
