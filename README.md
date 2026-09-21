# Rule-based CAD Construction Sequence Synthesis from B-rep Models

This repository implements a deterministic, semi-automatic and rule-based pipeline that converts history-free STEP/B-rep models into plausible, replayable CAD construction sequences.

The project addresses the practical question posed in the original project description:

> Can the final geometry and topology of a B-rep model constrain an executable CAD construction explanation?

The output is an auditable construction explanation that can be replayed in Autodesk Fusion and checked against the input geometry. The project does **not** claim recovery of the unique original designer history.

## Final project status

The repository contains the completed research implementation and delivery materials for the verified project scope:

| Required deliverable | Repository evidence | Status |
| --- | --- | --- |
| Rule-based code repository | `external/`, `shared/`, `fusion_scripts/`, `tools/` | Complete |
| Executable sequence schema | [`docs/sequence_schema_v0.1.md`](docs/sequence_schema_v0.1.md), [`docs/sequence_schema_v0.2.md`](docs/sequence_schema_v0.2.md) | Complete |
| Curated benchmark | [`benchmarks/`](benchmarks/), 30 frozen cases | Complete |
| Generated sequences, logs and replay outputs | [`benchmark_results/`](benchmark_results/) | Complete under condition-dependent package rules |
| Validation metrics and reports | [`logs/gate4/`](logs/gate4/) and per-case result packages | Complete |
| Final presentation | [`presentations/gate5/gate5_technical_briefing.pptx`](presentations/gate5/gate5_technical_briefing.pptx) | Complete |
| Three representative demonstrations | D-S04, D-H01 and D-S01; see [`docs/gate5_demo_runbook.md`](docs/gate5_demo_runbook.md) | Prepared for the live presentation |

The three existing short MP4 walkthroughs are supplementary artifact explanations. The project description requires a final presentation with a live demo; it does not require submitted operation recordings. If recorded backup videos are requested later, they must show real Fusion operation and must follow the provenance rules in [`docs/gate5_media_index.md`](docs/gate5_media_index.md).

## Supported construction scope

The frozen implementation supports two controlled construction classes:

1. **Single extrusion**
   - one planar outer profile;
   - either a closed 3-8-edge Line loop or one complete Circle;
   - one `New` extrusion with a positive distance;
   - named XY/XZ/YZ origin planes or a deterministic audited B-rep frame.

2. **Base extrusion with one straight through cylindrical cut**
   - one Line-profile base extrusion;
   - two explicit circular openings;
   - one connecting cylindrical face;
   - one semantic operation-cap Sketch;
   - one `Cut + through_all` operation.

The project deliberately excludes learning-based inference. It also excludes general fillet, chamfer, revolve, sweep, loft, shell, pattern, blind-hole, multiple-hole and arbitrary feature-graph recovery.

## End-to-end workflow

```text
History-free STEP/B-rep
        |
        v
Canonical geometry and topology facts
        |
        v
Rule-based candidate hypotheses
        |
        v
Candidate reconstruction, validation and deterministic ranking
        |
        v
Executable cadseq JSON
        |
        v
Autodesk Fusion replay -> F3D + STEP + execution log
        |
        v
Route-specific geometry validation
        |
        v
Auditable result package
```

The inference layer reads geometry and topology evidence rather than filenames, case IDs or expected labels. Expected labels are introduced only after sealed formal runs for statistical reporting.

## Sequence representation

The project defines two compatible schema versions:

- `cadseq-0.1` defines Sketch and Extrude operations, profile geometry, references and replay constraints.
- `cadseq-0.2` adds auditable root-frame provenance without broadening the operation vocabulary.

The schema distinguishes:

- named origin-plane references;
- deterministic frames inferred from the observed B-rep;
- semantic references such as an operation cap;
- an audited `absolute_fallback` mode for manual correction;
- validation failures, unsupported scope and executor failures.

The formal Gate 4 evaluation used zero manual corrections. The repository supplies the audited correction representation but does not provide an interactive CAD editing interface.

## Benchmark

The benchmark contains 30 frozen models:

