# Gate 0-4 Research Baseline Pack Design

## Status

Approved design decision record for the Gate 0-4 Research Baseline Pack. This document defines packaging and audit behavior only. It does not reopen, rerun, reinterpret, or modify any Gate 0-4 experiment, benchmark input, acceptance rule, schema, routing rule, validation protocol, result package, or terminal outcome.

## Objective

Create one minimal, stable, machine-verifiable entry point for the already closed Gate 0-4 technical evidence and its research interpretation. The baseline must remain recoverable after `main` advances, without copying existing benchmark inputs or result packages and without implying a public software release or general CAD-history recovery.

The final local and remote anchor is an annotated Git tag named `gate0-4-frozen-baseline-v1`. No GitHub Release or downloadable release asset is created.

## Non-goals

The Baseline Pack does not:

- change the frozen Gate 4 evaluation commit or rerun held-out evaluation;
- replace any existing Gate closure report;
- create a second benchmark manifest, result tree, or environment snapshot;
- introduce a Gate 5 research question, feature, benchmark, algorithm, or experiment;
- claim statistical representativeness, industrial generalization, causal success factors, unique original-history recovery, or universal thresholds;
- treat the preserved `T-S07` Fusion executor limitation as evidence of multi-feature ambiguity or fundamental underdetermination.

## Git object model

Three existing or future Git objects have distinct meanings:

1. Gate 4 evaluation commit `3d04273301cdacb8936707164f492427aab3273c` is the evaluation truth anchor. It identifies the algorithm, routing policy, semantic inventory, and validation protocol used for the frozen development and held-out runs.
2. Technical baseline commit `aafd082ccb296584364227ebc9203e44c7d13832` is the source of the integrated Gate 0-4 code, evidence, closure records, and README state before baseline packaging.
3. Baseline Pack commit `P` contains the manifest, verifier, tests, interpretation documents, and README entry. The annotated tag points to `P`.

The design specification is committed first as a separate design commit `D`, followed by implementation commit `P`. Both commits are descendants of the technical baseline, but `technical_baseline_commit` remains `aafd082ccb296584364227ebc9203e44c7d13832` because the design record is not part of the evaluated technical system.

The manifest must not contain the SHA of `P`. Such a value would be self-referential because changing the manifest changes the commit. Instead it records:

```json
{
  "baseline_manifest_schema": "gate0-4-baseline-manifest-0.1",
  "baseline_id": "gate0-4-frozen-baseline-v1",
  "tag_name": "gate0-4-frozen-baseline-v1",
  "tag_target_binding": "containing_git_commit",
  "technical_baseline_commit": "aafd082ccb296584364227ebc9203e44c7d13832",
  "gate4_evaluation_commit": "3d04273301cdacb8936707164f492427aab3273c"
}
```

The verifier resolves `containing_git_commit` from `HEAD` before tag creation and from the peeled tag target after tag creation.

## Baseline Pack files

The cumulative tracked diff from the technical baseline through `P` is limited to these eight paths:

```text
README.md
config/gate0_4_baseline_manifest.json
tools/verify_gate0_4_baseline.py
tests/test_baseline_verifier.py
docs/gate0_4_research_baseline.md
docs/benchmark_v1_card.md
docs/dr_li_gate0_4_technical_brief.md
docs/superpowers/specs/2026-09-06-gate0-4-research-baseline-pack-design.md
```

No file under `benchmarks/inputs/` or `benchmark_results/` may be added, copied, removed, or modified. No existing protocol, source module, replay script, result, report, or closure document may be modified.

### Manifest

`config/gate0_4_baseline_manifest.json` is a canonical JSON index. It answers only where authoritative evidence is stored, which Git object owns it, which role it serves, and which SHA-256 protects it. It does not restate results or replace closure reports.

The manifest contains these sections:

- `benchmark_artifacts`: the frozen case matrix, benchmark manifest, and benchmark freeze lock;
- `frozen_protocols`: Gate 2 and Gate 3 validation protocols plus Gate 4 evaluation, routing, retry, input-inventory, semantic-inventory, and freeze-lock artifacts;
- `formal_runs`: Gate 2, Gate 3, Gate 4 development, and Gate 4 held-out run directories, with their run manifests, environment snapshots, and available seals;
- `verification_reports`: one authoritative saved Gate 0 through Gate 4 verification report per Gate;
- `interpretation_documents`: the three new research-facing documents stored in `P`;
- `design_provenance`: this approved design document stored in `D` and therefore also present in `P`;
- `non_duplication`: an explicit `reference_only` policy for benchmark inputs, result packages, and environment snapshots;
- `tag_message`: the normalization rule and expected message SHA-256.

Every referenced artifact entry contains a repository-relative POSIX path, a role, a hash source, and a lowercase SHA-256. The manifest does not hash itself and does not record a containing-commit SHA, annotated-tag object SHA, wall-clock timestamp, absolute path, or working-tree hash.

Canonical JSON uses UTF-8 without a byte-order mark, LF newlines, lexicographically sorted object keys, two-space indentation, and one trailing newline.

### Research baseline

