# Benchmark v1 Card

## Purpose

This benchmark supports controlled evaluation of deterministic construction-sequence recovery from history-free STEP/B-rep models. It is a curated controlled benchmark, not a random or representative sample of industrial CAD models.

The authoritative case definitions and immutable input hashes are in [`benchmarks/case_matrix.json`](../benchmarks/case_matrix.json), [`benchmarks/manifest.json`](../benchmarks/manifest.json), and [`benchmarks/freeze.lock.json`](../benchmarks/freeze.lock.json). This card explains their use; it does not redefine or copy them.

## Composition

| Split | Composition | Cases |
| --- | --- | ---: |
| Development | ten single extrusions; five base-plus-through-hole constructions | 15 |
| Held-out | eight single extrusions; four base-plus-through-hole constructions; one ambiguity control; two unsupported controls | 15 |
| Total | all categories | 30 |

The source-construction provenance is 27 CadQuery-generated cases and three Fusion manually modelled source constructions. “Manually modelled” describes benchmark construction provenance, not human correction during evaluation.

Explicit generator frame metadata covers XY (11 cases), XZ (6), YZ (6), RX30 (1), and RY45 (1). The remaining cases contain manually specified or special construction conditions and are not forced into the same frame/profile categorization scheme.

## Split and label use

The development split was available for rule, protocol, and implementation development before the Gate 4 evaluation freeze. The held-out split was reserved from semantic development after the Gate 1 benchmark freeze. It is accurately described as frozen held-out, not as blind, secret, independently sourced, or previously unseen.

Gate 4 used one final evaluation commit for both formal splits. Semantic inference received STEP content and source hash but could not inspect case IDs, filenames, parent directories, family labels, expected scope, expected behavior, or generator geometry. Rename and parent-path invariance tests protected that firewall. Expected labels were loaded for statistics only after both raw formal runs had been sealed.

## Supported and control roles

The supported scope comprises:

- a single extrusion from one 3-8-edge line-only outer profile or one standalone complete circle under the frozen Gate 2 protocol;
- one line-profile base extrusion followed by one straight through cylindrical cut with two explicit circular openings and one connecting cylindrical face under the frozen Gate 3 protocol.

The held-out controls comprise:

- `T-C01`, an ambiguity control expected to emit a deterministic canonical candidate while retaining `ambiguous=true`;
- `T-C02`, an unsupported filleted solid;
- `T-C03`, an unsupported blind-hole solid.

The case label is an evaluation role, not an input to routing or inference. Failed supported cases cannot be relabelled after observing results.

## Evaluation contract

- Formal development and held-out runs use the same frozen implementation, routing policy, schemas, and validation protocols.
- Held-out semantic execution is one attempt. Only predefined, demonstrably infrastructure-only failures are eligible for a preserved retry record.
- Automatic evaluation prohibits manual correction.
- Terminal status, ambiguity, package completeness, replay success, and geometry validation are reported separately.
- `volume_iou` is the principal overlap metric when Boolean computation succeeds; Boolean failure produces `volume_iou=null` and a separately reported `surface_only` diagnostic fallback.
- Package completeness follows conditional artifact rules and is not a substitute for algorithmic success.

## Observed evaluation summary

The frozen Gate 4 evaluation produced 27/30 terminal automatic successes, 26/27 supported-case automatic recoveries, 2/2 correct unsupported rejections, 27/27 geometry passes among validated cases, and 30/30 conditionally complete result packages. Twenty-five cases produced volume-IoU values and two used surface-only validation.

Authoritative result interpretation remains in [`logs/gate4/gate4_closure_report.md`](../logs/gate4/gate4_closure_report.md) and [`logs/gate4/gate4_statistics.json`](../logs/gate4/gate4_statistics.json).

## Known biases and limitations

- The sample is small and intentionally structured around the frozen operation scope.
- Most cases share a CadQuery generator and related modelling conventions.
- Exporter diversity is limited: only three source constructions were manually modelled in Fusion.
- The operation vocabulary excludes common industrial features and interactions.
- Development and held-out cases are not a probability sample of any industrial CAD population.
- Near-unity IoU values within this set do not define a universal acceptance threshold.
- External validity, robustness to other kernels/exporters, and recovery of original design intent remain unknown.

## Intended use

Use this benchmark to reproduce or audit the frozen Gate 0-4 claims, compare later methods under an explicitly versioned protocol, and expose structured failures. Do not use it to claim industrial prevalence, general CAD-history recovery, causal feature effects, or statistically calibrated population performance.
