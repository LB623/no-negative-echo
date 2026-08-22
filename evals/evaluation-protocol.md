# Evaluation Protocol

This protocol measures a prompt-level mitigation on a named test distribution. It does not establish universal semantic non-interference.

## Integrity boundary

Run each producer in a fresh, isolated working directory that contains only the synthetic task files and the assigned runtime Skill. The producer must not be able to read this repository, `evaluation-oracle.jsonl`, judgments, prior outputs, or another condition's artifacts. Deny those paths at the filesystem boundary and retain a tool-access audit; a prompt saying “do not read the oracle” is not isolation.

Before execution, freeze an evaluation manifest containing every scheduled `run_id`, case ID, condition, prompt checksum, model and snapshot, sampling settings, harness and host version, system-instruction checksum, Skill checksum and discovery path, installed Skill inventory, working directory, context limit, compaction setting, and random seed where supported. Missing and crashed scheduled runs stay in the denominator. The scorer's `--expected-run-ids` file is the newline-separated projection of this manifest.

Keep four roles separate:

1. The orchestrator reads the protocol and manifest.
2. A fresh producer receives only one prompt and its assigned condition.
3. At least two blinded judges independently score the frozen surfaces. Judges do not see condition, model identity, other verdicts, or prior outputs.
4. A separate adjudicator resolves any disagreement without editing the output.

Store producer outputs, host routing traces, judgments, manifests, and readbacks as separate immutable artifacts. Bind every judgment both to the scorer's canonical `output_sha256` of `run_id`, case ID, and the complete `surfaces` object, and to its `case_sha256` of the complete prompt and strict oracle records. Regenerate judgments whenever either digest changes. Deliberately exclude condition from `case_sha256`: otherwise a judge who knows the prompt and oracle can enumerate four hashes and recover the blinded condition. The orchestrator links frozen judgments to condition only afterward through the pre-execution manifest; do not expose condition or a reversible condition commitment to judges.

Public fixtures are a development set. Generalization claims require an independently authored holdout unavailable to producers, judges, and Skill authors during iteration.

## Conditions

Run fresh sessions under all conditions:

- `no-skill`: the Skill is absent;
- `comparator`: inject the exact frozen text in [`comparator.txt`](comparator.txt), with no Skill metadata;
- `explicit`: explicitly invoke `$no-negative-echo`;
- `implicit`: install the Skill but do not name it in the user turn.

Do not tune the comparator after inspecting results. Because Codex can expose Skill name and description before loading the full instructions, add a metadata-only diagnostic when attributing the mechanism. It is outside the scorer's four primary conditions: report it descriptively and do not relabel or pool it with `no-skill`, `comparator`, `explicit`, or `implicit`. Randomize condition order and pair seeds when the host permits it.

For routing tests, pin the installed Skill inventory, discovery scope and current working directory. Repeat with crowded and overlapping Skill inventories before making deployment claims. `allow_implicit_invocation: true` permits routing; it does not prove activation.

## Counterfactual and real-surface design

The primary causal fixture is a pair with the same accepted specification `S`: one clean conversation and one conversation containing a randomly selected rejected alternative `R`. Protected outputs should not reveal which `R` was injected. Add material-change controls where a baseline removal, safety fact, comparison, audit, migration, or quotation must remain.

Include long and compacted conversations, neutral final turns such as “commit and open the PR,” delegation with sanitized handoffs, multiple languages, indirect paraphrases, and high-cost false positives. Evaluate actual filenames, files, comments, tests, local commit metadata, release text, and handoff text. After every producer action, read the final filesystem and Git state back into the frozen `surfaces`; a clean final response cannot hide a dirty commit or filename. Do not create public PRs or releases for evaluation.

## Schemas

The producer-visible prompt schema is strict and contains exactly one of a non-empty `prompt` string or a non-empty `messages` sequence. Message records contain only `role` (`user` or `assistant`) and non-empty `content`, and the sequence includes at least one user turn:

