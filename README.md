<p align="center">
  <img src="./no-negative-echo/assets/icon.png" width="168" height="168" alt="No Negative Echo icon">
</p>

<h1 align="center">No Negative Echo</h1>

<p align="center"><strong>Final-output hygiene for Agent Skills · 开放 Agent Skills 最终交付清理</strong></p>

<p align="center"><em>Ship the result, not the conversation.</em></p>

<p align="center">
  <strong>中文</strong> · <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml"><img src="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/LB623/no-negative-echo/stargazers"><img src="https://img.shields.io/github/stars/LB623/no-negative-echo?style=flat&amp;logo=github" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/LB623/no-negative-echo" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Agent%20Skills-open%20format-F97316" alt="Open Agent Skills format">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/docs-中文-E11D48" alt="中文文档">
</p>

<p align="center">
  <a href="#about">关于</a> ·
  <a href="#install">安装</a> ·
  <a href="#usage">使用</a> ·
  <a href="#boundary">判断边界</a> ·
  <a href="#evaluation">评测</a> ·
  <a href="#license">许可证</a> ·
  <a href="#feedback">反馈</a>
</p>

---

<a id="about"></a>

## 这是什么

方案已经改对，Agent 最后却把聊天里淘汰过的内容写进了标题、注释、commit 或 PR。`no-negative-echo` 用于降低这类会话残留进入最终交付的概率。

```diff
- 标题：番茄炒蛋（没有东坡肉）
+ 标题：番茄炒蛋
```

它要求从最终采用且已经验证的状态重写正文和外层文案，并分别检查标题、文件名、代码注释、测试名、commit、PR、发布说明和交付说明。聊天里被否掉的草案通常只作为控制信息；真实基线变化、已执行的外部操作和必要的安全、迁移、兼容及审计事实仍须保留。

