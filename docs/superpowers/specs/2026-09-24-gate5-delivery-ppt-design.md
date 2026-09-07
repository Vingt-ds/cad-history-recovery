# Gate 5 Delivery Presentation Design

## Status and provenance

This document is the approved design decision record for the Gate 5 technical briefing. It freezes the presentation structure, claim boundaries, evidence mapping, speaker-note rules, visual system, and demonstration fallback policy before slide production begins.

The filename uses the planned delivery-package date, `2026-09-24`. The design was approved and recorded on `2026-09-07`; the date in the filename must not be interpreted as the authoring or Git commit date.

This specification does not create or approve a PowerPoint file. It does not modify the frozen Gate 0-4 algorithms, schemas, protocols, thresholds, benchmark, formal result packages, evaluation outcomes, or annotated baseline tag.

## Presentation identity and boundary

| Item | Frozen value |
| --- | --- |
| Presentation version | `gate5-delivery-ppt-design-v1` |
| Planned deck | `delivery_package/gate5-delivery-v1_20260924/slides/gate5_delivery_v1.pptx` |
| Language | English |
| Aspect ratio | 16:9 |
| Formal slides | 10 |
| Backup appendix slides | 3 |
| Total briefing time | 10-15 minutes, including slides, live demonstrations, transitions, and buffer |
| Narrative target | approximately 7 minutes |
| Demonstration target | approximately 5 minutes |
| Transition and recovery buffer | approximately 2 minutes |
| Research anchor | annotated tag `gate0-4-frozen-baseline-v1` at `c3e448525e9424383e847332f4d0afc1444e7380` |
| Delivery branch | `gate5-delivery` |

The presentation is an evidence-bounded technical briefing. It communicates what the frozen Gate 0-4 evidence supports, how that evidence was produced, how three representative cases expose the evidence chain, and where the verified capability ends. It is not a product pitch, a paper, a new experiment, or a claim of general CAD-history recovery.

## Narrative and timing contract

The formal narrative is:

```text
Research Question
        |
        v
Evidence-based Pipeline
        |
        v
Frozen Evaluation
        |
        v
Demonstration Evidence
        |
        v
Capability Boundary
```

Gate numbers may appear as provenance labels, but the deck must not use a chronological `Gate 0 -> Gate 1 -> ... -> Gate 5` structure. The scientific story is the relationship between the question, evidence, replay, validation, and bounded conclusion.

The planned timing is:

| Segment | Target |
| --- | ---: |
| Research question and scope | 1 minute |
| Evidence pipeline | 1.5-2 minutes |
| Benchmark boundary and frozen observations | 2 minutes |
| Demonstration contract and three cases | 5-6 minutes |
| Scope, limitation, and future question | 1 minute |
| Transitions and recovery buffer | 1-2 minutes |

If a live demonstration is replaced by backup media, the replacement remains inside the same total time. Backup media is not an additional presentation segment.

## Terminology contract

Use `construction class` consistently for the two frozen supported scopes:

- single-extrusion construction;
- base extrusion plus one straight through cylindrical cut construction.

Do not substitute `feature class`, `feature recognition`, or `operation recognition` when describing the research scope. `Operation` remains appropriate only when naming a sequence element such as `New Extrusion` or `Cut + through_all`.

Use these status meanings without compression:

- `supported`: a candidate exists inside the frozen Gate 2/3 construction language; this is not a uniqueness claim;
- `ambiguous=true`: multiple candidates satisfy the frozen acceptance contract, independently of terminal success or failure;
- `unsupported`: no hypothesis inside the frozen supported language is accepted, so replay is not attempted;
- executor failure: inference produced a candidate, but the frozen Fusion path did not produce trusted replay evidence;
- geometry failure: Fusion produced replay artifacts that the frozen route-specific validator did not accept.

## Formal slide specifications

### Slide 1 - Construction Explanations from History-Free B-rep

**Purpose:** establish the research object and its bounded scope before any result is shown.

