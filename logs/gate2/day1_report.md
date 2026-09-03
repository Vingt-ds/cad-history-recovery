# Gate 2 Day 1 B-rep Fact Layer Report

- Actual execution date: 2026-09-03 (started earlier than the frozen 9 September schedule without changing `timeline-v1.2`).
- Scope: D-S01 through D-S10 only; no held-out input was inspected.
- Contract: `brep-summary-0.1` canonical facts only; no adjacency, convexity, candidate, scoring, or Fusion fields.
- Import path: one CadQuery STEP import followed by OCP inspection of the same wrapped solid.
- Test result at checkpoint: 100 tests passed, including the existing 85 Gate 0/1 tests.

## Canonical outputs

| Case | Faces | Wires | Edges | Vertices | Summary SHA-256 |
|---|---:|---:|---:|---:|---|
| D-S01 | 6 | 6 | 12 | 8 | `e3d68026aaf22543ab8e4b60a68000f19f7e715cc039294ed9e2cb1772bc0eb9` |
| D-S02 | 5 | 5 | 9 | 6 | `b2f3b47f9f864584a060279ed932fced9f6e8f7b29db013c2c0c38cbfa882608` |
| D-S03 | 7 | 7 | 15 | 10 | `9677c6b1167290ccc0ffee708bbd38fac3c4d740b0ab1bca32ea9694f40ea1e2` |
| D-S04 | 8 | 8 | 18 | 12 | `11f1b896927b7e6e52b4fbbc16e316a8fc378b04dbffbd8e95eba743770b3fb8` |
| D-S05 | 10 | 10 | 24 | 16 | `0ec27cff1c9528b53db2e471f6b5f9b4320a7a4b189819420e094318856a2016` |
| D-S06 | 10 | 10 | 24 | 16 | `594fc5ef374affb03a34b1dbc2638e307e4d10187382bea4a6b0e6d48170b834` |
| D-S07 | 3 | 3 | 3 | 2 | `806351959172a8bb16a7d44656de308846ed027931b14398f41534e15b171e25` |
| D-S08 | 8 | 8 | 18 | 12 | `96bede81a41f976a6c2a77f6eb3726e1d71722f61e0fc95926e6384c3503c116` |
| D-S09 | 6 | 6 | 12 | 8 | `b34b99e0a59e36e3b14d37162a93ccea0a7c5e4b47f8ac22736bd4f9f3683f8d` |
| D-S10 | 9 | 9 | 21 | 14 | `ae108e8731df8a6b189346a2baff3667e443fe85bbd38e1cef253e801b7e63f5` |

All ten summaries contain one valid solid, resolve all canonical references, contain no forbidden inference-layer fields, and were generated without embedding a `run_id`.
