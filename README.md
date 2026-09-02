# Rule-based CAD Construction Sequence Synthesis from B-rep Models

This repository contains a deterministic, semi-automatic pipeline under development for converting history-free B-rep/STEP models into plausible, replayable CAD construction sequences.

> **Current status:** Gate 0 and Gate 1 are closed. Schema v0.1 known sequences can be validated and replayed in Fusion for `New + distance` and `Cut + through_all`. The 30-case raw B-rep benchmark is frozen. Automatic B-rep-to-history inference has not started and is not claimed here.

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
benchmarks/      Frozen 30-case STEP benchmark, manifest, hashes, lock, and thumbnails
config/          Gate 0 input and Gate 1 replay request
docs/            Reuse audit, schema definition, and Gate 1 engineering log
environment/     Conda definition and verified package record
evidence/        Gate 0 evidence and Gate 1 Fusion replay screenshots
external/        Benchmark, geometry-validation, freeze, and Gate verification tools
fusion_scripts/  Gate 0 export and Gate 1 known-sequence replay scripts
logs/            Structured run logs and Gate 0/Gate 1 verification reports
models/          Native Fusion and STEP evidence models
replay_outputs/  Native F3D, STEP, and JSON replay evidence
sequences/       Known-valid and intentionally invalid schema fixtures
shared/          Pure-standard-library frame and sequence validation modules
tests/           Automated Gate 0/Gate 1 regression tests
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
```

The smoke test expects the committed Gate 0 STEP evidence under `models/`. It generates or refreshes `models/cadquery_box.step` and `logs/external_python.json`.

## Fusion scripts

In Fusion, open **Utilities -> Scripts and Add-ins**. Use `fusion_scripts/Gate0BoxExport` for the Gate 0 smoke export and `fusion_scripts/Gate1SequenceReplay` for Gate 1 known-sequence replay.

The script:

1. reads `config/gate0_box.json`;
2. validates the schema and millimetre units;
3. creates a new Fusion design document;
4. sketches and extrudes a rectangular box;
5. verifies one body and six faces;
6. exports STEP and writes a structured run log.

The committed `run01` and `run02` outputs are frozen evidence. The script intentionally refuses to overwrite them. Use a disposable checkout or preserve/move those four run artifacts before performing a fresh two-run experiment.

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

## References and reuse boundary

Gate 0 uses Autodesk Fusion's installed Python API and CadQuery/OCP as infrastructure. Fusion 360 Gallery and Analysis Situs were reviewed as architectural references only; their search systems and source code are not dependencies of this repository. See [`docs/gate0_reuse_audit.md`](docs/gate0_reuse_audit.md).

No project licence is granted at this stage. The repository remains private while the research prototype is under evaluation.
