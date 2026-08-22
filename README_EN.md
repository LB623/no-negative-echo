<p align="center">
  <img src="./no-negative-echo/assets/icon.png" width="168" height="168" alt="No Negative Echo icon">
</p>

<h1 align="center">No Negative Echo</h1>

<p align="center"><strong>Final-output hygiene for Agent Skills</strong></p>

<p align="center"><em>Ship the result, not the conversation.</em></p>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml"><img src="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/LB623/no-negative-echo/stargazers"><img src="https://img.shields.io/github/stars/LB623/no-negative-echo?style=flat&amp;logo=github" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/LB623/no-negative-echo" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Agent%20Skills-open%20format-F97316" alt="Open Agent Skills format">
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

The runtime package uses the common subset of the [open Agent Skills format](https://agentskills.io/specification). Hosts that support the format can discover it natively; other agents that can read repository files can load it through a manual prompt. Here, "compatible" refers only to package structure and an available installation path. It does not mean behavioral efficacy has been validated on every host.

### Why I built it

I have rewritten too many commit messages by hand. The same mistake kept showing up, so I gave it a name: No Negative Echo.

A typical case looks like this: ask an agent to make tomato and scrambled eggs, and it first adds braised pork. After correction, the dish is right, but the PR title becomes `Tomato and scrambled eggs (no braised pork)`. The comment then explains why the dish does not need braised pork.

The same thing happens in writing. Defensive explanations disappear from the body, then return in a title such as `Agent Evaluation Overview: No Over-Defending and Prompt-Free Edition`. Those rejected frames no longer describe the article, but the title still advertises them.

The analogy comes from [a post by @songkeys](https://x.com/songkeys/status/2090416137720999992). See [`BACKGROUND.md`](BACKGROUND.md) for the full background and discussion.

<a id="install"></a>

## Install

This package follows the Agent Skills `SKILL.md` plus optional scripts/resources structure. The open specification defines the package format, not discovery directories, invocation syntax, or tool permissions; the product scopes and paths below come from each host's official documentation. This repository does not yet publish cross-host model-behavior efficacy results.

### Give an agent one installation URL

Send this prompt to an agent with network, terminal, and filesystem access:

```text
Please install the no-negative-echo Skill from:
https://raw.githubusercontent.com/LB623/no-negative-echo/main/INSTALL.md
When finished, tell me the installation result and whether a new session or restart is required. If you cannot verify it, do not claim success.
```

[`INSTALL.md`](INSTALL.md) is an agent-readable installation contract. It requires host detection, a temporary clone with a recorded commit, tests before installation, destination readback, and an explicit answer about whether a new session is required. It does not assume that every agent natively supports skills.

### Install from the command line

```bash
git clone https://github.com/LB623/no-negative-echo.git
python3 -I -m unittest discover -s no-negative-echo/tests -p 'test_*.py'
python3 -I no-negative-echo/scripts/install_skill.py \
  --expected-provenance-sha256 9cc10a0f1d2d87f0de8517bf40c59e364783e2410308a0c8f815288f53a7cc47 \
  --discovery-root "$HOME/.agents/skills" \
  --agent codex
```

This example installs to the current Codex path. For another host, replace the preset using the matrix below. Use `--agent shared` only when the user explicitly requests one installation shared by multiple hosts.

Installation matrix (official documentation checked 2026-08-22. "Native package" means the vendor explicitly supports `SKILL.md`; it does not mean this repository has completed behavioral evaluation on that host):

| Host / product scope | Native package | Official user-level root | Installer preset | Shares `~/.agents/skills` |
|---|---|---|---|---|
| [ChatGPT desktop app / Codex CLI / IDE extension](https://developers.openai.com/codex/skills) | Yes | `~/.agents/skills` | `--agent codex` or `--agent shared` | Yes |
| [Claude Code](https://code.claude.com/docs/en/slash-commands) | Yes | `~/.claude/skills` | `--agent claude` | Not listed by its docs |
| [Cursor Agent / CLI](https://cursor.com/docs/skills) | Yes | `~/.cursor/skills` or `~/.agents/skills` | `--agent cursor` or `--agent shared` | Yes |
| [Gemini CLI](https://geminicli.com/docs/cli/tutorials/skills-getting-started/) | Yes | `~/.gemini/skills` or `~/.agents/skills` | `--agent gemini` or `--agent shared` | Yes |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/reference/customization-cheat-sheet) | Yes | `~/.copilot/skills` or `~/.agents/skills` | `--agent copilot` or `--agent shared` | Yes |

`--agent codex` and `--agent shared` both use `~/.agents/skills`; Cursor, Gemini CLI, and GitHub Copilot also document that shared user-level path. With no destination option, the installer prefers the current Codex path and reuses an existing old installation only when it detects one. Use `--agent codex-legacy` to select `${CODEX_HOME:-$HOME/.codex}/skills` explicitly. That legacy compatibility path is not the user-level path recommended by current OpenAI documentation. `--agent` and the advanced `--skills-dir /absolute/or/project/path` are mutually exclusive; a custom destination must be absolute and requires at least one `--discovery-root`. Before installation, pass every verified user/workspace discovery root for the current host as a separate `--discovery-root /absolute/path`, so the installer can repeat concurrent-collision checks while holding its coordination lock. A custom directory proves only that files were copied there; verify host discovery separately. For project scope, point `--skills-dir` at `.agents/skills` for Codex/Cursor/Gemini/Copilot or `.claude/skills` for Claude Code. GitHub Copilot also supports `.github/skills`. Copilot cloud agent and code review need a project Skill in the repository; they cannot rely on a local home directory.

The presets in the table apply only to the listed surfaces with a persistent local home; they do not assert user-level installation support for Codex cloud or other web, remote, or ephemeral surfaces. Such a surface may use `--skills-dir` only when official documentation names its exact project root and the user authorizes modifying the current repository. Otherwise, report the surface as unsupported rather than claiming that a copy in a temporary home is a persistent installation.

The script creates `no-negative-echo` under the selected root. It accepts only a fixed runtime manifest, rejects symlinks, special files, and unknown files, and uses file hashes in a provenance marker so a user-modified same-name directory is not mistaken for an owned installation. Only regular `.DS_Store` files and regular `.pyc`/`.pyo` files directly inside `__pycache__` are treated as disposable cache; any other added content makes installation stop in place. An unmarked historical official version is migrated only when every path and digest exactly matches a known commit; customized, partial, and otherwise unrecognized directories are preserved in place and rejected. Staging and validated previous-version recovery directories live at same-filesystem sibling paths outside the Skill discovery root. After an upgrade, the old version is preserved and its exact path is reported instead of being recursively deleted; this prevents duplicate discovery and path-swap deletion. After the new target is renamed into place, the installer revalidates its manifest, provenance, and directory identity. If that cannot be proven, it explicitly reports activation as uncertain with the target/recovery paths instead of reporting ordinary success. Before activation, replacement errors that Python can catch, including `KeyboardInterrupt`, trigger an attempted rollback; if rollback itself fails, the script reports the recovery path that requires manual inspection. A process crash, power loss, or `SIGKILL` can still land between the two renames and temporarily leave the target absent; inspect the reported recovery path before retrying. Provenance is an integrity and ownership boundary for this installation, not a code signature. For reproducible installation, check out a trusted tag or commit first.

A marked destination must also match an official marker SHA-256 embedded in the installer; a self-authored marker with an internally consistent structure and file hashes does not grant overwrite ownership. The Claude preset checks conflicts only in Claude Code's own discovery root. Because Cursor can also read `.claude/skills`, people who use Cursor as well must ensure that only one discoverable copy exists across `.agents/skills`, `.cursor/skills`, `.claude/skills`, and legacy `.codex/skills`.

For official historical text released before `.gitattributes`, the installer canonicalizes Windows checkout CRLF endings to LF before comparison. Binary files still match byte for byte, and no other content changes are tolerated.

Reload or restart as required by the host, then confirm that `no-negative-echo` appears in its skill list. A directory proves file installation; list visibility proves discovery. Neither alone proves activation in the current turn or behavioral efficacy. Unless the host can confirm both a current-session rescan and current-session activation, report that a new session is required or recommended; list visibility alone cannot justify "not required."

### Manual fallback without native skill discovery

If the agent can read the cloned files but does not support Agent Skills, or discovery cannot be confirmed, send this at the start of each task:

```text
Before starting the task, read ./no-negative-echo/SKILL.md in full, resolve its relative paths against ./no-negative-echo, and follow its workflow for this turn. In the handoff, state which files you actually read and which checks you actually ran. If you cannot read the files or run the scripts, label the result best-effort and do not claim that the host activated the Skill.
```

For a persistent lightweight rule, add this block to a project instruction file the host reliably loads, such as `AGENTS.md` on hosts that support it:

```md
## Final-output hygiene

- Before delivery, use the user's current request, the authoritative baseline for each surface (such as the parent commit, PR target branch, previous release, or user-approved draft), and the verifiable final state to review all text created or changed for the task, including body copy, titles and openings, filenames, comments and docstrings, test names, commits and PRs, release notes, and handoffs. State only the accepted result, real differences, checks actually run, and rationale readers need to understand or audit the result. Label anything that remains unverified.
- Treat rejected proposals, correction history, assistant drafts, and temporary attempts that did not enter the final baseline, along with negative constraints or banned-term lists used only to steer generation and not needed by readers, as working context. Do not put them in the deliverable or preserve them through near-synonyms, parentheticals, or labels such as "without X," "X-free," or "cleaned up." Judge each surface separately: would a reader without the working session need this information? Omit it when the answer is no and omission would not create factual error, mislead readers, or introduce safety, compatibility, migration, compliance, or audit risk.
- Do not overwrite, revert, or misattribute user changes that predate the task or happen concurrently, and do not present them as task results. Preserve real baseline changes, executed external actions and partial failures, unresolved risks, and comparisons, quotations, audits, or migration information that the user explicitly asks to publish. Disclose sensitive information only to the minimum degree required for the destination.
- This rule authorizes editorial cleanup and delivery organization only. Unless the user explicitly authorizes the change, the task requires it, and the relevant checks have passed, do not rewrite existing history or external records, or alter executable behavior, public APIs, protocols, data schemas or configuration formats, migration or diagnostic semantics, test assertions, coverage, snapshots, or golden files. Never change tests or snapshots to conceal a failure.
```

These fallbacks do not depend on native discovery, but they are not equivalent to the full Skill. Instruction filenames, scope, and load timing still depend on the host. The lightweight rule also omits explicit reactivation after long sessions, separate production and validation, the scanner, frozen-output and readback workflows, and the complete final gate.

<a id="usage"></a>

## Usage

Hosts that support implicit matching may select the Skill from its `description`, but discovery is not activation. After a long conversation, explicitly name it before generating a commit, PR, release title, or handoff note. The documented syntax is `$no-negative-echo` in Codex and `/no-negative-echo` in Claude Code. On other hosts, select the Skill through that host's current native mechanism, or name it directly in the prompt and verify actual activation; do not infer activation from output wording alone.

```text
Use the no-negative-echo Skill.
Write the commit subject, PR title, PR body, and handoff note from the final diff.
```

For an article:

```text
Use the no-negative-echo Skill.
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

- The host and current surface/version decide whether the Skill is discovered, implicitly selected, or explicitly activated, and which tools it can use. Explicitly name it for important deliveries and retain observable evidence.
- The skill cannot erase context the model has already read. It also cannot control terminal output, tool logs, or interface copy generated by the host.
- The bundled scanner provides deterministic checks for raw text, filenames, and suspicious Unicode. With `--root` it checks directory names in root-relative paths; otherwise it checks basenames only. It is not a rendering, semantic, media, or secret scanner; a `PASS` does not prove that the final deliverable is clean.
- If producer or validator context inheritance cannot be verified, the result is best-effort and must not be described as sanitized or independently validated.
- The skill removes session residue from final deliverables. It does not stop a model from attempting unnecessary work earlier in the session.
- Use dedicated secret scanners or compliance tools for credentials, personal information, and other sensitive data.

The installation matrix establishes only vendor-documented package-format and discovery-path compatibility. It does not show that this Skill routes correctly or behaves effectively on a host. For agents without native Agent Skills, manual loading is a best-effort fallback and must not be labeled native activation. `agents/openai.yaml` is optional UI metadata for OpenAI surfaces, not a prerequisite for common Agent Skills behavior.

<a id="evaluation"></a>

## Development and evaluation

Run the local tests:

```bash
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

The installed [`no-negative-echo/`](no-negative-echo/) directory contains runtime files only. Evaluation prompts and answers live in [`evals/`](evals/) so development cases do not enter the model context with the skill.

The public cases are a development set. Passing them does not mean the problem is solved. The repository specifies four conditions—no skill, a frozen comparator, explicit invocation, and implicit invocation—and requires routing to be reported separately from post-activation behavior, with independent judgments, frozen outputs, real-surface readback, and an unpublished holdout. One complete evaluation declares one reference host in advance and holds that host and version fixed across all four conditions; it does not need to test every agent. Other hosts are optional, independent replications and are not pooled with the primary evaluation. The scorer validates one condition at a time and treats `--reference-host` as a declared label; the orchestrator and frozen-manifest audit must enforce consistency across all four conditions. CI runs deterministic script and scorer tests only; it does not run agent-model evaluations or produce an efficacy percentage. See [`evaluation-protocol.md`](evals/evaluation-protocol.md) for the format and statistical limits.

<details>
<summary>Repository structure</summary>

```text
.
├── .gitattributes
├── .github/workflows/test.yml
├── BACKGROUND.md
├── INSTALL.md
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
│   ├── .no-negative-echo-provenance.json
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