**Frozen subtitle:** `A frozen research baseline for constrained executable reconstruction`

**Frozen claim:** The project studies whether final B-rep evidence can constrain plausible, replayable construction explanations within the two frozen construction classes.

**Visual structure:** a restrained title composition with one simplified history-free solid on the right and a short evidence path on the left: `Final B-rep -> Evidence -> Executable explanation`. The evidence-to-explanation link is dashed. No metric appears on the title slide.

**Required evidence:** the title and scope wording are grounded in `docs/gate0_4_research_baseline.md` and `docs/dr_li_gate0_4_technical_brief.md`. The solid may be an editable simplified rendering derived from a verified project case, but it must not imply a new or more complex construction class.

**Speaker notes:** state that STEP/B-rep retains final geometry and topology but normally loses the feature timeline and design intent. State that the goal is a plausible executable explanation, not guaranteed recovery of the unique original designer history.

**Forbidden wording:** `original history recovery`, `design intent recovery`, `general CAD reconstruction`, `arbitrary CAD`, or any success-rate headline.

**Target time:** 30-40 seconds.

### Slide 2 - Research Question and Scope

**Purpose:** state the precise research question and the two frozen construction classes.

**Frozen claim:** Final B-rep evidence may constrain plausible, executable construction explanations within two frozen construction classes.

**Visual structure:** one central question above two simple flat constructions. The first is `single extrusion`; the second is `base extrusion + straight through cylindrical cut`. A lower boundary line states `History-free STEP/B-rep input only` and `No unique-history claim`.

**Required evidence:** `docs/gate0_4_research_baseline.md`, especially the bounded hypothesis and current capability boundary; `docs/benchmark_v1_card.md` for supported-scope wording.

**Speaker notes:** explain that these are construction classes, not a general feature library. Mention that the second class is a coupled base-and-cut explanation, not a generic hole detector.

**Forbidden wording:** `two feature classes`, `hole recognition`, `recover the true sequence`, `industrial CAD`, or `universal construction recovery`.

**Target time:** 40-50 seconds.

### Slide 3 - Gate 0-4 Evidence Pipeline

**Purpose:** show how observable facts become testable explanations without presenting inference as direct historical truth.

**Frozen claim:** The pipeline separates observed B-rep facts from candidate hypotheses, then requires executable replay and geometry validation before accepting an explanation.

**Visual structure:** a single horizontal or stepped flow:

```text
History-free STEP
        -> Canonical B-rep facts
        -- constraints --> Candidate hypotheses
        -> Parametric sequence
        -> Fusion replay
        -> Route-specific validation
        -> Auditable result package
```

Solid connectors show data or artifact flow. The connector from facts to hypotheses is dashed and labelled `geometric and topological constraints`. All nodes are editable shapes; no model-architecture graphic is permitted.

**Required evidence:** `docs/gate0_4_research_baseline.md`; `docs/dr_li_gate0_4_technical_brief.md`; Gate 2 and Gate 3 closure evidence referenced through `config/gate0_4_baseline_manifest.json`.

**Speaker notes:** explain that CadQuery validates candidates rather than inventing arbitrary histories. Emphasize that replay and validation close the evidence loop, and that ambiguity, rejection, and failure remain explicit outcomes.

**Forbidden wording:** `B-rep directly yields history`, `end-to-end learned model`, `B-rep encoder`, `graph network`, `ranking model`, or any unimplemented architecture.

**Target time:** 70-90 seconds.

### Slide 4 - Benchmark and Evaluation Boundary

**Purpose:** establish why the measurements are auditable and what population they do not represent.

**Frozen claim:** One unchanged system was evaluated on a curated 30-case benchmark with development and frozen held-out roles, without post-freeze semantic tuning.

**Visual structure:** a four-step freeze sequence:

```text
Freeze benchmark and system
        -> Run development and held-out splits
        -> Seal raw evidence
        -> Evaluate outcomes
```