| Split | Composition | Cases |
| --- | --- | ---: |
| Development | 10 single extrusions and 5 base-plus-through-hole constructions | 15 |
| Frozen held-out | 8 single extrusions, 4 base-plus-through-hole constructions, 1 ambiguity control and 2 unsupported controls | 15 |
| Total | All categories | 30 |

Source-construction provenance comprises 27 CadQuery-generated models and three models manually constructed in Fusion. The held-out split was reserved from semantic development after the benchmark freeze. It is a frozen held-out set, not a blind, secret or independently sourced dataset.

Authoritative benchmark records:

- [`benchmarks/case_matrix.json`](benchmarks/case_matrix.json)
- [`benchmarks/manifest.json`](benchmarks/manifest.json)
- [`benchmarks/freeze.lock.json`](benchmarks/freeze.lock.json)
- [`docs/benchmark_v1_card.md`](docs/benchmark_v1_card.md)

## Frozen evaluation results

The final frozen evaluation used one implementation and one set of protocols for both the development and held-out splits.

| Observation | Result | Interpretation |
| --- | ---: | --- |
| Terminal automatic successes | 27/30 | Overall terminal outcome |
| Supported-case automatic recoveries | 26/27 | One supported case reached Fusion but failed at the executor boundary |
| Unsupported controls correctly rejected | 2/2 | Filleted and blind-hole controls |
| Geometry passes | 27/27 | Cases with trusted replay evidence |
| Conditionally complete result packages | 30/30 | Package completeness is not algorithmic success |
| Volume-IoU results | 25 | Two additional cases used surface-only validation |
| Manual corrections during formal evaluation | 0 | The frozen evaluation remained automatic |
| Cases retaining `ambiguous=true` | 4 | Ambiguity is independent of terminal success |

`T-S07` is the preserved supported failure. Semantic inference produced a candidate, but the frozen Fusion executor rejected its absolute RY45 frame as `unsupported_absolute_frame`. The case was not retried, relabelled as unsupported or presented as history ambiguity.

Authoritative reports:

- [`logs/gate4/gate4_verification_report.json`](logs/gate4/gate4_verification_report.json)
- [`logs/gate4/gate4_statistics.json`](logs/gate4/gate4_statistics.json)
- [`logs/gate4/gate4_closure_report.md`](logs/gate4/gate4_closure_report.md)
- [`docs/gate0_4_research_baseline.md`](docs/gate0_4_research_baseline.md)

## Representative demonstrations

The final presentation uses three development examples with different evidence roles:

| Case | Purpose | Execution rule |
| --- | --- | --- |
| `D-S04` | Single-extrusion end-to-end path | Fresh delivery-layer inference, Fusion replay and frozen validation |
| `D-H01` | Base extrusion plus one straight through cylindrical cut | Fresh delivery-layer inference, Fusion replay and frozen validation |
| `D-S01` | Multiple accepted construction hypotheses | Read-only view of the sealed Gate 4 artifact; no fresh inference or JSON editing |

Gate 5 demonstrations have `evidence_role=demonstration_only` and `formal_evaluation=false`. They explain the frozen results but do not change benchmark statistics.

Operational guidance:

- [`docs/gate5_demo_runbook.md`](docs/gate5_demo_runbook.md)
- [`docs/gate5_reproduction_guide.md`](docs/gate5_reproduction_guide.md)
- [`docs/gate5_media_index.md`](docs/gate5_media_index.md)

## Environment

The verified baseline environment is:

| Component | Verified version |
| --- | --- |
| Autodesk Fusion | 2704.1.53 |
| Conda Python | 3.11.16 |
| CadQuery | 2.8.0 |
| OCP | 7.9.3.1 |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |

Create the external Python environment with:

```powershell
conda env create -f environment/environment.yml
conda activate cadseq
```

Autodesk Fusion is a separately installed, signed-in external prerequisite.

## Reproduce the frozen checks

The baseline verifier is intentionally bound to the historical baseline tag. Verify it in a separate detached worktree rather than at the later delivery commit:

```powershell
git worktree add --detach ../cad-history-baseline-verify gate0-4-frozen-baseline-v1
python ../cad-history-baseline-verify/tools/verify_gate0_4_baseline.py `
  --project-root ../cad-history-baseline-verify `
  --require-tag
```