`docs/gate0_4_research_baseline.md` answers what the closed evidence means. It contains the research problem, constrained hypothesis, evidence-producing architecture, Gate progression, observed result taxonomy, capability boundary, defensible claims, non-claims, and a short pointer to the next research-question class.

It reports the fixed result denominators separately:

- 27/30 terminal automatic successes;
- 26/27 supported-case automatic recoveries;
- 2/2 unsupported correct rejections;
- 27/27 geometry passes among validated cases;
- 30/30 conditionally complete packages;
- 25 volume-IoU results and two surface-only validations.

Its success taxonomy is descriptive, not causal. It reports 17/18 supported single-extrusion successes, 9/9 supported base-plus-through-hole successes, one designated ambiguity case with a canonical automatic result, two correct unsupported rejections, four independent ambiguity flags, and the validation-mode split. It does not infer that any observed geometric property caused success.

### Benchmark card

`docs/benchmark_v1_card.md` answers what the 30-case benchmark is, how it was constructed, how the development and held-out roles were used, and which conclusions it cannot support.

It records:

- development composition: ten single extrusions and five through-hole constructions;
- held-out composition: eight single extrusions, four through-hole constructions, one ambiguity control, and two unsupported controls;
- provenance: 27 CadQuery-generated cases and three Fusion manually modelled source constructions;
- explicit generator metadata coverage: XY 11, XZ 6, YZ 6, RX30 1, and RY45 1;
- the remaining cases as manually specified or special construction conditions that are not forced into the same frame/profile categorization scheme;
- the freeze, label-firewall, intended-use, and evaluation boundaries.

It explicitly describes the benchmark as curated and controlled, not a random or representative sample of industrial CAD models. It records small sample size, generator dependence, narrow operation scope, limited exporter diversity, and unknown external validity. It links results but does not duplicate the result table.

### Dr. Li technical brief

`docs/dr_li_gate0_4_technical_brief.md` is a communication interface for a 10-15 minute technical update, not a paper, slide deck, or claim that a presentation has been requested. It supersedes the older Gate 2 outline only for the current project briefing and leaves that historical document unchanged.

It provides a defensible one-sentence claim, a 12-minute structure, exact denominators, evidence links, likely questions, prohibited overclaims, and three representative cases:

- `T-S01` for a non-rectangular single extrusion;
- `T-H03` for a YZ-oriented base plus through-hole reconstruction;
- `T-S07` for the preserved Fusion executor capability boundary.

### README

`README.md` receives only a concise Gate 0-4 Research Baseline entry with links to the manifest, research baseline, benchmark card, technical brief, verifier command, and annotated tag. The remote default branch must contain this entry before delivery is claimed.

## Hash ownership and byte rules

Evidence is divided by ownership:

- Existing technical evidence uses `hash_source=technical_baseline_commit`. Its SHA-256 is computed from the Git blob bytes at `aafd082ccb296584364227ebc9203e44c7d13832`, never from working-tree bytes.
- New interpretation and design documents use `hash_source=containing_git_commit`. Before tagging, the containing commit is clean `HEAD=P`; after tagging, it is the peeled tag target `P`.

The verifier obtains bytes through Git object access such as `git show <commit>:<path>` or an equivalent plumbing command. This prevents checkout-specific CRLF conversion from changing the audit result.

The normalized tag message is exactly:

```text
Gate 0-4 frozen research baseline v1.

Contains:
- Gate 0-3 validated reconstruction pipeline
- Gate 4 frozen held-out evaluation
- sealed benchmark evidence references
- baseline manifest and research interpretation documents

This tag does not indicate general CAD-history recovery.
It represents a reproducible research baseline.
```

Normalization is `utf8_lf_single_trailing_newline`. The expected SHA-256 of the 333 normalized bytes is `f965d43b3aa3bc2d7cce528b42a833269e9fb24cd8790a50377292578d619ffe`. This is a message digest, not the annotated-tag object SHA.

## Verifier design

`tools/verify_gate0_4_baseline.py` is read-only by default. It prints one structured JSON result to standard output and returns zero only when all checks required by the selected phase pass. It neither writes a report nor runs Fusion or any Gate experiment.

The interfaces are:

```powershell
python tools/verify_gate0_4_baseline.py --project-root .
python tools/verify_gate0_4_baseline.py --project-root . --require-tag
```

### Pre-tag phase

The default phase runs only after `P` exists and the worktree is clean. It checks:

1. schema, baseline identity, commit syntax, and fixed commit values;
2. absence of self-reference fields, including `baseline_pack_commit`, `containing_commit`, and tag-object SHA fields;
3. safe POSIX repository-relative paths with no absolute path, backslash, empty component, `.` component, or `..` component;
4. existence and hashes of technical references in the technical baseline commit;
5. existence and hashes of design and interpretation documents in `HEAD=P`;
6. the saved PASS semantics of the authoritative Gate 0-4 verification reports without rerunning experiments;
7. validity of both Gate 4 seals by reusing the existing seal-verification implementation;
8. equality of the evaluation commit to the frozen Gate 4 evaluation commit;
9. cleanliness of the current worktree;
10. exact restriction of `aafd082..P` to the eight approved paths;
11. the `reference_only` non-duplication policy.

