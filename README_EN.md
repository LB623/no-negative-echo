<p align="center">
  <img src="./no-negative-echo/assets/icon.png" width="168" height="168" alt="No Negative Echo icon">
</p>

<h1 align="center">No Negative Echo</h1>

<p align="center"><strong>Final-output hygiene for Codex</strong></p>

<p align="center"><em>Ship the result, not the conversation.</em></p>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml"><img src="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/LB623/no-negative-echo/stargazers"><img src="https://img.shields.io/github/stars/LB623/no-negative-echo?style=flat&amp;logo=github" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/LB623/no-negative-echo" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Codex-Skill-F97316" alt="Codex Skill">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/docs-English-E11D48" alt="English docs">
</p>

<p align="center">
  <a href="#about">About</a> ·
  <a href="#install">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#boundary">Decision boundary</a> ·
  <a href="#evaluation">Evaluation</a> ·
  <a href="#license">License</a> ·
  <a href="#feedback">Feedback</a>
</p>

---

<a id="about"></a>

## What this skill does

Sometimes the implementation is fixed, but the final title, comment, commit, or PR still repeats an idea rejected during the conversation. `no-negative-echo` aims to reduce that session residue in final deliverables.

```diff
- Title: Tomato and scrambled eggs (no braised pork)
+ Title: Tomato and scrambled eggs
```

It rewrites the artifact and surrounding copy from the accepted, verified state, then checks titles, filenames, code comments, test names, commits, PRs, release notes, and handoff notes separately. Rejected drafts usually remain control information, while real baseline changes, executed external actions, and required safety, migration, compatibility, and audit facts remain visible.

### Why I built it

I have rewritten too many commit messages by hand. The same mistake kept showing up, so I gave it a name: No Negative Echo.

A typical case looks like this: ask an agent to make tomato and scrambled eggs, and it first adds braised pork. After correction, the dish is right, but the PR title becomes `Tomato and scrambled eggs (no braised pork)`. The comment then explains why the dish does not need braised pork.

The same thing happens in writing. Defensive explanations disappear from the body, then return in a title such as `Agent Evaluation Overview: No Over-Defending and Prompt-Free Edition`. Those rejected frames no longer describe the article, but the title still advertises them.