A compact composition band states `15 development + 15 held-out`, `27 CadQuery-generated + 3 Fusion manually modelled`, and `curated controlled benchmark`. Avoid a dashboard or confusion-matrix layout.

**Required evidence:** `docs/benchmark_v1_card.md`; `logs/gate4/gate4_closure_report.md`; `logs/gate4/gate4_statistics.json`.

**Speaker notes:** explain that the held-out split measures fixed-system performance on the curated held-out subset without post-freeze semantic tuning. Expected labels were unavailable to semantic inference and were used for statistics only after both formal runs were sealed. State that the benchmark is neither random nor representative of industrial CAD populations.

**Forbidden wording:** `blind test`, `previously unseen industrial data`, `representative benchmark`, `generalization proved`, or `independent dataset`.

**Target time:** 55-65 seconds.

### Slide 5 - Frozen Gate 4 Observations

**Purpose:** report the complete frozen result taxonomy without turning the slide into a single accuracy claim.

**Frozen claim:** The frozen evaluation produced complete packages for all 30 cases and geometry passes for all 27 cases with trusted replay evidence, while retaining one supported executor failure and two correct scope rejections.

**Visual structure:** two evidence layers rather than an ML benchmark dashboard.

The upper layer, `Evidence integrity`, contains:

- `30/30 complete result packages`;
- `27/27 validated geometry passes`.

The lower layer, `Observed outcomes`, contains:

- `27/30 terminal automatic successes`;
- `26/27 supported automatic recoveries`;
- `2/2 unsupported correct rejections`.

A small validation note states `25 volume-IoU results + 2 surface-only validations`. Green indicates verified pass states; neutral text carries denominators. No single metric may dominate more than the evidence-integrity layer.

**Required evidence:** `logs/gate4/gate4_statistics.json`; `logs/gate4/gate4_closure_report.md`; `docs/gate0_4_research_baseline.md`.

**Speaker notes:** explain that package completeness follows condition-dependent artifact rules and is not algorithmic success. Explain that the two surface-only cases retain `volume_iou=null` and are not represented as IoU results. State that there were zero manual corrections in the formal Gate 4 evaluation.

**Forbidden wording:** `30/30 recovery`, `100% success`, `accuracy`, `perfect reconstruction`, `surface-only equals IoU`, `robustness`, or causal explanations for success.

**Target time:** 60-70 seconds.

### Slide 6 - Demonstration Evidence Contract

**Purpose:** prevent live and backup demonstrations from being mistaken for new formal evaluation.

**Frozen claim:** `Demonstration ≠ Evaluation`

**Visual structure:** a clear two-column contrast. `Frozen evaluation` points to sealed Gate 4 artifacts and fixed statistics. `Gate 5 demonstration` points to development-only reproduction and read-only visualization. A shared footer states `No algorithm changes, threshold tuning, benchmark updates, or result-count updates`.

The following metadata appears verbatim for D-S04 and D-H01:

```text
evidence_role = demonstration_only
formal_evaluation = false
source_split = development
baseline_tag = gate0-4-frozen-baseline-v1
```

For D-S01, show `source_mode = sealed_artifact_only` instead of suggesting a fresh demo run.

**Required evidence:** `docs/gate5_demo_runbook.md`; `docs/gate5_reproduction_guide.md`; `docs/gate5_media_index.md`.

**Speaker notes:** state that D-S04 and D-H01 exercise the frozen inference, Fusion replay, and validator through a delivery wrapper. State that D-S01 is read-only evidence from its sealed Gate 4 development package and is not rerun.

**Forbidden wording:** `new evaluation`, `new result`, `updated benchmark`, `demo success rate`, `fresh D-S01 inference`, or `manual correction`.

**Target time:** 35-45 seconds.

### Slide 7 - D-S04 Single Extrusion

**Purpose:** demonstrate the complete delivery path on a non-rectangular development single extrusion.

**Frozen claim:** This development case produced a plausible single-extrusion sequence that replayed and passed the frozen validator.