运行包采用 [Agent Skills 开放格式](https://agentskills.io/specification)的公共子集。支持该格式的宿主可以原生发现它；其他能读取仓库文件的 Agent 可通过手动提示词加载。这里的“兼容”只指包结构和可用安装路径，不代表每个宿主上都已验证行为有效性。

### 为什么做这个 Skill

我已经手改过太多次 commit message。其中一类改得最多，我给它起了个固定名字：「移除此地无银三百两」。

典型场景是，让 Agent 做一盘番茄炒蛋，它先加了东坡肉。指出问题后，菜改对了，PR 标题却成了 `番茄炒蛋（无东坡肉）`，注释里还要解释为什么这道菜不需要东坡肉。

写文章也会碰到同样的问题。正文里的自证句删完，标题又冒出 `某某综述：不过度防御且无提示版`。成品已经和那些说法没关系，交付层却把纠正过程带了回来。

这个比喻来自 [@songkeys 的帖子](https://x.com/songkeys/status/2090416137720999992)，更完整的背景和讨论收在 [`BACKGROUND.md`](BACKGROUND.md)。

<a id="install"></a>

## 安装

该包遵循 Agent Skills 格式的 `SKILL.md` + 可选脚本/资源结构。开放规范定义包格式，不定义发现目录、调用语法或工具权限；下表的产品范围和目录来自各宿主的官方文档。仓库尚未发布跨宿主的模型行为有效性结果。

### 给 Agent 一个 URL 安装

把下面这段发给有网络、终端和文件权限的 Agent：

```text
请安装 no-negative-echo Skill：
https://raw.githubusercontent.com/LB623/no-negative-echo/main/INSTALL.md
装完告诉我安装结果，以及是否需要开启新会话或重启。无法验证时，不要宣称安装成功。
```

[`INSTALL.md`](INSTALL.md) 是面向 Agent 的安装合约：它要求识别宿主、临时克隆并记录 commit、先测试后安装、回读目标，最后明确报告是否需要新会话。它不假设任意 Agent 都原生支持 Skill。

### 命令行安装

```bash
git clone https://github.com/LB623/no-negative-echo.git
python3 -I -m unittest discover -s no-negative-echo/tests -p 'test_*.py'
python3 -I no-negative-echo/scripts/install_skill.py \
  --expected-provenance-sha256 9cc10a0f1d2d87f0de8517bf40c59e364783e2410308a0c8f815288f53a7cc47 \
  --discovery-root "$HOME/.agents/skills" \
  --agent codex
```

上例安装到当前 Codex 路径；使用其他宿主时，按下表替换 preset。只在用户明确要求一份安装共享给多个宿主时使用 `--agent shared`。

安装矩阵（官方文档核实日期：2026-08-22。“原生包”表示厂商明确支持 `SKILL.md`，不表示本仓库已在该宿主完成行为评测）：

| 宿主 / 产品范围 | 原生包 | 官方 user-level 根目录 | 安装器 preset | `~/.agents/skills` 共享 |
|---|---|---|---|---|
| [ChatGPT desktop app / Codex CLI / IDE extension](https://developers.openai.com/codex/skills) | 是 | `~/.agents/skills` | `--agent codex` 或 `--agent shared` | 是 |
| [Claude Code](https://code.claude.com/docs/en/slash-commands) | 是 | `~/.claude/skills` | `--agent claude` | 官方未列出 |
| [Cursor Agent / CLI](https://cursor.com/docs/skills) | 是 | `~/.cursor/skills` 或 `~/.agents/skills` | `--agent cursor` 或 `--agent shared` | 是 |
| [Gemini CLI](https://geminicli.com/docs/cli/tutorials/skills-getting-started/) | 是 | `~/.gemini/skills` 或 `~/.agents/skills` | `--agent gemini` 或 `--agent shared` | 是 |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/reference/customization-cheat-sheet) | 是 | `~/.copilot/skills` 或 `~/.agents/skills` | `--agent copilot` 或 `--agent shared` | 是 |

`--agent codex` 和 `--agent shared` 都使用 `~/.agents/skills`；该共享 user-level 路径当前也被 Cursor、Gemini CLI 和 GitHub Copilot 列出。无参数运行会优先使用当前 Codex 路径，仅在发现现有旧安装时继续使用它；`--agent codex-legacy` 才显式选择 `${CODEX_HOME:-$HOME/.codex}/skills`。该 legacy compatibility path 不是当前 OpenAI 文档中的推荐 user-level 目录。`--agent` 和高级 `--skills-dir /absolute/or/project/path` 互斥；自定义目录必须是绝对路径，且至少传一个 `--discovery-root`。安装前应把当前宿主所有已核实的 user/workspace 发现根分别用 `--discovery-root 绝对路径` 传入，让安装器在协调锁内复查并发冲突。自定义目录只能证明文件复制到了该位置，必须另外核对宿主是否发现它。项目级安装可将 `--skills-dir` 指向仓库的 `.agents/skills`（Codex/Cursor/Gemini/Copilot）或 `.claude/skills`（Claude Code）；GitHub Copilot 也支持 `.github/skills`。Copilot cloud agent 或 code review 要使用仓库内的项目级 Skill，不能依赖本机 home 目录。

表中 preset 只适用于具有持久本地 home 的列出 surface，不代表 Codex cloud 或其他 web/remote/ephemeral surface 支持用户级安装。这些 surface 只能在官方文档明确项目级根目录、且用户授权修改当前仓库时使用 `--skills-dir`；否则应报告不支持，不能对临时 home 的复制声称持久安装成功。

脚本会在所选根目录下创建 `no-negative-echo`。它只接受固定运行文件清单，拒绝符号链接、特殊文件和未知文件，并用 provenance marker 的文件哈希防止把用户改过的同名目录误当成官方安装覆盖。只有普通 `.DS_Store` 以及 `__pycache__` 直接包含的普通 `.pyc`/`.pyo` 会被当作可丢弃缓存；其他附加内容都会让安装原地停止。无 marker 的历史官方版只在完整路径和哈希精确匹配已知提交时才会自动迁移；自定义、不完整或其他无法识别的目录会原地保留并报错。暂存目录和已验证旧版的 recovery 目录都放在 Skill 发现根之外的同盘相邻位置；升级成功后旧版不会被自动递归删除，而是保留并报告精确路径，避免扫描到两份 Skill 或因路径交换误删数据。新目标重命名后还会重验运行清单、provenance 和目录身份；如无法确认，安装器会显式报告 activation uncertain 及目标/recovery 路径，不会普通报成功。在激活前，Python 能捕获的替换异常（包括 `KeyboardInterrupt`）会尝试恢复旧目录；恢复失败则报告需要人工检查的 recovery 路径。进程崩溃、断电或 `SIGKILL` 仍可能在两次重命名之间使目标暂时缺失；重试前应先检查报告的 recovery 路径。provenance 只是本次安装的完整性与所有权边界，不是代码签名。需要可复现安装时，请先 checkout 你信任的 tag 或 commit。

有 marker 的旧目标还必须匹配安装器内置的官方 marker SHA-256；自写一份结构和内部哈希都自洽的 marker，也不构成自动覆盖授权。Claude preset 只按 Claude Code 自身的发现根判断冲突；由于 Cursor 也可读取 `.claude/skills`，同时使用 Cursor 的人还要确保 `.agents/skills`、`.cursor/skills`、`.claude/skills` 和 legacy `.codex/skills` 中只有一份可发现副本。

早于 `.gitattributes` 的官方历史文本会先把 Windows checkout 的 CRLF 规范为 LF 再比对，二进制文件仍逐字节匹配；安装器不容忍其他内容变化。

安装后按宿主的方式 reload/restart，再在技能列表中确认 `no-negative-echo`。目录存在只能证明文件已安装；列表可见只能证明已发现，两者都不能单独证明本轮已激活或行为有效。除非宿主能同时确认当前会话已重扫描且已激活，否则仍应报告需要或建议新会话，不能仅凭列表可见报告“不需要”。

### 手动回退：不依赖原生 Skill 发现

如果 Agent 可以读取克隆后的文件，但不支持 Agent Skills 或无法确认已发现，每次任务开始时显式发送：

```text
在开始任务前，请完整读取 ./no-negative-echo/SKILL.md，把相对路径视为相对 ./no-negative-echo，并在本轮遵循其中流程。交付时说明实际读取的文件和实际运行的检查；如果无法读取或运行脚本，请明确标注 best-effort，不要宣称 Skill 已被宿主激活。
```

只想持久放一条轻量规则时，也可把下面这段加到宿主能够稳定加载的项目指令文件（例如支持该文件的宿主中使用 `AGENTS.md`）：

```md
## 最终交付清理

- 交付前，按用户当前要求、每个输出位置的权威基线（如父提交、PR 目标分支、上一发布版本或用户批准稿）和可复核的最终状态，检查本任务新建或修改的正文、标题与开篇、文件名、注释/docstring、测试名、commit/PR、发布说明和交付说明。只陈述最终采用的结果、真实差异、实际执行的验证，以及读者理解或审计结果所需的理由；未验证项必须明确标注。
- 未进入最终基线的被否方案、纠错经过、助手草稿和临时尝试，以及仅用于控制生成过程、无需对读者公开的负向指令或禁用词表，只作为工作信息，不写入成品；也不得用近义改写、括号、“无 X”“非 X 版”或“已清理”等标签保留。每个位置单独判断：不了解本轮会话的读者是否需要该信息？若不需要，且省略不会造成事实错误、误导、安全、兼容、迁移、合规或审计风险，则省略。
- 不得覆盖、回退或误归因任务开始前及并发发生的用户改动，也不得把它们算作本次成果。按需如实保留真实基线变化、已执行的外部操作及部分失败、未解决风险，以及用户明确要求对外说明的比较、引用、审计或迁移信息；敏感信息按目的地最小披露。
- 此规则只授权清理表述和交付组织。除非用户明确授权、任务本身要求并已完成相应验证，不得改写既有历史或外部记录，不得改变可执行行为、公共 API、协议、数据结构或配置格式、迁移与诊断语义、测试断言、覆盖范围、快照或 Golden 文件，也不得通过修改测试或快照掩盖失败。
```

这些是不依赖原生发现的回退方案，但不等价于完整 Skill：指令文件的名称、作用域和加载时机仍取决于宿主，轻量规则也没有长会话重新激活、分离生成与验证、扫描器、冻结与回读流程和完整验收闸门。

<a id="usage"></a>

## 使用

支持隐式匹配的宿主可根据 `description` 自行选择该 Skill，但发现不等于激活。长对话结束后，准备生成 commit、PR、发布标题或交付说明时，最好显式指定它。Codex 的文档化语法是 `$no-negative-echo`，Claude Code 是 `/no-negative-echo`；其他宿主按其当前的原生方式选择 Skill，或在提示词中直接点名并验证实际激活，不要仅从输出措辞推断。

```text
使用 no-negative-echo Skill。
根据最终 diff 写 commit subject、PR 标题、PR 正文和交付说明。
```

文章场景可以这样用：

```text
使用 no-negative-echo Skill。
根据最终保留的正文重写标题和开篇。
```

### 它会检查哪些位置

| 位置 | 带着纠正过程 | 只写最终结果 |
|---|---|---|
| PR 标题 | `新增搜索（不用弹窗）` | `新增侧边栏搜索` |
| 代码注释 | `// 不再每秒检查` | `// 数据变化后刷新` |
| Commit | `搜索改版：删除弹窗方案，改成侧边栏` | `新增侧边栏搜索` |
| 文章标题 | `番茄炒蛋：不加东坡肉版` | `番茄炒蛋做法` |
| 交付说明 | `已去掉红色按钮和旧说明` | `提交按钮改为蓝色，测试通过` |

<a id="boundary"></a>

## 判断边界

这个 Skill 不做关键词清零。真实发生过的删除、迁移要求和安全信息，本来就应该写清楚。

| 内容 | 处理方式 |
|---|---|
| 只在聊天里讨论过、从未进入基线的方案 | 省略 |
| 未保存的助手草稿和中间尝试 | 省略 |
| 用户纠正过的标题框架、语气和自证句 | 省略 |
| 任务开始前已有的用户未提交改动 | 保留其归属，不算作本次成果或被否草稿 |
| 已经发送、发布、删除、迁移或部分执行的外部操作 | 按实际结果和风险保留 |
| 已发布的 v1 API 确实被删除 | 保留，并写清迁移方式 |
| 过敏原、安全规则、法律或兼容性要求 | 保留 |
| 用户明确要求的方案比较、审计和逐字引用 | 保留 |
| 已确认且能防止重复踩坑的架构决策 | 放入 ADR 等合适位置，不扩散到无关标题 |

每个输出位置都要单独判断：

- 没参与过这轮对话的读者，是否需要这条信息？
- 省略它，是否会带来安全风险、事实错误、误导、兼容性或合规问题？
- 它是否真实存在于权威基线中，而且当前产物需要说明这项变化？

第一项是前提。在此基础上，第二项或第三项至少满足一项，这条信息才保留。用户明确要求的方案比较、审计、逐字引用、发布记录或迁移说明也应保留。

<p align="center">
  <img src="./no-negative-echo/assets/decision-boundary.png" width="920" alt="工作会话中的草稿和修改痕迹留在筛选边界之外，只有一份干净的最终文档进入交付">
</p>

权威基线要按输出位置选择：commit 看父 tree 或 staged diff，PR 看目标分支 merge-base，发布说明看上一个已发布版本，交付说明还要考虑任务开始时的完整工作区和实际执行过的外部操作。未提交不等于被否；用户原有改动必须单独保留归属。助手草稿、未采用补丁和纯本地临时尝试才属于会话历史。

## 能力边界

这是提示词层的缓解措施，不是确定性过滤器。它能降低会话残留进入成品的概率，但不能保证每次都拦住。

- Skill 是否被发现、隐式选中或显式激活，以及它获得的工具权限，都由宿主和当前 surface/version 决定。重要交付应显式指定并保留可观测证据。
- Skill 无法擦除模型已经读到的上下文，也控制不了终端输出、工具日志和宿主生成的界面文案。
- 自带扫描器只提供原始文本、文件名和可疑 Unicode 的确定性检查；传入 `--root` 时会检查相对路径中的目录名，否则只检查 basename。它不是渲染、语义、媒体或秘密扫描器，`PASS` 不能单独证明最终交付干净。
- producer 或 validator 的上下文继承模式无法确认时，只能称为 best-effort，不能声称上下文已隔离或经过独立验证。
- 它处理最终交付里的会话残留，不负责阻止模型一开始做多余的实现。
- 凭据、个人信息和其他敏感数据仍应使用专门的密钥扫描或合规工具检查。

安装矩阵只证明各厂商文档声明的包格式和发现路径兼容，不证明本 Skill 在该宿主上会被正确路由，也不证明激活后的行为有效。对没有原生 Agent Skills 的 Agent，手动读取只是 best-effort 回退，不得标记为原生激活。`agents/openai.yaml` 是 OpenAI surface 的可选界面元数据，不是 Agent Skills 公共行为的前提。

<a id="evaluation"></a>

## 开发和评测

运行本地测试：

```bash
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

安装目录 [`no-negative-echo/`](no-negative-echo/) 只放运行时文件。评测提示和答案放在 [`evals/`](evals/) 里，避免开发用例跟着 Skill 一起进入模型上下文。

公开用例只用于开发，跑通不等于问题消失。仓库提供无 Skill、固定对照提示、显式调用和隐式调用的评测协议，要求把 routing 与激活后的行为分开报告，并使用独立裁判、冻结输出、真实 surface 回读和未公开 holdout。一次完整评测只需预先声明一个 reference host，并在四个条件中固定该宿主及版本；不需要把所有 Agent 都测一遍。其他宿主只作独立、可选的 replication，不与主评测混池。评分器每次只验证一个条件，`--reference-host` 也只是申报标签；完整的四条件一致性必须由调度器和冻结 manifest 审计保证。CI 只运行确定性脚本与评分器测试，不运行 Agent 模型评测，也不产生有效性百分比。格式和统计限制见 [`evaluation-protocol.md`](evals/evaluation-protocol.md)。

<details>
<summary>仓库结构</summary>

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

## 许可证

本项目采用 [MIT License](LICENSE)。允许商用、修改、分发和闭源再发布，但必须保留原始版权与许可声明。

<a id="feedback"></a>

## 反馈

如果遇到新的「此地无银三百两」输出，提 Issue 时请带上原始请求、实际输出、期望输出和出现位置，再说明当时是显式调用还是隐式触发。提交前，请先替换真实凭据、个人信息和内部项目名。
