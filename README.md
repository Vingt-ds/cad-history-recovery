# Rule-based CAD Construction Sequence Synthesis from B-rep Models

This repository contains a deterministic, semi-automatic pipeline under development for converting history-free B-rep/STEP models into plausible, replayable CAD construction sequences.

> **Current status:** Gate 0 through Gate 3 are closed. The frozen 30-case B-rep input set remains unchanged. Gate 2 automatically inferred, Fusion-replayed, and geometrically validated 10/10 frozen development single-extrusion cases. Gate 3 did the same for 5/5 frozen development cases containing one supported through cylindrical Cut. These results do not claim held-out performance or arbitrary B-rep history recovery.

## Gate 3 completed scope

- coupled recovery of one Line-only base extrusion and one straight through cylindrical Cut;
- outer-wire base matching that is not invalidated by circular inner wires;
- paired circular openings and their connecting cylindrical face as explicit Cut evidence;
- deterministic `cadseq-0.2` synthesis of `Sketch -> New Extrusion -> Sketch on operation_cap -> Cut through_all`;
- CadQuery validation of the complete hypothesis before Fusion replay;
- hard analytic checks for hole radius, undirected axis, axis-line offset, opening centres and span;
- a thin `Gate3SequenceReplay` adapter reusing the validated Gate 2 and Gate 1 replay layers;
- immutable manifests, inference evidence, native F3D, replay STEP, validation metrics and terminal statuses.

The formal run `gate3-formal-20260904-8e8ae63` produced 5/5 automatic successes, 5/5 geometry passes, 5/5 analytic hole-feature matches and 5/5 complete result packages, with no ambiguity or manual correction. The verified report is available at [`benchmark_results/gate3-formal-20260904-8e8ae63/gate3_verification_report.json`](benchmark_results/gate3-formal-20260904-8e8ae63/gate3_verification_report.json), with the closure summary at [`logs/gate3/gate3_closure_report.md`](logs/gate3/gate3_closure_report.md).

## Gate 2 completed scope

- one STEP import feeding a deterministic CadQuery/OCP B-rep fact layer;
- canonical Solid/Face/Wire/Edge/Vertex facts and minimal attributed face adjacency;
- explainable extrusion hypotheses with retained acceptance and rejection evidence;
- one simple 3--8-edge Line-only outer profile or one standalone complete Circle;
- `cadseq-0.2` root-frame provenance for named origin planes and inferred B-rep frames;
- CadQuery candidate reconstruction, deterministic final ranking, and calibrated geometry validation;
- a Gate 2 Fusion batch adapter reusing the Gate 1 Sketch/New Extrude replay core;
- immutable run-level manifests, environment snapshots, case logs, native F3D files, replay STEP files, validation metrics, and terminal statuses.

The formal run `gate2-formal-20260903-e93dc2f` produced 10/10 automatic successes, 10/10 geometry passes, and 10/10 complete result packages. `D-S01` and `D-S09` retain `ambiguous=true` because multiple histories satisfy the frozen acceptance protocol. Two earlier infrastructure-failure runs are preserved and are not counted as algorithm outcomes.

The verified Gate 2 report is available at [`benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json`](benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json), with the closure summary at [`logs/gate2/gate2_closure_report.md`](logs/gate2/gate2_closure_report.md). The audited completion tag is `gate2-forward-path`.

## Gate 1 completed scope

- 30 fixed raw STEP inputs: 15 development and 15 held-out;
- 27 deterministic CadQuery sources and three Fusion-manual sources;
- schema v0.1 known-sequence examples for a box and a box with one through-hole;
- one shared pure-standard-library validator used by external Python and Fusion replay;
- explicit rejection fixtures for unsupported Cut distance, broken loop references, invalid operation-cap references, and invalid frames.
- Fusion replay of Line/Circle sketches, outer loops, `New + distance`, semantic `operation_cap`, and `Cut + through_all`;
- XY/XZ/YZ origin planes plus fixed RX30/RY45 frame cases with world-coordinate checks;
- explicit `semantic_reference_failed` handling and audited absolute-frame fallback;
- deterministic geometry inspection and bidirectional sampled surface-distance calibration;
- three stable box replays and three stable box-with-through-hole replays, with native F3D, STEP, JSON logs, and screenshots.

