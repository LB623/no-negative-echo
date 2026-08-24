<p align="center">
  <img src="./no-negative-echo/assets/icon.png" width="168" alt="No Negative Echo icon">
</p>

<h1 align="center">No Negative Echo</h1>

<p align="center"><strong>Ship the accepted result, not the rejected proposal.</strong></p>

<p align="center"><em>Ship the result, not the conversation.</em></p>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml"><img src="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/LB623/no-negative-echo/stargazers"><img src="https://img.shields.io/github/stars/LB623/no-negative-echo?style=flat&amp;logo=github" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/LB623/no-negative-echo" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
</p>

## The problem

An agent corrects its implementation, then lets the rejected proposal leak into the final title, comment, commit, PR, or handoff:

```diff
- Title: Tomato and Egg Stir-fry (without braised pork)
+ Title: Tomato and Egg Stir-fry
```

`no-negative-echo` is an [Agent Skills](https://agentskills.io/specification)-format skill. It has agents regenerate delivery text from the accepted, verified state and check delivery surfaces for session residue.

Use it to:

- Write commit messages, PR titles, and descriptions from the final diff
- Rewrite article titles, openings, UI copy, or handoffs
- Finalize work after long conversations, collaboration, or multiple revisions

## Ways to use it

Install the Skill when you need its decision workflow, scanner, and high-assurance mode. Add the compact instructions to `AGENTS.md` when you only want the current project to follow the core rule continuously. You can use both approaches together.

### Option 1: Install the Skill

Ask an agent with network, terminal, and file permissions to follow the installation contract:

```text
Install the no-negative-echo Skill:
https://raw.githubusercontent.com/LB623/no-negative-echo/main/INSTALL.md
Report the installation result and whether a new session or restart is needed.
If verification is unavailable, do not claim that installation succeeded.
```

Local Codex example:

```bash
git clone https://github.com/LB623/no-negative-echo.git
cd no-negative-echo
python3 -I -m unittest discover -s tests -p 'test_*.py'
python3 -I scripts/install_skill.py \
  --expected-provenance-sha256 d42280b21f519ea00e417c68f31c68ca3d7faae607faf6dcb6e04beeff9c5ed6 \
  --discovery-root "$HOME/.agents/skills" \
  --agent codex
```

See [INSTALL.md](INSTALL.md) for other hosts, project-level installation, upgrades, and the complete safety contract.

Explicitly invoke the Skill before an important delivery:

```text
Use the no-negative-echo Skill.
Based on the final diff, write the commit subject, PR title, PR body, and handoff.
```

For editorial work:

```text
Use the no-negative-echo Skill.
Rewrite the title and opening from the final retained body.
```

### Option 2: Add it to the project's AGENTS.md

If you only need the core behavior, append the following instructions to `AGENTS.md` at the project root. Create the file if it does not exist, and do not overwrite existing project instructions.

```markdown
## No Negative Echo

When producing final artifacts and their wrappers, including titles, filenames,
body text, comments, labels, commits, PRs, and handoffs, describe only the
accepted final state. Assume the reader did not see this session.

- Treat session-only rejections, intermediate attempts, and wording corrections as control information. Do not make them the name or narrative center of the final artifact.
- Judge each delivery surface separately: Would a reader who did not see this session need the information? Would omission make the result inaccurate, unsafe, misleading, or incomplete for compatibility? Is it a real change from the state committed or approved when the task began, and does this surface need to explain it?
- “Do not mention X” does not mean “write X-free.” Regenerate titles, filenames, openings, and labels from the positive target instead of editing rejected wording token by token.
- Preserve real baseline changes, executed external actions, and necessary technical names, diagnostics, tests, and snapshots. User changes that existed before the task are not rejected content.
- Do not include unrelated changes in this task's commit, PR, or handoff. Keep comparisons, quotations, audits, and migration explanations only when the user requests them or the current surface requires them.
- After writing, reread all user-visible content and wrappers, including filenames, metadata, and hook rewrites. Recheck after any change. Do not add “cleaned” or “no residue” claims.
```

This option depends on the agent supporting `AGENTS.md`. Codex reads project instructions at the start of each run; after changing the file, start a new run or session to load the latest version. See the [official OpenAI documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md) for discovery details.

The `AGENTS.md` option does not install the Skill and cannot use `scripts/check_surface.py` or the high-assurance workflow. When both approaches are present, `AGENTS.md` supplies the persistent core rule and the Skill adds full validation for important deliveries.

## Decision rule

| Content | Treatment |
|---|---|
| A proposal discussed only in the session and absent from the final baseline | Omit |
| Assistant drafts, intermediate attempts, and wording corrections | Omit |
| Released API removals, migrations, and external operations | State accurately |
| Facts required for safety, law, compatibility, or audit | Keep |
| Comparisons, quotations, or decision records explicitly requested by the user | Keep |
| User changes that existed before the task | Preserve attribution; do not claim them as task output |

For every surface, ask:

1. Would a reader who never saw the session need this information?
2. Would omission make the result inaccurate, unsafe, misleading, or incompatible?
3. Is it a real change in the authoritative baseline that this surface needs to explain?

Something having been discussed or rejected is not, by itself, a reason to mention it.

## Boundaries

This is a prompt-level mitigation, not a deterministic filter:

- Discovery does not prove activation; explicitly invoke it for important delivery work.
- It cannot erase context already read by a model or control tool logs and host UI.
- Its bundled scanner checks text, filenames, and suspicious Unicode only; `PASS` is not a semantic review.
- Do not change APIs, migrations, tests, snapshots, or pre-existing user work merely to satisfy this skill.
- Use dedicated tools for credentials, privacy, and compliance checks.

See [SKILL.md](no-negative-echo/SKILL.md) for the default workflow. Sensitive data, public release, and strict validation load [high-assurance-finalization.md](no-negative-echo/references/high-assurance-finalization.md) only when needed.

## Development and evaluation

```bash
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

The evaluation protocol and public cases are in [`evals/`](evals/). CI runs deterministic scripts and scorer tests; it does not make model-effectiveness claims.

## Further reading

- [Installation contract](INSTALL.md)
- [Background](BACKGROUND.md)
- [Evaluation protocol](evals/evaluation-protocol.md)
- [License](LICENSE)

## Feedback

When opening an issue, include the original request, actual output, expected output, location, and whether invocation was explicit or implicit. Remove credentials, personal data, and internal project names first.

Licensed under the [MIT License](LICENSE).