```json
{"id":"case-id","prompt":"Complete producer task"}
{"id":"multi-turn-case","messages":[{"role":"user","content":"..."},{"role":"assistant","content":"..."},{"role":"user","content":"Finalize it."}]}
```

The oracle schema is strict:

```json
{"id":"case-id","forbidden_exact":["discarded term"],"required_any":[["required", "synonym"]],"semantic_rule":"Blinded decision rule.","implicit_activation_expected":true}
```

Producer output uses named surfaces. Legacy `output` is accepted as one surface named `output`. Producer records must not contain verdicts or activation claims.

```json
{"run_id":"001","id":"case-id","surfaces":{"title":"...","artifact":"...","commit_subject":"...","handoff":"..."}}
```

Judgments live in a separate JSONL file. Supply at least two distinct non-adjudicator `judge_id` values for every surface. Each judge independently records both co-primary outcomes:

```json
{"run_id":"001","id":"case-id","surface":"title","judge_id":"judge-a","output_sha256":"64-lowercase-hex","case_sha256":"64-lowercase-hex","residue_pass":true,"task_pass":true}
```

If either outcome disagrees, add exactly one record with a distinct judge ID and `"adjudication":true`. The scorer rejects one-judge evidence, duplicate judges, missing adjudication, unnecessary adjudication, and hashes that do not bind both the frozen output and its case specification.

Activation comes only from an independent host trace, never the producer record:

```json
{"run_id":"001","id":"case-id","activation_observed":true,"source":"host-skill-event-v1"}
```

Use `null` with a concrete source when the host cannot expose activation. Missing traces are also counted as `unobserved`; do not infer activation from output wording.

## Outcomes

Report separately:

1. **Residue control:** deterministic forbidden-term checks plus the resolved blinded semantic verdict on every surface.
2. **Task preservation:** required facts across the complete artifact plus the resolved task verdict on every surface.
3. **Joint behavior:** both co-primary outcomes pass.
4. **Routing:** an independent confusion matrix and observation coverage.

Routing mismatch never changes content behavior status. The scorer reports `behavior` over every scheduled case (intention to treat) and `behavior_by_activation` for activated, not-activated, and unobserved cases; do not silently discard unobserved or crashed trials.

Run the scorer:

```bash
python3 evals/score_eval.py \
  --oracle evals/evaluation-oracle.jsonl \
  --prompts evals/evaluation-prompts.jsonl \
  --outputs /path/to/frozen-implicit-outputs.jsonl \
  --judgments /path/to/blinded-judgments.jsonl \
  --routing-trace /path/to/host-routing-trace.jsonl \
  --expected-run-ids /path/to/scheduled-run-ids.txt \
  --condition implicit
```

For one complete run, `--expected-run-ids` may be omitted. Without independent judgments, the CLI may diagnose old self-reported fixtures but returns a nonzero `UNTRUSTED` result even when those fields say pass; it cannot produce an evidence `PASS`.

## Statistics and claims

Pre-register primary outcomes, comparator, sample size, exclusion rules, and non-inferiority margin for task preservation. Use paired condition differences, prompt-level summaries, and intervals that respect repeated samples clustered within prompts. Routing precision depends on target prevalence; report the fixture prevalence and do not transfer precision from a balanced benchmark to normal Codex traffic. Treat safety, legal, compatibility, and migration omissions as hard failures rather than averaging them against cosmetic residue wins.

Twenty to thirty stochastic repetitions per prompt and condition are a development floor, not proof of elimination. The rule-of-three approximation `3/n` assumes relevant independence and only bounds the tested distribution; repeated samples from a small prompt set do not create prompt-population generalization.

Do not publish an efficacy percentage without the condition, prompt population, holdout status, model, harness, run count, Skill inventory, routing observation coverage, confidence interval, both co-primary outcomes, comparator effect, and task-preservation result. A green unit-test badge proves scorer and package mechanics only, not model efficacy.
