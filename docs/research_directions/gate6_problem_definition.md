# Gate 6 Problem Definition

## Status and purpose

This document defines the scientific question and evidence boundary for Gate 6. It does not select operation types, define a benchmark, set acceptance thresholds, or authorize implementation.

Gate 6 extends the research question beyond the Gate 3 setting of one base construction followed by one modifier. Its controlled object is an oracle-held frozen base followed by exactly two modifier operations selected from a small, explicitly declared candidate language with deterministic replay semantics.

The word *frozen* describes control of benchmark generation. It does not mean that the base geometry is supplied to inference.

## 1. Existing evidence from Gate 0-4

Gate 0-4 established that, for the frozen feature classes and execution environment, geometric and topological facts from a history-free STEP/B-rep can constrain plausible construction explanations that are synthesized, replayed, and geometrically validated.

The closed baseline provides evidence for:

- a bounded single-extrusion construction;
- one bounded base extrusion coupled with one straight through cylindrical cut;
- deterministic fact extraction, candidate formation, sequence synthesis, Fusion replay, and route-specific validation;
- explicit ambiguity, rejection, executor-failure, and packaging semantics; and
- frozen held-out evaluation without post-freeze semantic tuning.

It does not provide evidence for interaction between two modifier operations, general operation-order recovery, unique recovery of the designer's original history, or history reconstruction outside the frozen candidate classes.

## 2. Unresolved scientific gap

Gate 3 already covers a base-plus-one-modifier construction. Merely adding another named feature would be a scale extension, not by itself a new research contribution.

The unresolved question is whether evidence remaining in a final B-rep can distinguish alternative executable orderings when two modifiers interact, and whether some semantically distinct histories are observationally indistinguishable even after independent replay and validation.

This requires both kinds of controlled comparison:

- **Order-sensitive, non-commutative pairs:** both `A -> B` and `B -> A` are executable, but their final B-reps are not observationally equivalent.
- **Commutative or otherwise equivalent pairs:** two semantically distinct executable sequences independently reconstruct observationally equivalent final B-reps.

Without both classes, an ordering failure cannot be separated cleanly from genuine non-identifiability.

## 3. Research question

> Given only a final history-free B-rep generated from an oracle-held frozen base and two controlled modifier operations, can geometric and topological evidence provide sufficient constraints to distinguish executable orderings within a frozen candidate language, and when do semantically distinct executable sequences remain observationally equivalent in the final B-rep?

This asks about identifiability within a declared candidate language. It does not ask whether the unique original designer history can be recovered from arbitrary CAD models.

## 4. Falsifiable hypotheses

### H1: Ordering identifiability within the candidate language

For a controlled order-sensitive pair, the final B-rep contains sufficient geometric or topological constraints to reject non-equivalent executable orderings and retain the ordering explanation consistent with the observed final solid.

H1 is not supported if a frozen method cannot distinguish the verified order-sensitive alternatives using only the allowed final-B-rep evidence. Such a result is initially a method limitation, not proof that the histories are fundamentally indistinguishable.

### H2: Demonstrable underdetermination

For a controlled equivalent pair, at least two semantically distinct sequences can independently replay from fresh documents and each reconstruct a final B-rep that is observationally equivalent to the same target under a predeclared validation protocol.

H2 is not supported by multiple unexecuted candidates, JSON differences, a search failure, or geometric similarity without independent replay and validation.

### H3: Failure attribution is separable from information insufficiency

If an oracle history exists within the frozen candidate language but the method does not recover a valid explanation, the result is classified as a method limitation unless evidence independently establishes an executor, infrastructure, or protocol failure. It is not classified as underdetermination.

H3 is violated if algorithm failure, executor failure, scope rejection, or unverified candidate multiplicity is reported as demonstrated history ambiguity.

## 5. Controlled problem formulation

### 5.1 Inference input

Inference receives only:

- the final history-free B-rep and content-derived facts permitted by the later frozen protocol.

Inference must not receive or derive decisions from:

- the oracle base B-rep;
- generating histories or operation order;
- intermediate solids;
- oracle parameters or expected outcomes;
- case identifiers, filenames, directory names, or labels; or
- benchmark metadata that encodes the generating class.

The frozen base geometry, generating sequence, parameters, intermediate states, and expected outcomes are oracle artifacts used only for benchmark construction, evaluation, and sealed post-hoc analysis. They are never inference inputs.

### 5.2 Candidate language

The candidate language must be small, explicit, and frozen before formal evaluation. Its base-construction language must be declared and bounded, and every explanation contains exactly two modifier operations selected from a declared subset with deterministic replay semantics. This document does not expand or otherwise select the base-construction language.

This definition does not yet select modifier types. Selection requires a separate operation-pair design review based on evidential value, replay stability, and the ability to construct both order-sensitive and equivalent controls.

### 5.3 Evaluation object

The evaluation object is a complete executable construction explanation, including the reconstructed base explanation and both ordered modifiers. The oracle-held base is a controlled generative factor, not a known starting state provided to the method.

## 6. Evidence contract

A candidate sequence is not a valid explanation unless it independently reconstructs a verified final B-rep. At minimum, each claimed explanation must be:

