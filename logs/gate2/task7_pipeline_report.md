# Gate 2 Task 7: Analysis Pipeline and Gate Verifier

## Debug run

- Run ID: `gate2-debug-analysis-20260903`
- Run kind: `debug`
- Selection source: frozen `case_matrix.json`; D-S01 through D-S10 only.
- Frozen validation protocol SHA-256: `8656e3882ee8c71c310b3ad5afe85177cf8e1d2e67d1bff6d03e13d64148c05a`
- Analysis outcome: 10 awaiting Fusion, 0 failed.
- Every case contains input metadata, canonical B-rep facts, retained candidates, inference log, and selected `cadseq-0.2` sequence.
- No case contains `final_status.json`; the debug analysis run makes no terminal success claim before Fusion replay.

## Failure isolation

The focused test processes an invalid STEP before a valid non-rectangular D-S04 input. The invalid case receives a structured `failed` status at `brep_inspection`, while D-S04 continues to `awaiting_fusion`. A valid STEP retains its canonical B-rep summary even if a later stage fails.

## Verification semantics

`verify_gate2.py` reports package completeness, terminal status, ambiguity, and geometric pass counts separately. Gate passage requires all of the following:

- exact D-S01 through D-S10 manifest set;
- run-level environment evidence;
- `git_dirty_at_start=false`;
- 10/10 complete packages;
- at least 8 `automatic_success` cases;
- geometry pass for every successful case;
- no supported development case relabelled as `unsupported`.

## Automated verification

- Pipeline and verifier focused tests: 5 tests, 0 failures.
- Full repository regression after Task 7: 143 tests, 0 failures.
