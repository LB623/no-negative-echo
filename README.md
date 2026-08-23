<p align="center">
  <img src="./no-negative-echo/assets/icon.png" width="168" alt="No Negative Echo icon">
</p>

<h1 align="center">No Negative Echo</h1>

<p align="center"><strong>让 Agent 交付最终结果，而非复述被否方案。</strong></p>

<p align="center"><em>Ship the result, not the conversation.</em></p>

<p align="center">
  <strong>中文</strong> · <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml"><img src="https://github.com/LB623/no-negative-echo/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/LB623/no-negative-echo/stargazers"><img src="https://img.shields.io/github/stars/LB623/no-negative-echo?style=flat&amp;logo=github" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/LB623/no-negative-echo" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
</p>

## 它解决什么问题

Agent 在迭代中修正了方案，却把被否内容带进最终标题、注释、commit、PR 或交付说明：

```diff
- 标题：番茄炒蛋（没有东坡肉）
+ 标题：番茄炒蛋
```

`no-negative-echo` 是一个 [Agent Skills](https://agentskills.io/specification) 格式的 Skill。它要求 Agent 从已采用、已验证的最终状态重新生成交付文案，并在多个交付面检查会话残留。

适用场景：

- 根据最终 diff 写 commit、PR 标题和说明
- 重写文章标题、开篇、UI 文案或交付说明
- 长对话、多人协作或多轮修改后的最终收口

## Star 趋势

[![GitHub Star 趋势](docs/assets/star-history.svg)](https://github.com/LB623/no-negative-echo/stargazers)

## 安装

让具备网络、终端和文件权限的 Agent 按安装合约执行：

```text
请安装 no-negative-echo Skill：
https://raw.githubusercontent.com/LB623/no-negative-echo/main/INSTALL.md
装完告诉我安装结果，以及是否需要开启新会话或重启。无法验证时，不要宣称安装成功。
```

本地安装示例（Codex）：

```bash
git clone https://github.com/LB623/no-negative-echo.git
cd no-negative-echo
python3 -I -m unittest discover -s tests -p 'test_*.py'
python3 -I scripts/install_skill.py \
  --expected-provenance-sha256 d42280b21f519ea00e417c68f31c68ca3d7faae607faf6dcb6e04beeff9c5ed6 \
  --discovery-root "$HOME/.agents/skills" \
  --agent codex
```

其他宿主、项目级安装、升级与完整安全约束见 [INSTALL.md](INSTALL.md)。

## 使用

在最终生成 commit、PR、发布说明或交付说明前显式调用：

```text
使用 no-negative-echo Skill。
根据最终 diff 写 commit subject、PR 标题、PR 正文和交付说明。
```

文章场景：

```text
使用 no-negative-echo Skill。
根据最终保留的正文重写标题和开篇。
```

## 判断原则

| 内容 | 处理 |
|---|---|
| 只在会话中讨论、从未进入最终基线的方案 | 省略 |
| 助手草稿、中间尝试、用户的措辞纠正 | 省略 |
| 已发布的 API 删除、迁移与外部操作 | 如实说明 |
| 安全、法律、兼容性、审计所需事实 | 保留 |
| 用户明确要求的对比、引用或决策记录 | 保留 |
| 任务开始前已有的用户改动 | 保留归属，不算作本次成果 |

每个输出位置单独问三个问题：

1. 不知道本轮对话的读者需要这条信息吗？
2. 省略会造成事实错误、安全风险、误导或兼容问题吗？
3. 它是否是权威基线中的真实变化，且当前交付面需要解释它？

仅仅“出现过”或“被否过”不是保留理由。

## 边界

这是提示词层的缓解措施，不是确定性过滤器：

- Skill 被发现不等于已激活；重要交付应显式调用。
- 它不能清除模型已读上下文，也不能控制工具日志或宿主 UI。
- 内置扫描器只能做文本、文件名和可疑 Unicode 检查；`PASS` 不代表语义检查完成。
- 不要为通过检查而修改 API、迁移、测试、快照或现有用户改动。
- 凭据、隐私与合规问题仍应交给专门工具处理。

默认流程见 [SKILL.md](no-negative-echo/SKILL.md)；敏感信息、公开发布与严格验收才会按需读取 [high-assurance-finalization.md](no-negative-echo/references/high-assurance-finalization.md)。

## 开发与评测

```bash
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

评测协议与公开用例位于 [`evals/`](evals/)。CI 只运行确定性脚本和评分器测试，不将其表述为模型行为有效性结论。

## 相关资料

- [安装合约](INSTALL.md)
- [设计背景](BACKGROUND.md)
- [评测协议](evals/evaluation-protocol.md)
- [许可证](LICENSE)

## 反馈

提 Issue 时请提供：原始请求、实际输出、期望输出、发生位置，以及当时是显式调用还是隐式触发。提交前请移除凭据、个人信息和内部项目名。

本项目采用 [MIT License](LICENSE)。