The benchmark is frozen by `benchmarks/manifest.json` and `benchmarks/freeze.lock.json`. After the freeze, the 15-case held-out split is excluded from rule and threshold development. It is a frozen held-out set, not a blind or previously unseen set.

The verified Gate 1 report is available at [`logs/gate1_report.md`](logs/gate1_report.md).

## Gate 0 scope

Gate 0 establishes the execution boundary required by later inference work:

- a shared millimetre-based JSON configuration;
- manual Fusion modelling, STEP export, and STEP re-import evidence;
- a Fusion Python script that creates a fresh `60 x 40 x 20 mm` box and exports STEP;
- two independent Fusion script runs, each producing one body with six faces;
- CadQuery/OCP generation and re-import of a box STEP;
- CadQuery/OCP inspection of the two Fusion STEP files and the manual box-with-through-hole STEP;
- matching SHA-256 records proving that Fusion and external Python read the same JSON;
- automated tests and a consolidated PASS/FAIL report.

The verified Gate 0 report is available at [`logs/gate0_report.md`](logs/gate0_report.md).

## Verified environment

| Component | Verified version |
| --- | --- |
| Autodesk Fusion | 2704.1.53 |
| Conda Python | 3.11.16 |
| CadQuery | 2.8.0 |
| OCP | 7.9.3.1 |

The environment definition is in [`environment/environment.yml`](environment/environment.yml). The accompanying `pip-freeze.txt` is an audit record from the verified Conda environment, not the preferred installation method.

## Repository layout

```text
benchmark_results/ Immutable Gate 2 and Gate 3 formal runs and per-case result packages
benchmarks/        Frozen 30-case STEP input set, manifest, hashes, lock, and thumbnails
config/            Gate inputs and frozen Gate 2/Gate 3 validation protocols
docs/              Reuse audit, sequence schemas, and Gate design/implementation plans
environment/     Conda definition and verified package record
evidence/        Gate 0 evidence and Gate 1 Fusion replay screenshots
external/        B-rep inspection, inference, validation, pipeline, and Gate verification tools
fusion_scripts/  Gate 0 export plus Gate 1, Gate 2 and Gate 3 replay scripts
logs/            Structured run logs and Gate closure/verification reports
models/          Native Fusion and STEP evidence models
replay_outputs/  Native F3D, STEP, and JSON replay evidence
sequences/       Known-valid and intentionally invalid cadseq fixtures
shared/          Pure-standard-library frame and sequence validation modules
tests/           Automated Gate 0 through Gate 3 regression tests
```

## Reproduce the external checks

Create and activate the environment:

```powershell
conda env create -f environment/environment.yml
conda activate cadseq
```

Run the CadQuery/OCP smoke test from the repository root:

```powershell
python external/cadquery_smoke.py
```

Run the regression tests and consolidated verifier:

```powershell
python -m unittest discover -s tests -v
python external/verify_gate0.py --project-root .
python external/verify_gate1.py
python external/verify_gate2.py benchmark_results/gate2-formal-20260903-e93dc2f
python external/verify_gate3.py benchmark_results/gate3-formal-20260904-8e8ae63
```

The smoke test expects the committed Gate 0 STEP evidence under `models/`. It generates or refreshes `models/cadquery_box.step` and `logs/external_python.json`.

## Fusion scripts

In Fusion, open **Utilities -> Scripts and Add-ins**. Use `fusion_scripts/Gate0BoxExport` for the Gate 0 smoke export, `fusion_scripts/Gate1SequenceReplay` for Gate 1 known-sequence replay, `fusion_scripts/Gate2SequenceReplay` for a pipeline-prepared Gate 2 batch request, and `fusion_scripts/Gate3SequenceReplay` for a pipeline-prepared Gate 3 through-hole batch request.

