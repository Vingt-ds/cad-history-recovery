# Gate 5 Demonstration Runbook

## Presentation contract

The three demonstrations explain the frozen Gate 0-4 evidence chain. They do not create a new benchmark, update success counts, tune a threshold, or claim general CAD-history recovery. Stop the demonstration if any command or artifact differs from the prepared run; do not repair JSON, code, or parameters live.

## Pre-demo checks

1. Confirm `git status --short` contains no unexplained tracked changes.
2. Confirm `git rev-parse gate0-4-frozen-baseline-v1^{commit}` still returns `c3e448525e9424383e847332f4d0afc1444e7380`.
3. In a separate clean checkout at `gate0-4-frozen-baseline-v1`, run the Gate 0-4 baseline verifier with `--require-tag`. Do not run that verifier with the Gate 5 delivery commit as `HEAD`, because its frozen contract intentionally requires `HEAD` to equal the baseline-tag target.
4. Confirm Fusion is installed, running, and signed in.
5. Confirm no `runs/gate5_active_request.json` remains from a previous demonstration.
6. Open each backup JSON, STEP, F3D, screenshot, and MP4 before the session.

## Demo 1 — D-S04 single extrusion

Purpose: show a non-rectangular development example through the complete demonstration path.

1. Run `gate5_demo.py prepare` for `D-S04`.
2. Show the JSON output and the demonstration-only manifest fields.
3. Run `Gate5DemoWrapper` in Fusion.
4. Run `finalize`, then `verify`.
5. Open `sequence/inferred_sequence.json`, `replay/replay.f3d`, `replay/replay.step`, and `validation/validation_metrics.json`.
6. State only that this development case produced a plausible executable sequence accepted by the frozen route-specific validator.

## Demo 2 — D-H01 base plus one through hole

Purpose: show the frozen coupled base-extrusion and straight through-cut route.

1. Repeat the complete prepare, Fusion replay, finalize, and verify sequence for `D-H01`.
2. Show the accepted hole evidence in `analysis/candidates.json`.
3. Show the `New Extrusion` followed by `Cut + through_all` operations in the inferred sequence.
4. Open the replayed Fusion document and validation metrics.
5. Do not generalize the observation to blind, stepped, multiple, intersecting, threaded, or otherwise untested holes.

## Demo 3 — D-S01 sealed ambiguity evidence

Purpose: explain ambiguity without rerunning inference or modifying the sealed result.

Source mode is fixed to:

```text
sealed_artifact_only
```

1. Run the Gate 4 seal verifier for `benchmark_results/gate4-development-formal-20260905`.
2. Read only the sealed files under `benchmark_results/gate4-development-formal-20260905/cases/D-S01/`.
3. Show multiple accepted entries in `analysis/candidates.json`.
4. Show the deterministic `selected_candidate_id` and canonical `sequence/inferred_sequence.json`.
5. Show `ambiguous=true` in both the candidate evidence and final status.
6. State that multiple candidates satisfy the frozen acceptance contract; do not claim that the original designer history is known or that all alternatives are semantically distinct histories.

The `prepare` command intentionally rejects `D-S01` with `sealed_artifact_only`. Manual JSON correction is prohibited.

## Failure boundary

`T-S07` may be mentioned as a known limitation but is not a live demonstration. Its frozen outcome is an executor limitation (`unsupported_absolute_frame`), not an unsupported semantic case and not demonstrated history underdetermination.

## Backup policy

Each demo has a local MP4 and PNG with the fixed names in `docs/gate5_media_index.md`. If live Fusion execution is unstable, switch to the matching backup without changing code, data, parameters, thresholds, or artifacts.
