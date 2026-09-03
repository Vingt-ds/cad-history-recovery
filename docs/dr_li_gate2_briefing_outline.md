# Dr. Li Gate 2 Briefing Outline

## Purpose

Prepare a 10--15 minute project update that demonstrates a reproducible prototype milestone, states the evidence boundary, and motivates the next bounded research question. This is a briefing outline, not evidence that a formal presentation has been requested or scheduled.

Recommended delivery length: 12 minutes plus questions. Prefer recorded or fixed replay evidence over a live Fusion demonstration.

## Slide 1 — Problem definition (1 minute)

**Title:** From history-free B-rep to a replayable CAD construction explanation

Opening statement:

> The prototype generates a deterministic, plausible, and replayable CAD construction sequence from a history-free STEP B-rep. It does not claim to recover the designer's unique original history.

State the current supported result narrowly: one simple profile followed by one New distance extrusion.

## Slide 2 — Why the problem is non-trivial (1 minute)

- A B-rep stores final geometry and topology, but not design intent or construction order.
- Multiple valid histories may explain the same solid.
- A useful result must be executable in CAD and geometrically checked, not merely assigned a feature label.

Use D-S01 and D-S09 only to illustrate that ambiguity can remain even when reconstruction succeeds.

## Slide 3 — Evidence-producing framework (2 minutes)

Show one compact pipeline:

```text
Frozen STEP B-rep
    -> canonical fact extraction
    -> feature hypotheses with reasons
    -> normalized sequence synthesis
    -> CadQuery candidate validation
    -> Fusion replay
    -> geometric and package audit
```

Emphasize that CadQuery validates candidates derived from B-rep facts; it does not search arbitrary programs to invent an explanation.

## Slide 4 — Experimental discipline (1.5 minutes)

- One frozen 30-case benchmark input set.
- Gate 2 development uses only the pre-labelled `D-S01`--`D-S10` subset.
- Held-out geometry is not used for rule or threshold development.
- Formal runs are non-overwriting and record source hashes, code commit, environment, logs, replay files, validation, and final status.
- Completeness and geometric success are evaluated separately.

Do not present the 30 inputs as 30 successful history recoveries; Gate 2's measured denominator is ten development single-extrusion cases.

## Slide 5 — Gate 2 measured outcome (2 minutes)

Present only the frozen formal-run results:

```text
10/10 automatic terminal success
10/10 frozen geometry-protocol pass
10/10 complete result packages
2 ambiguous accepted histories: D-S01 and D-S09
0 manual success, 0 failed, 0 unsupported
```

Evidence links:

- Formal run: `benchmark_results/gate2-formal-20260903-e93dc2f/`
- Verification: `benchmark_results/gate2-formal-20260903-e93dc2f/gate2_verification_report.json`
- Closure report: `logs/gate2/gate2_closure_report.md`
- Completion tag: `gate2-forward-path`

Do not convert 10/10 development performance into a statistical generalization claim.

## Slide 6 — Three representative cases (2 minutes)

Use fixed screenshots or a short recording:

1. **D-S04:** non-rectangular L profile, demonstrating that the pipeline is not limited to a box template.
2. **One offset or rotated case:** demonstrating fact-derived `inferred_brep` frame provenance without manual correction.
3. **D-S01 or D-S09:** demonstrating that the system reports multiple accepted explanations rather than hiding ambiguity.

For each case, show input B-rep, selected sequence, Fusion replay, and validation result. Avoid a live-demo dependency.

## Slide 7 — Failure honesty and current limits (1.5 minutes)

State explicitly:

- The benchmark is curated and source-biased; 10/10 does not establish arbitrary B-rep generalization.
- Current automatic inference excludes arcs, splines, mixed or multiple profiles, Add, pockets, holes, fillets, and chamfers.
- The recovered frame and operation order are normalized executable choices, not recovered designer intent.
- D-S01 and D-S09 remain ambiguous even though both pass replay and geometry validation.
- Earlier infrastructure failures are preserved rather than removed from the evidence history.

Preferred sentence:

> The system recovers a validated construction explanation within a frozen scope, not necessarily the original designer history.

## Slide 8 — Gate 3 research question (1.5 minutes)

Frame Gate 3 as a proposed test, not an achieved capability:

> Can the same evidence discipline recover one base New extrusion followed by one circular through-all Cut from a perforated final B-rep?

Proposed scope:

- one straight cylindrical void;
- two explicit, equal-radius, coaxial circular openings;
- openings on opposite planar base end faces;
- one circular Sketch on a semantic operation cap;
- one `cut + through_all` replay.

Explicit exclusions: blind, stepped, countersunk, threaded, multiple, patterned, or intersecting holes.

## Slide 9 — Gate 3 pre-check and decision point (1.5 minutes)

Report the pre-check honestly:

- `D-H01`--`D-H05` contain sufficient raw cylinder, circle, wire, and incidence facts.
- Existing Gate 2 extrusion inference does not directly recover the perforated base: the intended end-face pair is rejected, while unrelated side-face pairs create ambiguity.
- The current adjacency convention labels the hole rims `convex`, so concavity cannot yet be used as an accepted hard rule.
- Gate 3 therefore requires a coupled base-plus-hole hypothesis and validation of the complete New-plus-Cut reconstruction.

Close with the decision boundary:

> Proceed only with this single-through-hole design. If automatic recognition cannot satisfy the later frozen Gate 3 condition, retain automatic base recovery and use an audited manual JSON Cut as the planned fallback.

## Questions to invite

- Is a normalized executable construction explanation the appropriate project objective, or should the evaluation prioritize another notion of history plausibility?
- Is the proposed single-through-hole scope sufficient for the next prototype milestone?
- Which additional independent CAD source would be most valuable later as supplementary validation, without changing the main benchmark denominator?

Do not ask for approval of arbitrary B-rep recovery, and do not imply that supplementary validation has already been performed.
