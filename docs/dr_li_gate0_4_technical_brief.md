# Dr. Li Gate 0-4 Technical Brief

## Purpose

This is a speaking outline for a 10-15 minute technical update. It is not a slide deck, paper draft, or indication that a presentation has been requested.

## One-sentence claim

We built and froze an auditable pipeline that generates plausible, replayable CAD construction sequences from history-free B-rep models for two constrained feature classes, then evaluated the unchanged system on a 30-case controlled benchmark with a sealed held-out split.

## Suggested 12-minute structure

### 1. Problem and research distinction — 1.5 minutes

- STEP/B-rep preserves final geometry and topology but normally loses the feature timeline and design intent.
- The objective is not to recover a guaranteed unique original history; it is to generate a plausible, executable construction explanation constrained by observable evidence.

### 2. Evidence-producing framework — 1.5 minutes

```text
B-rep -> canonical facts -> feature hypotheses -> sequence synthesis
      -> Fusion replay -> geometry validation -> auditable result package
```

- Keep facts separate from inference.
- Use CadQuery for candidate validation, not arbitrary history search.
- Preserve ambiguity, rejection, and failure independently.

### 3. Gate progression — 2 minutes

- Gate 0: verified the Fusion/external-Python execution and STEP-inspection boundary.
- Gate 1: froze 30 inputs, replay semantics, and validation foundations.
- Gate 2: recovered ten development single extrusions.
- Gate 3: recovered five development base-plus-through-hole constructions using a coupled base-and-cut hypothesis.
- Gate 4: froze one evaluation commit, ran both formal splits, sealed raw output, and only then used expected labels for statistics.

### 4. Frozen results — 2 minutes

Report the denominators exactly:

- 27/30 terminal automatic successes;
- 26/27 supported-case automatic recoveries;
- 2/2 unsupported correct rejections;
- 27/27 geometry passes among validated cases;
- 30/30 conditionally complete packages;
- 25 volume-IoU results and two separately reported surface-only validations;
- zero manual corrections in the formal Gate 4 evaluation.

Do not compress these into “30/30 recovery success.”

### 5. Three representative cases — 2 minutes

1. `T-S01`: a non-rectangular single extrusion demonstrating profile and frame recovery outside a box-only example.
2. `T-H03`: a YZ-oriented base plus straight through-hole reconstruction demonstrating the coupled `New Extrusion + Cut through_all` explanation.
3. `T-S07`: a supported case whose inference reached replay but the Fusion executor rejected the absolute RY45 frame with `unsupported_absolute_frame`. It was preserved without retry or relabelling.

### 6. Scientific boundary and next question — 2 minutes

- The current evidence supports deterministic recovery for the tested constrained classes and environment.
- It does not establish unique designer-history recovery, industrial generalization, arbitrary reference handling, or support for common advanced features.
- The next question should be tested separately: how can topology and geometry constrain controlled multi-operation histories and distinguish genuinely equivalent executable sequences?
- That is a future hypothesis, not a conclusion from the current benchmark.

### 7. Close — 1 minute

The main deliverable is not only a working prototype. It is a reproducible research baseline with fixed inputs, explicit scope, label-isolated evaluation, immutable raw evidence, structured failure semantics, and machine-verifiable references.

## Likely questions and bounded answers

### “Did the system recover the original CAD history?”

No uniqueness claim is made. It recovered a plausible parametric construction that replayed and matched the reference under the frozen validation protocol.

### “How representative are 30 cases?”

They are curated controls for mechanism validation, not a random industrial sample. External validity requires a separate, more diverse benchmark.

### “Why did `T-S07` fail?”

The semantic pipeline produced a candidate, but the frozen Fusion executor did not support that absolute frame. This is an executor boundary, not evidence that the history is fundamentally ambiguous.

### “Are the two surface-only passes equivalent to IoU validation?”

No. Boolean overlap failed for those two cases, so they retain `volume_iou=null` and are counted separately as surface-only diagnostic validation.

### “Why is Gate 4 still a pass with one supported failure?”

Gate 4 tested frozen evaluation integrity, not a minimum held-out success-rate target. The failure is part of the measured result; changing the algorithm after observing it would invalidate the held-out experiment.

## Prohibited overclaims

Do not claim:

- 30/30 automatic recovery;
- general or industrial CAD-history recovery;
- recovery of unique original design intent;
- that the benchmark proves generalization or causal success factors;
- that surface-only validation is equivalent to volume IoU;
- that an algorithm or executor failure proves fundamental history underdetermination.

## Evidence links

- Research interpretation: [`docs/gate0_4_research_baseline.md`](gate0_4_research_baseline.md)
- Benchmark card: [`docs/benchmark_v1_card.md`](benchmark_v1_card.md)
- Gate 4 closure: [`logs/gate4/gate4_closure_report.md`](../logs/gate4/gate4_closure_report.md)
- Gate 4 verification: [`logs/gate4/gate4_verification_report.json`](../logs/gate4/gate4_verification_report.json)
- Baseline manifest: [`config/gate0_4_baseline_manifest.json`](../config/gate0_4_baseline_manifest.json)