**Visual structure:** use a simple four-stage evidence strip: `STEP input -> inferred sequence -> Fusion replay -> geometry PASS`. The full verified fallback screenshot may occupy the right half or be used full-frame during a backup transition. Complexity of the solid is not a claim and must not be visually exaggerated.

**Required figure:** `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_01_single_extrusion_v1.png`. Live artifacts are those created under the ignored `runs/gate5/<run-id>/` directory by the fixed D-S04 demonstration procedure.

**Required evidence:** `docs/gate5_demo_runbook.md`; `docs/gate5_reproduction_guide.md`; the verified D-S04 demo manifest, inferred sequence, replay F3D/STEP, and validation metrics produced before final deck assembly.

**Speaker notes:** show the sequence, Fusion result, and validation outcome. State that the case is from the development split and has `evidence_role=demonstration_only` and `formal_evaluation=false`. Do not present zero error in this one demonstration as a universal tolerance result.

**Forbidden wording:** `the system reconstructs CAD history`, `unique history`, `complex geometry capability`, `general single-extrusion recovery`, or any benchmark-denominator update.

**Target time:** approximately 2 minutes including live execution or its backup excerpt.

### Slide 8 - D-H01 Base and Straight Through Cut

**Purpose:** demonstrate the coupled base-extrusion and straight through-cut route.

**Frozen claim:** This development case produced a coupled `New Extrusion + Cut through_all` explanation that replayed and passed the frozen route-specific geometry checks.

**Visual structure:** show the observed circular-opening and cylindrical-face evidence at left, the two-operation sequence in the centre, and the Fusion replay plus three pass states at right: `geometry`, `base geometry`, and `hole feature match`. The title must remain construction-oriented rather than classification-oriented.

**Required figure:** `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_02_through_hole_v1.png`.

**Required evidence:** `docs/gate5_demo_runbook.md`; the verified D-H01 candidate evidence, inferred sequence, replay F3D/STEP, and route-specific validation metrics produced before final deck assembly.

**Speaker notes:** explain that the base and cut are evaluated as one coupled hypothesis. Show `New Extrusion` followed by `Cut + through_all`, then the replay and validation results. Explicitly restrict the observation to one straight cylindrical through cut with the frozen evidence requirements.

**Forbidden wording:** `hole recognition`, `general hole recovery`, `all through-holes`, or support for blind, stepped, tapered, multiple, intersecting, threaded, counterbored, countersunk, or patterned holes.

**Target time:** 2-2.5 minutes including live execution or its backup excerpt.

### Slide 9 - D-S01 Sealed Ambiguity Evidence

**Purpose:** show that the system can retain non-uniqueness evidence without rerunning or editing a formal result.

**Frozen claim:** Three candidate hypotheses satisfied the frozen pre-Fusion acceptance contract. The canonical selection replayed successfully, while the system retained `ambiguous=true`.

**Visual structure:** show three small, muted hypothesis markers labelled `C1`, `C2`, and `C3`. Highlight only the canonical selection and connect only that candidate to `Fusion replay -> geometry PASS`. Place `ambiguous=true` in yellow beside the candidate set. Do not render three large green `Accepted` panels.

**Required figure:** `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_03_ambiguity_v1.png`.

**Required evidence:** read-only sealed files under `benchmark_results/gate4-development-formal-20260905/cases/D-S01/`, specifically `analysis/candidates.json`, `sequence/inferred_sequence.json`, `replay/replay_log.json`, `validation/validation_metrics.json`, and `final_status.json`; the development-run `seal.json`; `docs/gate5_demo_runbook.md`.

**Speaker notes:** first state `source_mode=sealed_artifact_only`. Explain that 3 of 15 candidate hypotheses have `status=accepted` under the frozen pre-Fusion contract. The selected candidate is `extrusion-face-002-face-003`. Only the canonical selected sequence has formal Fusion replay evidence in this result package. Explain that `ambiguous=true` neither means failure nor proves enumeration of all possible designer histories.

