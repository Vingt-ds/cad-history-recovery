# Gate 4 closure report

## Decision

Gate 4 is **PASS as a frozen evaluation and benchmark-integrity gate**. This decision does not mean that every supported held-out case was recovered. It means that the fixed algorithm was evaluated once on the held-out split without post-result semantic tuning, both formal runs were sealed, and all 30 result packages satisfy the conditional artifact contract.

The held-out measurement is therefore retained as observed: 11 of 12 supported held-out cases were automatic successes, two of two unsupported cases were correctly rejected, and `T-S07` remains a structured failure.

## Frozen execution boundary

| Item | Evidence |
| --- | --- |
| Evaluation commit C | `3d04273301cdacb8936707164f492427aab3273c` |
| Formal development run | `benchmark_results/gate4-development-formal-20260905` |
| Development evidence commit | `bcde869a08b70d501c388d243feb4c78820339ab` |
| Formal held-out run | `benchmark_results/gate4-held-out-formal-20260905` |
| Held-out raw evidence commit | `0c7dc63` |
| Held-out seal evidence commit | `0625921cd91487a11af7476b4c2960f97c7b0a27` |
| Held-out execution count | one (`attempt_number=1`) |
| Expected labels at run time | not loaded |
| Expected-label release | only after both seals verified |

Both manifests record the same evaluation commit, `git_dirty_at_start=false`, the same frozen protocol/hash inventory and their correct split roles. The evaluation protocol explicitly states that success rate is a reported measurement, not a Gate 4 pass threshold.

## Results

| Metric | Development | Held-out | Overall |
| --- | ---: | ---: | ---: |
| Cases | 15 | 15 | 30 |
| Terminal `automatic_success` | 15 | 12 | 27 |
| Supported automatic success | 15/15 | 11/12 | 26/27 |
| Unsupported correct rejection | 0/0 | 2/2 | 2/2 |
| Geometry pass among validated cases | 15/15 | 12/12 | 27/27 |
| Fusion replay failures / attempts | 0/15 | 1/13 | 1/28 |
| Volume-IoU results | 15 | 10 | 25 |
| Surface-only validation | 0 | 2 | 2 |
| Complete result packages | 15/15 | 15/15 | 30/30 |
| Ambiguous cases | 2 | 2 | 4 |
| Manual corrections | 0 | 0 | 0 |

The 25 successfully computed IoU values range from `0.9999999999999998` to `1.0`. This is descriptive evidence, not a newly introduced acceptance threshold. The mean automatic analysis time recorded in the inference logs is approximately `0.1682 s` per case; it is not end-to-end Fusion wall time.

## Preserved failure and validation fallbacks

`T-S07` is a supported single-extrusion case whose inference reached Fusion replay. The frozen executor rejected its absolute frame with `failure_stage=fusion_replay` and `failure_code=unsupported_absolute_frame`. This is an executor-capability limitation, not one of the frozen infrastructure retry codes. The case was not rerun, relabelled or converted to `unsupported`.

`T-C02` and `T-C03` are the two frozen unsupported cases. They were rejected with, respectively, `no_gate2_candidate_passed_frozen_protocol` and `hole_like_geometry_outside_frozen_gate3_scope`. Neither case received fabricated replay or validation artifacts.

Boolean overlap failed for `T-H02` and `T-H04`. In accordance with the frozen protocol, both retain `volume_iou=null`, `boolean_validation_failed=true` and `validation_mode=surface_only`. They passed their frozen route-specific geometry protocol, but they are reported separately and are not included in the 25 IoU results.

Ambiguity remains independent of terminal status. The four ambiguous cases are `D-S01`, `D-S09`, `T-C01` and failed case `T-S07`.

## Post-run tooling fixes

Two audit-only defects were closed after raw execution:

1. The package auditor initially rejected `T-C02` because a legitimate non-empty rejected candidate set remained after candidate generation. Commit `e7d310c` corrected only the conditional package rule; it did not change routing, inference, sequence synthesis, thresholds, Fusion execution or case outcomes.
2. Combining the two evidence histories exposed that Git `core.autocrlf` can alter JSON checkout bytes while preserving content. Commit `af02d7d` allows only LF/CRLF normalization for JSON during seal verification. Binary artifacts and semantic text changes remain hash-sensitive, and the formal run contents and seals were not rewritten.
3. The cross-Gate verification found the same checkout risk in the byte-hashed Gate 0 shared configuration. Commit `2604975` marks only `config/gate0_box.json` as Git binary; its committed bytes and all three historical execution hashes remain unchanged.

The evaluation-time frozen files continue to be verified from commit C. These post-run fixes are recorded in `gate4_post_run_packaging_fixes.json` and must not be represented as evaluation-time semantic code.

## Demonstration cases

- `T-S01`: held-out seven-edge non-rectangular single extrusion, automatic and unambiguous, with Fusion replay and `volume_iou=1.0`.
- `T-H03`: held-out YZ-oriented base plus through cylindrical cut, automatic and unambiguous, with all analytic hole checks passing and `volume_iou=1.0`.

The selection is recorded in `gate4_demo_case_selection.json`. It does not change the benchmark denominator or omit the preserved failure.

## Evidence index

- `logs/gate4/gate4_verification_report.json`: unified PASS/FAIL checks.
- `logs/gate4/gate4_statistics.json`: development, held-out and overall statistics.
- `logs/gate4/gate4_case_records.json`: 30 per-case records after seal-gated label release.
- `logs/gate4/gate4_failure_taxonomy.json`: failed, unsupported and surface-only classifications.
- `logs/gate4/gate4_post_run_packaging_fixes.json`: audit-only post-run corrections.
- `benchmark_results/gate4-development-formal-20260905/seal.json`: immutable development inventory.
- `benchmark_results/gate4-held-out-formal-20260905/seal.json`: immutable held-out inventory.
- `logs/gate4/heldout_execution_lock.json`: single-execution lock.
- `evidence/gate4/heldout_batch_complete.png`: Fusion UI confirmation of 13 attempted, 12 successful and one failed replay.

## Scope of the conclusion

Gate 4 supports the research claim that the frozen rule-based pipeline was evaluated reproducibly on the fixed 30-case benchmark, with development and held-out results reported separately. It does not establish general CAD-history recovery, perfect held-out recovery, recovery of the original designer's unique intent, or support for operations outside the frozen Gate 2 and Gate 3 scopes.

No Gate 4 completion tag name was defined in the frozen contract, so this closure report does not invent or move a tag. The authoritative closure references are the evaluation commit, the two sealed evidence histories, the unified verification report and the eventual integrated main commit.