The Gate 0 smoke script:

1. reads `config/gate0_box.json`;
2. validates the schema and millimetre units;
3. creates a new Fusion design document;
4. sketches and extrudes a rectangular box;
5. verifies one body and six faces;
6. exports STEP and writes a structured run log.

The committed `run01` and `run02` outputs are frozen evidence. The script intentionally refuses to overwrite them. Use a disposable checkout or preserve/move those four run artifacts before performing a fresh two-run experiment.

The Gate 2 adapter creates a fresh Fusion document for each case, reuses the validated Gate 1 Sketch/New Extrude core, creates inferred construction planes parametrically, and refuses to overwrite existing case outputs. The completed formal request is preserved as `benchmark_results/gate2-formal-20260903-e93dc2f/replay_request_used.json`; no active replay request remains in `config/` after closure.

The Gate 3 adapter adds a semantic operation-cap circular sketch and `Cut + through_all` while reusing the earlier replay layers. Its completed formal request is preserved as `benchmark_results/gate3-formal-20260904-8e8ae63/replay_request_used.json`; no active Gate 3 replay request remains in `config/` after closure.

## Gate 0 evidence

- `manual_box_hole.f3d`: native Fusion model with Sketch/Extrude/Sketch/Cut history;
- `manual_box_hole.step`: exported history-free B-rep;
- `manual_box_hole_reimported.f3d`: STEP imported into a fresh Fusion document;
- `01_original_timeline.png` and `02_reimported_timeline.png`: evidence that geometry is retained while the original feature timeline is lost;
- `fusion_run01.json`, `fusion_run02.json`, and `external_python.json`: structured execution records.

## Current limitations

Gate 0 did **not** implement:

- automatic feature or construction-history inference;
- the final editable sequence schema;
- ambiguity handling or manual sequence correction;
- production geometric-distance or volume-IoU validation;
- benchmark development/test splits;
- advanced operations such as fillet, chamfer, revolve, sweep, loft, shell, or patterns.

Those capabilities were deferred to later gates. Learning-based inference remains outside the project scope.

Gate 1 does **not** claim:

- automatic B-rep feature or construction-history inference;
- `Add/Join`, `Cut + distance`, blind holes, multiple holes, or fillet/chamfer recovery;
- arbitrary Face/Edge/Vertex references or general topological naming;
- a universal geometric acceptance threshold or production volume-IoU acceptance rule;
- byte-for-byte deterministic Fusion STEP exports; the verified claim is geometric stability.

Gate 2 does **not** claim:

- recovery of the designer's unique original construction history;
- generalization beyond the frozen ten-case development single-extrusion subset;
- held-out benchmark performance, which remains reserved for the later frozen evaluation;
- mixed curves, arcs, splines, inner or multiple profile loops, or profiles outside the verified 3--8 Line range;
- multi-feature recovery such as automatic holes, fillets, chamfers, revolves, sweeps, lofts, shells, or patterns;
- universal validity of the calibrated surface thresholds outside the frozen Gate 2 protocol and environment.

Gate 3 does **not** claim:

- held-out performance or generalization beyond the five frozen development through-hole cases;
- blind, tapered, stepped, counterbored, countersunk, threaded, multiple, patterned, intersecting or non-circular hole recovery;
- recovery of a through hole without two explicit circular openings and one connecting cylindrical face;
- convexity as a hard hole criterion, or a calibrated universal surface-distance threshold;
- recovery of the designer's unique original construction history.

## References and reuse boundary

Gate 0 uses Autodesk Fusion's installed Python API and CadQuery/OCP as infrastructure. Fusion 360 Gallery and Analysis Situs were reviewed as architectural references only; their search systems and source code are not dependencies of this repository. See [`docs/gate0_reuse_audit.md`](docs/gate0_reuse_audit.md).

No project licence is granted at this stage. The repository remains private while the research prototype is under evaluation.