**Forbidden wording:** `three executable histories`, `three true histories`, `all possible histories`, `the system discovers multiple histories`, `fundamental underdetermination`, `fresh inference`, or `JSON correction`.

**Target time:** 1-1.5 minutes.

### Slide 10 - Validated Scope and Open Question

**Purpose:** close with the strongest defensible conclusion and the next unresolved question without implying that Gate 6 has started.

**Frozen claim:** The evidence supports deterministic, auditable reconstruction within the tested construction classes and environment. It does not establish unique-history recovery or general industrial validity.

**Visual structure:** a balanced two-column close. `Validated here` contains constrained canonical facts, candidate evidence, sequence synthesis, Fusion replay, route-specific validation, and explicit failure/status semantics. `Not established` contains unique designer history, arbitrary operation vocabulary and references, industrial generalization, and universal thresholds.

Include one restrained boundary callout:

```text
T-S07: executor capability boundary
unsupported_absolute_frame
```

The final future-work sentence is exactly:

> Future work will investigate controlled multi-operation ordering and history ambiguity.

**Required evidence:** `docs/gate0_4_research_baseline.md`; `logs/gate4/gate4_closure_report.md`; `docs/benchmark_v1_card.md`; `docs/dr_li_gate0_4_technical_brief.md`.

**Speaker notes:** distinguish the preserved T-S07 Fusion executor limitation from semantic unsupported cases and from demonstrated history ambiguity. Present Gate 6 only as a future research direction.

**Forbidden wording:** `failed case proves ambiguity`, `general CAD-history recovery`, `industrial robustness`, `Gate 6 benchmark`, `operation pair`, `Add/Cut experiment`, or any proposed Gate 6 algorithm.

**Target time:** 50-60 seconds.

## Appendix specifications

Appendix slides are not part of the planned narrative and are opened only to answer a question. Their presence does not extend the formal 10-15 minute contract.

### Appendix 1 - Implementation Verification

**Purpose:** provide software and audit verification details without presenting test volume as a scientific result.

**Content:** `311 tests passed` from the approved Checkpoint A verification; Gate 0, Gate 1, Gate 2, Gate 3, and Gate 4 verifier PASS states; baseline annotated-tag verification PASS; Gate 5 delivery-package preflight PASS; baseline tag and candidate delivery commit identifiers.

**Evidence rule:** the final slide must be regenerated from a fresh pre-delivery verification record. If the fresh test count or candidate commit changes, update this appendix and its speaker note; do not silently preserve `311` as a decorative number. Test count remains labelled `implementation verification`, not `research result`.

**Visual structure:** a compact verification list with one evidence-path footer, not a dashboard and not a wall of command output.

### Appendix 2 - Status and Validation Semantics

**Purpose:** answer why `ambiguous=true` is not failure and why package completeness is not recovery success.

**Content:** the frozen definitions of `supported`, `ambiguous=true`, `unsupported`, executor failure, and geometry failure. Include a separate three-part distinction:

```text
terminal outcome != ambiguity flag != package completeness
```

**Evidence:** `README.md`; `docs/gate5_reproduction_guide.md`; `docs/gate0_4_research_baseline.md`; `logs/gate4/gate4_closure_report.md`.

### Appendix 3 - Evidence References

**Purpose:** answer `Where can I verify this?`

**Content:** concise repository-relative references to the baseline manifest, research baseline, benchmark card, Gate 4 closure report, Gate 4 statistics, demo runbook, media index, and sealed D-S01 artifact directory. Include the baseline tag name and peeled commit. Do not paste file hashes, result packages, or long URLs onto the slide.

**Evidence:** `config/gate0_4_baseline_manifest.json` and the referenced repository files.

## Speaker-note contract

