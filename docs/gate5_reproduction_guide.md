# Gate 5 Single-Case Reproduction Guide

## Scope

This guide exercises the frozen Gate 0-4 capability on one development case. It creates demonstration-only artifacts under `runs/`; it does not alter or replace the formal benchmark results, protocols, thresholds, or `gate0-4-frozen-baseline-v1` tag.

The inference input remains a history-free STEP/B-rep. Case identifiers are used only by the outer orchestration layer. The inference call receives a neutrally named copy of the STEP bytes, the frozen source SHA-256, a neutral work directory, and the frozen Gate 2 and Gate 3 protocols.

## External prerequisites

- Windows with Git and Conda available.
- Autodesk Fusion installed, launched, and signed in. Fusion is an external prerequisite and is not installed by this repository.
- The private repository checkout, including the frozen benchmark inputs.

## Create the Python environment

From the repository root:

```powershell
conda env create -f environment/environment.yml
conda activate cadseq
python external/cadquery_smoke.py
```

If the `cadseq` environment already exists, do not recreate it for routine use. The final clean-environment acceptance uses a separate temporary Conda prefix.

## Prepare D-S04

```powershell
python tools/gate5_demo.py prepare `
  --project-root . `
  --case-id D-S04 `
  --output-root runs/gate5
```

The command prints JSON containing the newly created run directory. It refuses held-out cases, the sealed-only ambiguity case `D-S01`, a mismatched source hash, an unsafe output path, an existing run directory, or an existing active Fusion request.

## Run the frozen Fusion executor through the thin wrapper

1. In Fusion, open **Utilities -> Scripts and Add-ins**.
2. Add or locate `fusion_scripts/Gate5DemoWrapper`.
3. Run `Gate5DemoWrapper` once.
4. Confirm that Fusion reports one completed case.

The wrapper reads only `runs/gate5_active_request.json`. It validates that the request resolves to one immediate child of `runs/gate5/`, then delegates document creation and replay to the frozen `Gate2SequenceReplay._replay_case` implementation. It contains no sketch, extrusion, cut, inference, or geometry-validation implementation.

## Finalize and verify

Replace `<run-id>` with the run directory printed by `prepare`:

```powershell
python tools/gate5_demo.py finalize `
  --project-root . `
  --run-dir runs/gate5/<run-id>

python tools/gate5_demo.py verify `
  --project-root . `
  --run-dir runs/gate5/<run-id>
```

`finalize` invokes the existing route-specific Gate 2 or Gate 3 validator. It then moves the active request into the run directory as `replay_request_used.json`, preventing accidental reuse. A second finalization is rejected.

## Demonstration package layout

```text
runs/gate5/<run-id>/
├── manifest.json
├── metadata/input_metadata.json
├── analysis/
│   ├── brep_summary.json
│   ├── candidates.json
│   └── inference_log.json
├── sequence/inferred_sequence.json
├── replay/
│   ├── replay.f3d
│   ├── replay.step
│   └── replay_log.json
├── batch_replay_log.json
├── environment.json
├── replay_request_used.json
├── validation/validation_metrics.json
└── final_status.json
```

Every Gate 5 demo manifest states:

```text
evidence_role = demonstration_only
formal_evaluation = false
source_split = development
baseline_tag = gate0-4-frozen-baseline-v1
```

## Status semantics

- `supported`: the observed B-rep is inside the frozen candidate language and yields a replayable candidate. It does not mean that the recovered sequence is the unique original designer history.
- `ambiguous=true`: more than one candidate satisfies the frozen acceptance contract. This flag is independent of terminal success or failure.
- `unsupported`: no hypothesis inside the frozen Gate 2/3 language is accepted; Fusion replay is not attempted.
- executor failure: inference produced a candidate, but the frozen Fusion replay path could not execute it or did not produce complete trusted replay evidence.
- geometry failure: Fusion produced replay artifacts, but the frozen route-specific validator did not accept the result.

`T-S07` is the preserved executor-boundary example: the frozen system reached Fusion replay, which rejected an absolute RY45 frame as `unsupported_absolute_frame`. It is not evidence of fundamental history ambiguity and is not rerun in Gate 5.