Run the full regression suite:

```powershell
python -m unittest discover -s tests -v
```

Run the gate-specific verifiers:

```powershell
python external/verify_gate0.py --project-root .
python external/verify_gate1.py
python external/verify_gate2.py benchmark_results/gate2-formal-20260903-e93dc2f
python external/verify_gate3.py benchmark_results/gate3-formal-20260904-8e8ae63
python external/verify_gate4.py `
  --project-root . `
  --development-run benchmark_results/gate4-development-formal-20260905 `
  --held-out-run benchmark_results/gate4-held-out-formal-20260905
```

## Reproduce a delivery demonstration

Prepare the fixed D-S04 demonstration:

```powershell
python tools/gate5_demo.py prepare `
  --project-root . `
  --case-id D-S04 `
  --output-root runs/gate5
```

In Fusion, open **Utilities -> Scripts and Add-ins**, load `fusion_scripts/Gate5DemoWrapper`, and run it once. Then finalize and verify the run:

```powershell
python tools/gate5_demo.py finalize `
  --project-root . `
  --run-dir runs/gate5/<run-id>

python tools/gate5_demo.py verify `
  --project-root . `
  --run-dir runs/gate5/<run-id>
```

Generated demonstrations remain under the ignored `runs/` directory. They do not overwrite formal evaluation evidence.

## Repository structure

```text
benchmark_results/  Frozen formal runs, replay artifacts, metrics and per-case packages
benchmarks/          Frozen 30-case input set, case matrix, hashes and thumbnails
config/              Frozen protocols, routing policy, inventories and manifests
docs/                Schemas, benchmark card, research interpretation and demo guidance
environment/         Conda environment definition and verified package snapshot
evidence/            Gate 0 and Gate 1 screenshots and supporting execution evidence
external/            B-rep inspection, inference, reconstruction, validation and reporting
fusion_scripts/      Fusion scripts for model creation and executable sequence replay
logs/                Gate reports, statistics, closure records and failure taxonomy
models/              Native Fusion and STEP evidence models
presentations/       Final technical presentation
replay_outputs/      Committed Gate 1 native and neutral-format replay evidence
sequences/           Valid and intentionally invalid cadseq fixtures
shared/              Shared frame and sequence validators used by Python and Fusion
tests/               Regression, invariance, packaging and protocol tests
tools/               Baseline verification and delivery-demonstration utilities
```

## Evidence and provenance

The frozen scientific baseline is anchored by the annotated tag:

```text
gate0-4-frozen-baseline-v1
```

The baseline manifest is [`config/gate0_4_baseline_manifest.json`](config/gate0_4_baseline_manifest.json). It binds benchmark inputs, protocols, formal runs and verification reports to recorded hashes and Git provenance.

Formal result packages are immutable evidence. Demonstration runs, presentation screenshots and supplementary media are explanatory delivery artifacts and are not new scientific evaluations.

## Limitations

- The system recovers plausible executable explanations, not the unique original feature history.
- The supported feature vocabulary is intentionally narrow.
- The benchmark is small, curated and dominated by one procedural generator.
- Exporter and CAD-kernel diversity is limited.
- The held-out split is frozen but not independently sourced or statistically representative.
- Near-unity IoU values on this benchmark do not define a universal tolerance.
- Surface-only validation is reported separately from volume IoU.
- The repository has an audited manual-correction representation but no interactive correction UI.
- External validity for arbitrary industrial B-rep models remains unknown.

## References and reuse boundary

DeepCAD, WHUCAD and VideoCAD informed the project context and comparison boundary. No learning-based implementation or third-party research code was copied into the pipeline. See:

- [`docs/third_party_and_references.md`](docs/third_party_and_references.md)
- [`docs/gate0_reuse_audit.md`](docs/gate0_reuse_audit.md)
- [`docs/gate5_license_audit.md`](docs/gate5_license_audit.md)

This is a private research repository. The absence of a root software licence means that access does not grant permission to copy, modify or redistribute the code or data.
