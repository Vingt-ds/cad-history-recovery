# Gate 2 Single-Extrusion Recovery Implementation Plan

> **For agentic workers:** Execute inline with the `executing-plans` and `test-driven-development` skills. Do not use held-out data or add unapproved CAD capability.

**Goal:** Automatically recover and Fusion-replay a canonical single-extrusion history for at least 8 of the 10 frozen development single-extrusion cases while producing complete, auditable result packages for all 10.

**Architecture:** Import each STEP once through CadQuery and inspect its wrapped OCP topology. Build deterministic facts, minimal face adjacency, fact-derived hypotheses, supported 2D profiles, `cadseq-0.2` sequences, independent CadQuery validation, Fusion replay, and a separate completeness audit.

**Tech Stack:** Python 3.11, CadQuery 2.8.0, OCP 7.9.3.1, NumPy, SciPy, Fusion 2704.1.53, standard-library `unittest`.

---

## Task 1: Result-package contract and development selector

Create `external/result_package.py` and `tests/test_result_package.py`. Write failing tests for D-S01--D-S10 selection, held-out refusal, safe relative paths, immutable run IDs, manifest hashes, `git_dirty_at_start`, terminal-status vocabulary, and conditional artifacts. Implement only enough code to pass, run focused and full tests, then commit.

## Task 2: Canonical B-rep facts

Create `external/brep_inspection.py`, `external/inspect_brep.py`, and `tests/test_brep_inspection.py`. Start with D-S01 aggregate facts; then add topology identity/incidence, type-specific surfaces and curves, canonical ordering, collision rejection, and independent-process byte equality. Add D-S07, D-S04, D-S09, invalid, zero/multi-solid, and collision cases one failing test at a time. Generate Day 1 evidence for D-S01--D-S10 under `logs/gate2/`, run the complete suite, and commit.

## Task 3: Minimal attributed adjacency

Create `external/topology_adjacency.py` and `tests/test_topology_adjacency.py`. Add failing tests for D-S01 box convexity, D-S04 concavity, D-S07 local cylinder normals, seam exclusion, and unknown classification. Implement local shared-edge normal/tangent evaluation and record each signed measurement. Do not proceed until expected geometry passes without changing labels. Run all tests and commit.

## Task 4: Extrusion hypotheses

Create `external/extrusion_inference.py` and `tests/test_extrusion_inference.py`. Test fact-only end-face checks, deterministic pre-validation order, rejection reasons, translated line/circle boundary matching, side coverage, reverse-pair deduplication, and retained alternatives. Run D-S01, D-S04, D-S07, D-S09, and D-S10 and save candidate evidence. Run all tests and commit.

## Task 5: Profile reconstruction and `cadseq-0.2`

Create `external/profile_reconstruction.py`, extend `shared/sequence_validator.py` with version-dispatched v0.2 validation, add `docs/sequence_schema_v0.2.md`, and extend schema tests. Cover 3--8 line profiles, one full circle, winding, self-intersection, degeneracy, mixed/arc/spline/multiple-loop rejection, named/inferred/manual frame provenance, operation-cap exemption, and unchanged v0.1 behavior. Emit valid sequences for D-S03, D-S05, D-S06, D-S08, and D-S10 without corrections. Run all tests and commit.

## Task 6: CadQuery validation and calibration freeze

Create `external/candidate_validation.py`, `external/calibrate_gate2.py`, and focused tests. Implement one-solid validity, explicit volume/bbox tolerances, round-trip measurements, controlled temporary perturbations, and the separation rule for surface threshold versus `diagnostic_only`. Freeze `config/gate2_validation_protocol.json` with evidence and SHA before formal candidate evaluation. Add post-validation ranking and ambiguity assignment. Run all tests and commit.

## Task 7: Pipeline and result-package writing

Create `external/gate2_pipeline.py`, `external/verify_gate2.py`, and focused tests. The pipeline reads only selected development inputs, writes required and conditional artifacts, isolates case failures, preserves failure stages/codes, and never overwrites a run. Create a debug run without claiming formal completion. Run all tests and commit.

## Task 8: Fusion replay adapter

Add a Gate 2 thin adapter around one validated replay core. Preserve Gate 1 behavior while extracting reusable Sketch/New Extrude logic. If Fusion module loading blocks safe reuse for 45 minutes, retain Gate 1 unchanged and record the bounded minimal-copy fallback. Test v0.2 inferred planes, batch requests, document isolation, output non-overwrite, frame round trips, and case failure logs. Run full regression and commit. Ask the user for one Fusion batch launch only after a non-rectangular request is ready.

## Task 9: Formal run and closure

Commit code, confirm clean state, and create one formal run with `git_dirty_at_start=false`. Run D-S01--D-S10 through inference, Fusion, validation, terminal status, and completeness audit. Run all unit tests and Gate 0/1/2 verifiers. Require at least 8 automatic successes and 10 complete packages. If passed, commit evidence, tag `gate2-forward-path`, merge to `main`, and push. If failed, preserve results and minimal reproductions without relabeling, tagging, merging, or entering Gate 3.
