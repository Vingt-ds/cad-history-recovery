# Gate 0-4 Research Baseline

## Research question and bounded hypothesis

History-free STEP/B-rep models preserve geometry and topology but not the designer's feature timeline or intent. This baseline tests a narrow question: can deterministic geometric and topological evidence constrain a plausible, executable construction sequence for predefined feature classes?

The evaluated hypothesis is deliberately limited. For a single extrusion, or for one line-profile base extrusion followed by one straight through cylindrical cut with explicit circular openings, the pipeline should be able to extract canonical facts, form auditable hypotheses, synthesize a parametric sequence, replay it in Fusion, and compare the reconstructed solid with the reference.

## Evidence-producing architecture

```text
history-free STEP
        |
        v
canonical B-rep facts
        |
        v
fact-driven feature hypotheses
        |
        v
deterministic candidate validation and selection
        |
        v
parametric sequence synthesis
        |
        v
Fusion replay and geometry validation
```

The fact layer is separated from inference. CadQuery validates candidates; it does not search by generating arbitrary histories. Ambiguity is recorded independently of terminal status, and rejected or failed cases remain in the evidence set.

## Gate progression

- Gate 0 established the Fusion/external-Python execution boundary and reproducible STEP inspection.
- Gate 1 froze the 30-case benchmark, replay schema, reference semantics, and baseline geometry checks.
- Gate 2 recovered the ten development single-extrusion cases under a frozen protocol.
- Gate 3 recovered the five development base-plus-through-hole cases using a coupled hypothesis rather than appending a cut to an independently accepted base.
- Gate 4 evaluated one frozen implementation commit on formal development and held-out splits, sealed raw results, and released expected labels only after sealing.

## Frozen observations

| Observation | Result |
| --- | ---: |
| Terminal automatic success | 27/30 |
| Supported-case automatic recovery | 26/27 |
| Unsupported correct rejection | 2/2 |
| Geometry pass among validated cases | 27/27 |
| Conditionally complete result packages | 30/30 |
| Volume-IoU results | 25 |
| Surface-only validations | 2 |

The success taxonomy is descriptive:

- supported single extrusions: 17/18 automatic successes;
- supported base-plus-through-hole constructions: 9/9 automatic successes;
- designated ambiguity control: one canonical automatic result with `ambiguous=true`;
- unsupported controls: 2/2 structured rejections;
- ambiguity flags: four total, independent of terminal status;
- validation modes: 25 Boolean volume-IoU results and two surface-only fallbacks.

These observations do not establish that any individual geometric property caused success. The benchmark is too small and controlled for causal or population-level inference.

## Preserved boundary case

`T-S07` is a frozen supported case whose inference reached Fusion replay. The executor rejected its absolute frame with `failure_stage=fusion_replay` and `failure_code=unsupported_absolute_frame`. It was not retried, relabelled, or converted to unsupported. This is evidence of an executor capability boundary, not evidence of multi-feature ambiguity or fundamental history underdetermination.

## Current capability boundary

The frozen pipeline demonstrates:

- deterministic canonical facts for valid single-solid STEP inputs in the tested environment;
- single-extrusion recovery for one 3-8-edge line-only outer profile or one standalone complete circle within the frozen protocol;
- coupled recovery of one line-only base extrusion and one straight through cylindrical cut when two circular openings and one connecting cylindrical face are explicit;
- deterministic sequence synthesis, Fusion replay, structured failure semantics, conditional result packaging, and route-specific geometry validation;
- content-driven routing isolated from case identifiers, filenames, parent directories, and expected labels.

It does not demonstrate:

- recovery of the unique original designer history;
- arbitrary frames or topological references throughout the Fusion executor;
- blind, multiple, tapered, stepped, counterbored, countersunk, threaded, patterned, or interacting holes;
- fillet, chamfer, revolve, sweep, loft, shell, pattern, or general feature-graph recovery;
- general operation ordering, industrial-scale robustness, or external validity beyond the frozen benchmark;
- a universal surface-distance or volume-IoU acceptance threshold.

## Defensible conclusion

Under the frozen benchmark protocol, the pipeline produced 27 terminal automatic successes, including 26/27 supported-case automatic recoveries, while correctly rejecting 2/2 out-of-scope cases. All 27 validated reconstructions passed their frozen route-specific geometry protocol, and all 30 cases produced conditionally complete result packages.

This supports the narrower conclusion that deterministic, auditable recovery is feasible for the constrained feature classes and execution environment tested here. It does not support a claim of general CAD-history recovery or statistically representative industrial performance.

## Evidence pointers

- Baseline index: [`config/gate0_4_baseline_manifest.json`](../config/gate0_4_baseline_manifest.json)
- Benchmark definition: [`docs/benchmark_v1_card.md`](benchmark_v1_card.md)
- Gate 4 closure: [`logs/gate4/gate4_closure_report.md`](../logs/gate4/gate4_closure_report.md)
- Gate 4 verification: [`logs/gate4/gate4_verification_report.json`](../logs/gate4/gate4_verification_report.json)
- Gate 4 statistics: [`logs/gate4/gate4_statistics.json`](../logs/gate4/gate4_statistics.json)

The next research-question class is controlled multi-operation reconstruction. It remains a future hypothesis requiring a separate problem definition, benchmark, and branch; it is not part of this frozen baseline.