Gate 0 and Gate 1 saved Markdown reports are checked against their existing explicit overall PASS markers. Gate 2, Gate 3, and Gate 4 JSON reports are checked for their existing `gate_pass=true` semantics after their Git-blob hashes have matched the manifest. The verifier does not reconstruct a second experiment runner.

### Post-tag phase

`--require-tag` includes every pre-tag check and additionally checks:

1. `refs/tags/gate0-4-frozen-baseline-v1` exists;
2. the direct object type is `tag`, rejecting a lightweight tag;
3. the peeled target is a commit;
4. the peeled target contains the same manifest and is the containing commit used for new-document hashes;
5. the technical baseline commit is an ancestor of the peeled target;
6. the cumulative diff remains restricted to the approved paths;
7. the normalized complete tag message matches the frozen message SHA-256.

## Test contract

`tests/test_baseline_verifier.py` uses temporary Git repositories for mutation and tag tests. It must never create, delete, or move a real repository tag or modify real frozen evidence.

At minimum, tests cover:

1. a valid manifest and synthetic repository pass pre-tag verification;
2. absolute paths, traversal, backslashes, and malformed components are rejected;
3. a wrong SHA-256 is rejected;
4. missing evidence is rejected;
5. Git blob bytes, not checkout-transformed bytes, are hashed;
6. self-referential commit or tag-object fields are rejected;
7. a lightweight tag is rejected;
8. an annotated tag with the wrong target is rejected;
9. a frozen protocol or result-package change after the technical baseline is rejected;
10. a cumulative diff limited to the approved paths is accepted;
11. a changed or partially matching tag message is rejected;

The real-repository integration check is a post-commit verification command, not a pre-commit unit test. Before `P`, there is no containing Git commit from which its interpretation-document blobs can be verified.

## Implementation and delivery sequence

1. Confirm clean `main`, `main == origin/main`, and `HEAD == aafd082ccb296584364227ebc9203e44c7d13832`.
2. Create branch and ignored project-local worktree `gate0-4-research-baseline`.
3. Run the existing full test suite to establish a clean baseline.
4. Write and self-review this design document.
5. Commit only this document as design commit `D`.
6. Stop for user review; do not implement the verifier, manifest, interpretation documents, README entry, or tag before approval.
7. After approval, write failing verifier tests first.
8. Implement the verifier, manifest, three interpretation documents, and README entry.
9. Run the baseline-specific tests.
10. Run the full Gate 0-4 regression suite.
11. Audit the cumulative diff from the technical baseline against the eight-path allowlist.
12. Create Baseline Pack implementation commit `P`.
13. With clean `HEAD=P`, run the default pre-tag verifier.
14. Fast-forward `P` into local `main` without modifying the historical Gate evidence.
15. On merged `main`, rerun the full test suite and pre-tag verifier.
16. Create the annotated tag `gate0-4-frozen-baseline-v1` at `P` using the exact frozen message.
17. Run the post-tag verifier with `--require-tag`.
18. Atomically push `main` and `refs/tags/gate0-4-frozen-baseline-v1`.
19. Fetch the remote and verify `origin/main == P`, remote default branch `main`, annotated-tag type, peeled target `P`, and the remote README baseline entry.
20. Remove the merged temporary worktree and branch only after remote verification.

## Failure handling

- A failing original regression test stops the Baseline Pack implementation; no tag is created.
- A manifest, blob-hash, seal, report-status, path-safety, worktree-cleanliness, or diff-allowlist failure stops before tag creation.
- A post-tag failure stops before push. Because the tag is still local and was created by this workflow, it may be corrected only by deleting the unpushed local tag, fixing the packaging defect without touching technical evidence, creating a replacement implementation commit, and repeating all pre-tag checks.
- An atomic push failure leaves the verified local tag and commit intact and is reported as delivery failure, not baseline failure.
- A remote verification failure prevents any claim that the baseline was delivered.

## Acceptance criteria

Design commit `D` is complete only when this specification is the sole tracked change, contains no incomplete marker or open design decision, and is committed on `gate0-4-research-baseline` while `main` remains unchanged.

The future Baseline Pack is eligible for its annotated tag only when:

- all baseline-specific and existing tests pass;
- the pre-tag verifier passes on clean `P`;
- the cumulative diff is limited to the eight approved paths;
- no frozen technical evidence changed or was duplicated;
- the three interpretation documents retain their non-overlapping responsibilities;
- README contains the baseline entry;
- no Gate 5 document or implementation is present.

Remote delivery is complete only after the post-tag verifier passes locally, the atomic push succeeds, the remote tag peels to `P`, `origin/main` equals `P`, the remote default branch is `main`, and the remote README exposes the baseline entry.

## Gate 5 isolation

Only after remote baseline verification may a new branch be created from `gate0-4-frozen-baseline-v1` for `docs/research_directions/gate5_problem_definition.md`. That future document and all Gate 5 code, data, hypotheses, and experiments remain outside this baseline tag and cannot be merged backward into it.