The analogy comes from [a post by @songkeys](https://x.com/songkeys/status/2090416137720999992). See [`BACKGROUND.md`](BACKGROUND.md) for the full background and discussion.

<a id="install"></a>

## Install

This package is adapted to the Codex Skill structure and includes deterministic script tests and a public evaluation protocol. The repository does not yet publish model-behavior efficacy results.

### Ask Codex to install it

Send this prompt to Codex:

```text
Install the no-negative-echo Skill. Clone https://github.com/LB623/no-negative-echo, inspect the runtime manifest, and run python3 -m unittest discover -s no-negative-echo/tests -p 'test_*.py'. If it passes, run python3 no-negative-echo/scripts/install_skill.py. Report the installation path, source commit, and verification result, then remind me that the Skill will be available from the next conversation.
```

### Install from the command line

```bash
git clone --depth 1 https://github.com/LB623/no-negative-echo.git
python3 -m unittest discover -s no-negative-echo/tests -p 'test_*.py'
python3 no-negative-echo/scripts/install_skill.py
```

The script installs to `${CODEX_HOME:-$HOME/.codex}/skills/no-negative-echo` by default. It accepts only a fixed runtime manifest, rejects symlinks, special files, and unknown files, and replaces only a destination that validates as the same named Skill. Before the new target is activated, replacement errors that Python can catch, including `KeyboardInterrupt`, trigger an attempted rollback; if rollback itself fails, the script reports the backup path that requires manual inspection. Activation is the commit point: failure to clean up the old backup afterward emits a warning with its path but still reports a successful install. A process crash, power loss, or `SIGKILL` can still land between the two renames, temporarily leaving the target absent and a `.no-negative-echo-backup-*` directory behind; inspect that backup before retrying. For reproducible installation, check out a trusted tag or commit first.

Reload or restart Codex after installation.

### No install: copy into `AGENTS.md`

For a lightweight rule, add this block to the project's `AGENTS.md`:

```md
## Final-output hygiene

- Before delivery, use the user's current request, the authoritative baseline for each surface (such as the parent commit, PR target branch, previous release, or user-approved draft), and the verifiable final state to review all text created or changed for the task, including body copy, titles and openings, filenames, comments and docstrings, test names, commits and PRs, release notes, and handoffs. State only the accepted result, real differences, checks actually run, and rationale readers need to understand or audit the result. Label anything that remains unverified.
- Treat rejected proposals, correction history, assistant drafts, and temporary attempts that did not enter the final baseline, along with negative constraints or banned-term lists used only to steer generation and not needed by readers, as working context. Do not put them in the deliverable or preserve them through near-synonyms, parentheticals, or labels such as "without X," "X-free," or "cleaned up." Judge each surface separately: would a reader without the working session need this information? Omit it when the answer is no and omission would not create factual error, mislead readers, or introduce safety, compatibility, migration, compliance, or audit risk.
- Do not overwrite, revert, or misattribute user changes that predate the task or happen concurrently, and do not present them as task results. Preserve real baseline changes, executed external actions and partial failures, unresolved risks, and comparisons, quotations, audits, or migration information that the user explicitly asks to publish. Disclose sensitive information only to the minimum degree required for the destination.
- This rule authorizes editorial cleanup and delivery organization only. Unless the user explicitly authorizes the change, the task requires it, and the relevant checks have passed, do not rewrite existing history or external records, or alter executable behavior, public APIs, protocols, data schemas or configuration formats, migration or diagnostic semantics, test assertions, coverage, snapshots, or golden files. Never change tests or snapshots to conceal a failure.
```

This is a no-install lightweight option, not an equivalent replacement for the full Skill. It does not include explicit reactivation after long sessions, separate production and validation, the scanner, frozen-output and readback workflows, or the complete final gate. However, a project's `AGENTS.md` is often loaded consistently. Start with this block if you prefer, then install and explicitly invoke the Skill for important deliverables.

<a id="usage"></a>

## Usage

Codex may load the skill implicitly. After a long conversation, invoke it explicitly before generating a commit, PR, release title, or handoff note:

```text
$no-negative-echo
Write the commit subject, PR title, PR body, and handoff note from the final diff.
```

For an article:

```text
$no-negative-echo
Rewrite the title and opening from the retained final text.
```

### Surfaces it checks

| Surface | Includes correction history | States the final result only |
|---|---|---|
| PR title | `Add search (without a modal)` | `Add sidebar search` |
| Code comment | `// Do not check every second` | `// Refresh when the data changes` |
| Commit | `Search redesign: remove the modal and use a sidebar` | `Add sidebar search` |
| Article title | `Tomato and Eggs: No Braised Pork Edition` | `How to Make Tomato and Eggs` |
| Handoff note | `Removed the red button and the old explanation` | `Changed the submit button to blue; tests pass` |

<a id="boundary"></a>

## Decision boundary

This skill does not simply purge keywords. Real removals, migration requirements, and safety information still belong in the final artifact.

| Content | Treatment |
|---|---|
| An option discussed only in the conversation and never added to the baseline | Omit |
| Unsaved assistant drafts and intermediate attempts | Omit |
| Rejected title frames, tones, and self-defensive wording | Omit |
| Pre-existing uncommitted user changes | Preserve ownership; do not treat them as this task's work or a rejected draft |
| External sends, publications, deletions, migrations, or partial actions | Preserve the observed result and material risk |
| A published v1 API that was actually removed | Keep, with migration instructions |
| Allergens, safety rules, legal requirements, or compatibility constraints | Keep |
| Comparisons, audits, or verbatim quotations explicitly requested by the user | Keep |
| A confirmed architectural decision that prevents recurrence | Keep in an ADR or equivalent surface, not unrelated titles |

Judge each output surface separately:

- Would a reader who never saw the working session need this information?
- Would omitting it make the result unsafe, inaccurate, misleading, incompatible, or noncompliant?
- Did it exist in the authoritative baseline, and does the current artifact need to explain that change?

The first condition is required. If it holds, keep the information when either the second or third condition also holds. Keep comparisons, audits, verbatim quotations, changelogs, and migration notes when the user explicitly requests them.

<p align="center">
  <img src="./no-negative-echo/assets/decision-boundary.png" width="920" alt="Working-session drafts and correction traces remain outside the review boundary while one clean final document moves into delivery">
</p>

Choose the authoritative baseline per surface: a commit uses its parent tree or staged diff, a PR uses the target-branch merge base, a release note uses the previous release, and a handoff also accounts for the initial working tree and executed external actions. Uncommitted does not mean rejected; preserve ownership of pre-existing user changes. Only assistant drafts, unaccepted patches, and local temporary attempts are session history.

## Capability boundary

This is a prompt-level mitigation, not a deterministic filter. It reduces the chance that session residue enters the final artifact, but it cannot guarantee a clean result every time.

- The host decides whether Codex loads the skill implicitly. Invoke it explicitly for important deliverables.
- The skill cannot erase context the model has already read. It also cannot control terminal output, tool logs, or interface copy generated by the host.
- The bundled scanner provides deterministic checks for raw text, filenames, and suspicious Unicode. With `--root` it checks directory names in root-relative paths; otherwise it checks basenames only. It is not a rendering, semantic, media, or secret scanner; a `PASS` does not prove that the final deliverable is clean.
- If producer or validator context inheritance cannot be verified, the result is best-effort and must not be described as sanitized or independently validated.
- The skill removes session residue from final deliverables. It does not stop a model from attempting unnecessary work earlier in the session.
- Use dedicated secret scanners or compliance tools for credentials, personal information, and other sensitive data.

Claude Code, Cursor, and similar environments have not been independently tested. This repository does not claim support for them.

<a id="evaluation"></a>

## Development and evaluation

Run the local tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The installed [`no-negative-echo/`](no-negative-echo/) directory contains runtime files only. Evaluation prompts and answers live in [`evals/`](evals/) so development cases do not enter the model context with the skill.

The public cases are a development set. Passing them does not mean the problem is solved. The repository specifies four conditions—no skill, a frozen comparator, explicit invocation, and implicit invocation—and requires routing to be reported separately from post-activation behavior, with independent judgments, frozen outputs, real-surface readback, and an unpublished holdout. CI runs deterministic script and scorer tests only; it does not run Codex model evaluations or produce an efficacy percentage. See [`evaluation-protocol.md`](evals/evaluation-protocol.md) for the format and statistical limits.

<details>
<summary>Repository structure</summary>

```text
.
├── .github/workflows/test.yml
├── BACKGROUND.md
├── LICENSE
├── README.md
├── README_EN.md
├── evals/
│   ├── comparator.txt
│   ├── evaluation-oracle.jsonl
│   ├── evaluation-prompts.jsonl
│   ├── evaluation-protocol.md
│   └── score_eval.py
├── no-negative-echo/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── assets/
│   │   ├── decision-boundary.png
│   │   ├── icon-400.png
│   │   └── icon.png
│   └── scripts/check_surface.py
├── scripts/install_skill.py
└── tests/
    ├── evaluation-cases.md
    ├── test_eval_integrity.py
    ├── test_installer_scanner.py
    └── test_scripts.py
```

</details>

<a id="license"></a>

## License

This project is released under the [MIT License](LICENSE). Commercial use, modification, distribution, and closed-source redistribution are allowed as long as the original copyright and license notices are preserved.

<a id="feedback"></a>

## Feedback

If you find another no-negative-echo result, open an issue with the original request, actual output, expected output, and affected surface. Also note whether the skill was invoked explicitly or loaded implicitly. Replace real credentials, personal information, and internal project names before submitting.