- Notes are written in English as concise speaking prompts, not as an essay or a verbatim transcript.
- Each formal slide begins with its frozen claim and ends with a transition to the next evidence question.
- Notes carry qualifications that are too detailed for the slide, including the held-out label-release sequence, condition-dependent package completeness, surface-only validation, and the D-S01 replay boundary.
- All numerical statements identify their denominator. No live-demo output may create or update a benchmark statistic.
- Live-demo cues use `[LIVE DEMO]`; fallback cues use `[BACKUP: <asset>]`. A fallback cue replaces the live segment and does not add a second demonstration.
- Evidence paths may appear in the note section under `Evidence`, but note text must not imply that a source was opened live unless it actually will be opened.
- Notes must not contain unapproved Gate 6 hypotheses, operation pairs, benchmark designs, or algorithms.
- A claim that cannot be traced to the evidence map is removed rather than softened into vague language.

## Visual style contract

The deck uses a restrained technical-research aesthetic consistent with the verified Gate 5 screenshots.

- Canvas: 16:9 widescreen.
- Background: dark graphite, approximately `#0B121A`.
- Primary text: cool off-white, approximately `#E8EEF5`.
- Secondary text: blue-grey, approximately `#94A9BC`.
- Structure and data-flow accent: cyan, approximately `#38C9FF`.
- Verified pass accent: green, approximately `#57DE9B`.
- Ambiguity and caution accent: yellow, approximately `#FFC857`.
- Panel and hairline tones may use `#112230`, `#182C3B`, and `#28506B`.
- Use one presentation-safe sans-serif family such as Aptos for prose and a monospace family such as Consolas only for field names, status values, commands, and short identifiers.
- Titles are direct statements, not slogans. No title ends with a period.
- Use flat compositions with a small number of aligned text groups. Avoid repeated UI cards, dashboard chrome, decorative gradients, 3D effects, and machine-learning visual language.
- All conceptual flows and tables are editable native PowerPoint shapes. Existing PNGs are evidence images and remain raster assets.
- Use each of the three verified demo screenshots only on its corresponding case slide. Do not reuse a screenshot as a background or decorative motif.
- Do not generate synthetic CAD evidence, decorative AI imagery, logos, or unverified screenshots.
- The facts-to-hypotheses relationship is always dashed; solid arrows are reserved for artifact or execution flow.
- Green is reserved for verified pass states. Yellow is reserved for ambiguity or caution. Failure and unsupported states use neutral or muted red only when they must be distinguished, never for spectacle.

## Global forbidden claims

The deck and speaker notes must never claim:

- general, arbitrary, industrial, or population-level CAD-history recovery;
- recovery of the unique original designer history or design intent;
- 30/30 automatic recovery, 100% recovery, or perfect reconstruction;
- that the controlled benchmark proves generalization or causal success factors;
- that all D-S01 accepted candidates are independently replayed executable histories;
- that the D-S01 candidates enumerate all possible histories;
- that `T-S07` is semantically unsupported, a geometry failure, or evidence of history ambiguity;
- that surface-only validation is equivalent to a computed volume IoU;
- that package completeness is algorithmic success;
- that D-H01 demonstrates general hole recognition;
- that Gate 5 creates new scientific results;
- that Gate 6 operation pairs, benchmark design, or implementation have been selected.

Terms such as `accuracy`, `improved`, `state of the art`, `robust`, and `generalizes` require explicit evidence and are excluded from this deck.

## Evidence map

