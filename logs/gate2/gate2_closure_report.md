# Gate 2 closure report

- Formal run: `gate2-formal-20260903-e93dc2f`
- Code commit at run start: `e93dc2ffa8b720cd31825f05decbf1f210d40b51`
- Frozen validation protocol SHA-256: `8656e3882ee8c71c310b3ad5afe85177cf8e1d2e67d1bff6d03e13d64148c05a`
- Fusion replay: 10 success, 0 failure
- Automatic terminal success: 10/10
- Frozen geometry protocol pass: 10/10
- Complete result packages: 10/10
- Ambiguous accepted histories: 2 (`D-S01`, `D-S09`)
- Manual success: 0
- Failed: 0
- Unsupported: 0
- Gate decision: PASS

The two earlier formal attempts remain immutable evidence. `gate2-formal-20260903-d3e22ee` stopped before modeling because Fusion reused a stale cadseq-0.1 validator. `gate2-formal-20260903-ed117e8` completed four named-origin cases and exposed that transient `setByPlane` is unsupported in Fusion's parametric or hybrid environment. Neither attempt was counted as the final algorithm outcome or overwritten.

Gate 2 passes the frozen requirement of at least 8/10 automatic successes, geometry success for every successful case, no post-hoc unsupported relabeling, and 10/10 complete packages. The reported result is limited to the frozen development single-extrusion subset and does not claim arbitrary B-rep history recovery.

## Post-closure repository audit

A later documentation and test-coverage audit was completed at commit `9501b939984d04f4da19c8e111fbc9957be7a80a` (`docs: close Gate 2 audit gaps`). This audit did not rerun, overwrite, or reinterpret the immutable formal run. The saved formal verification report remains `benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json` with SHA-256 `5047e6f6fdbe5c3b8aa2119822e3cd3951be61e2523b56316083de027a83f95f`.

The audit closed three repository-level gaps:

- `README.md` now reports the completed Gate 2 scope, evidence locations, reproduction commands, and explicit non-claims.
- `logs/gate2/task8_fusion_adapter_report.md` now records the implemented parametric construction-plane paths: `setByOffset` for axis-aligned inferred frames and `setByAngle` about a parametric construction axis for rotated inferred frames. The superseded `setByPlane` attempt remains documented only as preserved failure evidence.
- `tests/test_brep_inspection.py` now covers six previously missing Day 1 negative/topology paths: invalid STEP import, zero solids, multiple solids, invalid solid, non-finite geometry, and coincident geometry with distinct topology incidence.

Fresh post-audit verification records:

- Full repository regression: 169 tests, 0 failures.
- Gate 0 verifier: 22/22 checks passed.
- Gate 1 verifier: 8/8 checks passed.
- Gate 2 formal verifier: 10/10 automatic success, 10/10 geometry pass, 10/10 package completeness, two ambiguous accepted histories, and `gate_pass=true`.

These additions improve repository documentation and negative-path evidence; they do not change the frozen case selection, schemas, validation protocol, candidate histories, Fusion outputs, terminal statuses, or Gate 2 pass decision. The immutable completion tag `gate2-forward-path` resolves to commit `5f755d6ba92bd47e48553209ac55c71b41485099`, while the later post-closure audit commit is intentionally recorded separately above rather than rewriting that tag.
