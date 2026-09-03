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
