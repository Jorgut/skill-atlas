# Closeout 新手使用教程

**中文** | [English](GETTING_STARTED.en.md) | [Русский](GETTING_STARTED.ru.md)

Closeout 用于项目完成一个阶段后的“事实收尾”：核对代码、实际运行结果、文档、Agent 规则、获准维护的记忆和工作区残留是否一致。

它不是普通的文件整理工具，也不会在未经确认时删除文件、分支或 worktree。

## 1. 安装

打开终端，逐行运行：

```bash
git clone https://github.com/Jorgut/closeout-skill.git
cd closeout-skill
python3 scripts/install_closeout.py --all-platforms --commands
```

第三条命令只显示安装计划。确认没有路径冲突后再正式安装：

```bash
python3 scripts/install_closeout.py \
  --all-platforms \
  --commands \
  --apply \
  --confirm
```

安装后完全退出并重新打开 Codex、OpenCode 或 Claude Code。

## 2. 在哪里输入命令

### Codex

Codex 不会显示自定义 `/closeout`。在对话框输入：

```text
$closeout
```

或者直接说：

```text
使用 Closeout 检查这个项目的代码、README 和 Agent 规则是否一致。
```

### OpenCode 或 Claude Code

在对话框输入：

```text
/closeout
```

也可以使用自然语言：

```text
净化一下这个项目，先不要删除任何文件。
```

## 3. 第一次安全试用

建议先在一个有 Git、README 和少量代码的小项目里测试。

1. 用 Agent 打开项目目录。
2. 确保项目当前改动已经保存。
3. 输入：

```text
$closeout docs-sync，只核对代码、README 和规则文件，不修改记忆，不删除任何内容。
```

OpenCode/Claude Code 使用：

```text
/closeout docs-sync，只核对代码、README 和规则文件，不修改记忆，不删除任何内容。
```

4. 阅读报告中的六个事实面状态。
5. 如果报告列出删除候选，不确认就不会删除。

## 4. 四种模式怎么选

### `docs-sync`：只同步文档和规则

适合日常开发结束：

```text
$closeout docs-sync，检查 README 里的启动命令、端口和功能是否与代码一致。
```

### `knowledge-closeout`：完整知识收尾

适合一个功能或阶段完成，需要给下次会话留下准确上下文：

```text
$closeout knowledge-closeout，同步文档、规则和当前平台允许维护的记忆。
```

没有明确授权或平台入口时，Closeout 不应自行写入记忆。

### `release-closeout`：发布收尾

适合 PR 合并、部署或正式发布：

```text
$closeout release-closeout，确认代码、远端、部署和线上页面分别处于什么状态。
```

Closeout 会区分：

- `draft`
- `PR`
- `merged`
- `deployed`
- `live-verified`
- `knowledge-closed`
- `cleaned`

“已经合并”不等于“已经部署”，“已经部署”也不等于“线上验证通过”。

### `workspace-audit`：检查多个项目

只有确实要审查整个 workspace 时才使用：

```text
$closeout workspace-audit，只读检查这些项目的规则和文档冲突，不跨项目写入。
```

## 5. 如何读懂结果

Closeout 会给六个事实面分别标状态：

| 事实面 | 检查内容 |
| --- | --- |
| `code` | 源码、配置、schema 和测试实际实现了什么 |
| `runtime` | 用户或线上服务当前真正得到什么 |
| `docs` | README 和文档是否准确 |
| `rules` | AGENTS.md、CLAUDE.md 等规则是否有效 |
| `memory` | 获准维护的跨会话记忆是否准确 |
| `workspace` | 临时文件、旧副本、分支或 worktree 是否仍需处理 |

常见状态：

- `verified-current`：已经核对，当前正确
- `changed-and-verified`：已修正并重新验证
- `pending`：目前无法验证，不能假装完成
- `out-of-scope`：不属于本次范围
- `not-applicable`：这个项目不适用，例如没有部署环境

## 6. 删除和清理为什么要确认两次

Closeout 会先给出完整报告和删除候选，例如旧计划、备份副本、临时 worktree。只有你看完报告后再次明确确认，它才能执行清理。

正确流程：

```text
用户：$closeout knowledge-closeout
Agent：给出事实报告和待删除候选
用户：我已阅读报告，确认只删除候选 A 和 B，保留 C
Agent：执行删除，再重新审计并补充结果
```

最初一句“做完顺便清理”不能替代最终确认，这是为了避免误删唯一副本。

## 7. 实用示例

### 功能开发结束

```text
$closeout docs-sync，核对刚完成的登录功能、环境变量说明和测试命令。
```

### 准备交接给同事

```text
$closeout knowledge-closeout，为新接手者准备准确的项目状态；列出未完成事项，但不要编造完成状态。
```

### 发布后检查

```text
$closeout release-closeout，检查 GitHub 提交、部署记录和真实线上页面；无法访问的项目标 pending。
```

### 只检查，不修改

```text
$closeout workspace-audit，全程只读，不修改文件、记忆、分支或 worktree。
```

## 8. 常见问题

### 输入 `/` 看不到 Closeout

- Codex 使用 `$closeout`，不会显示自定义 `/closeout`。
- OpenCode/Claude Code 安装时必须带 `--commands`。
- 安装后需要完全重启应用。
- 检查命令软链接：

```bash
ls -l ~/.config/opencode/commands/closeout.md
ls -l ~/.claude/commands/closeout.md
```

### Closeout 没有自动删除候选文件

这是正常安全机制。先阅读预清理报告，再明确回复允许删除哪些项目。

### 为什么有 `pending`

`pending` 表示缺少真实证据，例如无法访问线上环境、没有权限读取远端或测试未运行。它比虚假的“全部完成”更可靠。

### 如何确认本机安装成功

```bash
ls -l ~/.agents/skills/closeout/SKILL.md
ls -l ~/.codex/skills/closeout
ls -l ~/.config/opencode/skills/closeout
ls -l ~/.claude/skills/closeout
```

如果后三项显示指向同一个 canonical 目录的软链接，说明多平台正在共享同一份 Skill。