1. valid under the frozen Gate 6 schema and candidate language;
2. replayed from a fresh document without manual geometric correction or shared hidden state;
3. executable under the declared deterministic replay semantics;
4. preserved with its replay output and structured execution evidence; and
5. validated against the same target B-rep under a protocol frozen before evaluation.

Observational equivalence must be determined from predeclared geometric and topological observables. It must not be inferred from matching JSON, operation names, a single one-way distance, or one scalar metric alone.

Claims must distinguish constraints extracted directly from the target B-rep before replay from alternatives eliminated only by replay validation. If ordering is resolved only through exhaustive replay, the result supports distinguishability within the frozen candidate language, but not a stronger claim that topology alone directly reveals the order.

Demonstrated underdetermination requires all of the following:

- at least two semantically distinct candidate sequences;
- independent successful replay of every sequence;
- validation of every replay against the same target B-rep; and
- observational equivalence under the same frozen protocol.

## 7. Semantic-distinctness definition

Semantically distinct sequences differ, under the declared schema, in at least one of:

- modifier operation type;
- modifier operation order; or
- explicit construction parameters that change the construction explanation.

Differences caused only by field ordering, identifier names, serialization, equivalent coordinate notation, kernel entity numbering, or other representation-level variation after canonicalization do not establish semantic distinctness.

Parameter differences count only when they remain distinct after the schema's canonicalization and equivalence rules. This prevents duplicate encodings of one construction from being misreported as multiple histories.

## 8. Failure-separation contract

Gate 6 results must keep the following outcomes separate:

- **Method limitation:** an oracle-valid explanation is in scope, but the inference or search method does not recover it.
- **Executor limitation:** a schema-valid candidate cannot be replayed because of a demonstrated CAD-executor capability boundary.
- **Infrastructure or protocol failure:** execution or evidence production is invalidated by an allowed infrastructure failure or a violated experimental contract.
- **Scope rejection:** the observed case cannot be expressed in the frozen candidate language and is rejected without being treated as an algorithmic success or ambiguity result.
- **Unresolved candidate ambiguity:** multiple candidates are proposed but the independent replay-and-equivalence contract has not been satisfied.
- **Demonstrated underdetermination:** at least two semantically distinct sequences satisfy the complete evidence contract for the same target.

These categories are mutually reportable but must not be collapsed into a single failure or ambiguity count. In particular, failure to find a history is not evidence that no identifiable history exists.

## 9. Minimum falsifiable pre-check

Before benchmark freezing or automatic inference development, the proposed operation subset must support an oracle-only construction pre-check containing at least:

1. one verified order-sensitive pair for which both `A -> B` and `B -> A` replay successfully and produce non-equivalent final B-reps; and
2. one verified equivalent pair for which two semantically distinct sequences replay successfully and produce observationally equivalent final B-reps.

For every pre-check pair, the evidence must include:

- schema-valid sequences and explicit oracle annotations;
- replay from fresh documents without manual geometric correction;
- preserved intermediate and final oracle artifacts for evaluation use only;
- deterministic replay evidence; and
- geometry and topology validation results under the declared pre-check protocol.

Failure to construct a proposed pair falsifies the suitability of that operation subset or experimental operationalization. It does not prove that the broader scientific question is nonexistent.

## 10. Decision criteria before implementation

No automatic inference implementation is authorized until all of the following are reviewed and accepted:

1. the minimum pre-check contains at least one verified order-sensitive pair and one verified equivalent pair;
2. both classes satisfy schema legality, fresh-document deterministic replay, geometry validation, and explicit oracle annotation;
3. the inference/oracle firewall is testable and excludes base geometry, histories, parameters, labels, identifiers, filenames, and directory semantics from inference;
4. the candidate language and operation subset are explicitly bounded;
5. the observational-equivalence protocol is defined before results are observed; and
6. the subsequent benchmark design states how method limitation, executor limitation, protocol failure, scope rejection, unresolved candidate ambiguity, and demonstrated underdetermination will be reported separately.

If these conditions are not met, Gate 6 pauses at experimental design. No feature implementation is justified by this document alone.

## 11. Non-goals

Gate 6 does not currently claim or authorize:

- arbitrary multi-feature or industrial CAD-history recovery;
- unique recovery of original design intent;
- general feature-graph reconstruction;
- fillet, chamfer, pattern, shell, revolve, sweep, loft, or any other undeclared operation family;
- learning-based candidate ranking;
- a benchmark size, success-rate target, geometry threshold, or formal-run policy;
- modification of Gate 0-4 protocols, evidence, Baseline Pack, or tag; or
- use of oracle artifacts as inference inputs.

## 12. Next review gate

The next authorized activity is an operation-pair selection and benchmark-design review. That review may propose a minimal modifier subset and oracle pre-check protocol, but it must not begin automatic inference implementation until the decision criteria above are satisfied.

Gate 5 is the documentation, demonstration, and submission milestone for the closed Gate 0-4 system. Its delivery work remains separate from this scientific Gate 6 and cannot alter the Gate 6 evidence contract.
