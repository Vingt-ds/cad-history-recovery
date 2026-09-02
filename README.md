# Rule-based CAD Construction Sequence Synthesis from B-rep Models

This repository contains a deterministic, semi-automatic pipeline under development for converting history-free B-rep/STEP models into plausible, replayable CAD construction sequences.

> **Current status:** Gate 0 is closed and Gate 1 is in progress. The 30-case raw B-rep benchmark and schema v0.1 static validator are implemented. Fusion known-sequence replay and automatic B-rep-to-history inference have not started and are not claimed here.

## Gate 1 current scope

- 30 fixed raw STEP inputs: 15 development and 15 held-out;
- 27 deterministic CadQuery sources and three Fusion-manual sources;
- schema v0.1 known-sequence examples for a box and a box with one through-hole;
- one shared pure-standard-library validator for external Python and future Fusion replay;
- explicit rejection fixtures for unsupported Cut distance, broken loop references, invalid operation-cap references, and invalid frames.

The held-out split is assembled but is not frozen until the planned manifest, hashes, and lock are created. It must not be described as blind or unseen data.

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
config/          Shared Gate 0 JSON input
docs/            Reuse and engineering audit notes
environment/     Conda definition and verified package record
evidence/        Manual Fusion timeline evidence and export settings
external/        CadQuery smoke test and consolidated verifier
fusion_scripts/  Fusion Python script and manifest
logs/            Structured run logs and Gate 0 verification report
models/          Native Fusion and STEP evidence models
tests/           Automated Gate 0 regression tests
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
python external/verify_gate0.py
```

The smoke test expects the committed Gate 0 STEP evidence under `models/`. It generates or refreshes `models/cadquery_box.step` and `logs/external_python.json`.

## Fusion script

In Fusion, open **Utilities -> Scripts and Add-ins**, add the checkout's `fusion_scripts/Gate0BoxExport` folder, and run `Gate0BoxExport`.

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

Gate 1 has not yet implemented:

- Fusion replay of schema v0.1 operations;
- runtime `operation_cap` resolution or Cut-intersection checks;
- geometric-distance and volume-IoU validation;
- the formal benchmark manifest/hash lock;
- automatic B-rep feature or history inference.

## References and reuse boundary

Gate 0 uses Autodesk Fusion's installed Python API and CadQuery/OCP as infrastructure. Fusion 360 Gallery and Analysis Situs were reviewed as architectural references only; their search systems and source code are not dependencies of this repository. See [`docs/gate0_reuse_audit.md`](docs/gate0_reuse_audit.md).

No project licence is granted at this stage. The repository remains private while the research prototype is under evaluation.