| Slide | Primary authoritative source | Supporting or visual source |
| --- | --- | --- |
| 1 | `docs/gate0_4_research_baseline.md` | `docs/dr_li_gate0_4_technical_brief.md` |
| 2 | `docs/gate0_4_research_baseline.md` | `docs/benchmark_v1_card.md` |
| 3 | `docs/gate0_4_research_baseline.md` | `config/gate0_4_baseline_manifest.json` |
| 4 | `docs/benchmark_v1_card.md` | `logs/gate4/gate4_closure_report.md` |
| 5 | `logs/gate4/gate4_statistics.json` | `logs/gate4/gate4_closure_report.md` |
| 6 | `docs/gate5_demo_runbook.md` | `docs/gate5_reproduction_guide.md` |
| 7 | verified D-S04 demonstration package | `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_01_single_extrusion_v1.png` |
| 8 | verified D-H01 demonstration package | `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_02_through_hole_v1.png` |
| 9 | `benchmark_results/gate4-development-formal-20260905/cases/D-S01/` and its seal | `delivery_package/gate5-delivery-v1_20260924/screenshots/demo_03_ambiguity_v1.png` |
| 10 | `docs/gate0_4_research_baseline.md` | `docs/benchmark_v1_card.md` and `logs/gate4/gate4_closure_report.md` |
| Appendix 1 | fresh Checkpoint B verification record | baseline verifier and package preflight outputs |
| Appendix 2 | `docs/gate5_reproduction_guide.md` | `README.md` and Gate 4 closure evidence |
| Appendix 3 | `config/gate0_4_baseline_manifest.json` | the repository paths listed on the slide |

Local delivery assets are presentation aids and are not authoritative sources for Gate 0-4 scientific statistics. If a screenshot conflicts with a sealed artifact or repository document, the screenshot is rejected and regenerated from the authoritative source.

## Demonstration fallback policy

The live sequence is D-S04, then D-H01, then D-S01 sealed-artifact explanation. D-S01 is never a fresh inference demonstration.

Before presenting:

1. open all three screenshots and MP4 files;
2. verify the D-S04 and D-H01 prepared run directories and the D-S01 seal;
3. confirm Fusion is installed, launched, and signed in;
4. confirm no stale `runs/gate5_active_request.json` exists;
5. rehearse switching from the live view to each matching backup asset without editing files.

If Fusion or a live command is unstable, stop the live path and switch directly to the matching asset:

- D-S04: `videos/demo_01_single_extrusion_v1.mp4` or `screenshots/demo_01_single_extrusion_v1.png`;
- D-H01: `videos/demo_02_through_hole_v1.mp4` or `screenshots/demo_02_through_hole_v1.png`;
- D-S01: `videos/demo_03_ambiguity_v1.mp4` or `screenshots/demo_03_ambiguity_v1.png`.

Do not edit code, JSON, parameters, inputs, thresholds, or artifacts during the presentation. Do not troubleshoot Fusion live. State that the backup is a prepared technical evidence view, continue the same claim, and preserve the total briefing time.

## Production and review gate

PPT production may begin only after this design record is committed and approved. The implementation must:

1. create exactly 10 formal slides and 3 appendix slides;
2. add English speaker notes that follow the timing and claim contracts;
3. use only the mapped evidence and the three verified case screenshots;
4. render every slide and inspect layout, text fit, contrast, connector semantics, numerical denominators, and screenshot legibility;
5. audit all slide and note text against the global forbidden-claim list;
6. rehearse the slides and demonstrations together inside the 10-15 minute limit;
7. place the reviewed deck in the local delivery package only after it passes visual and claim review;
8. regenerate and verify the final delivery manifest and `SHA256SUMS.txt` after the PPT is present.

Creating this design record does not authorize merging `gate5-delivery`, creating `gate5-delivery-v1`, moving `gate0-4-frozen-baseline-v1`, or pushing any branch or tag.

## Acceptance criteria for this specification

This design specification is complete when:

- it is the only tracked change in its design commit;
- it contains the approved 10-slide and 3-appendix structure;
- every formal slide has a purpose, frozen claim, visual structure, evidence source, speaker-note boundary, forbidden wording, and timing target;
- `construction class` is used consistently for the frozen supported scopes;
- the facts-to-hypotheses relationship is explicitly non-causal and dashed;
- D-S01 remains `sealed_artifact_only`, and only the canonical selection is connected to formal Fusion replay;
- T-S07 remains an executor capability boundary;
- the filename's planned delivery date is distinguished from the actual design-record date;
- no PPT, local tag, merge, push, benchmark rerun, or Gate 6 implementation is created as part of this commit.
