# Skill Atlas 新手使用教程

**中文** | [English](GETTING_STARTED.en.md) | [Русский](GETTING_STARTED.ru.md)

这份教程面向第一次使用 Agent Skill、不会配置软链接、也不熟悉命令行的用户。按顺序操作即可。

## 1. 先理解它能做什么

Skill Atlas 有五组能力：

| 你想做什么 | 使用命令 |
| --- | --- |
| 查看电脑里装了哪些 Skill | `manage scan` |
| 检查重复、更新和软链接 | `manage status`、`manage dedupe`、`manage sync` |
| 为自己的 Skill 找竞品 | `discover competitors` |
| 不知道做产品需要哪些 Skill | `recommend product` 或 `recommend task` |
| 组合多个 Skill 完成复杂工作 | `orchestrate plan` 或 `orchestrate validate` |
| 定期重新检查竞品变化 | `monitor` |

默认情况下它只检查和生成计划，不会偷偷安装、删除或替换 Skill。

## 2. 安装

打开终端，逐行运行：

```bash
git clone https://github.com/Jorgut/skill-atlas.git
cd skill-atlas
python3 scripts/skill_atlas.py install --all-platforms --commands
```

最后一条只是预览。确认输出里的目标目录没有冲突后，正式安装：

```bash
python3 scripts/skill_atlas.py install \
  --all-platforms \
  --commands \
  --apply \
  --confirm
```

安装完成后，完全退出并重新打开 Codex、OpenCode 或 Claude Code。

### 安装实际做了什么

- 主文件只保留一份：`~/.agents/skills/skill-atlas`
- Codex、OpenCode、Claude Code 的 Skill 目录通过软链接指向主文件
- OpenCode 和 Claude Code 注册 `/skill-atlas`
- Codex 使用 `$skill-atlas`，不会出现自定义 `/skill-atlas`

## 3. 第一次使用

先扫描本机 Skill。

### Codex

在对话框输入：

```text
$skill-atlas manage scan
```

也可以直接说：

```text
使用 Skill Atlas 扫描本机所有 Skill，并告诉我哪些是重复副本或软链接。
```

### OpenCode 或 Claude Code

在对话框输入：

```text
/skill-atlas manage scan
```

如果 `/skill-atlas` 没出现在菜单里，仍可使用自然语言：

```text
使用 Skill Atlas 扫描本机所有 Skill。
```

### 直接从终端运行

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py manage scan
```

## 4. 常用场景

### 场景 A：检查重复和更新

```text
$skill-atlas manage status
$skill-atlas manage dedupe
$skill-atlas manage sync
```

OpenCode 和 Claude Code 把 `$skill-atlas` 换成 `/skill-atlas`。

这些命令只生成报告或计划。看到 `Consolidation Suggestions` 不代表已经创建软链接。

### 场景 B：给自己的 Skill 找竞品

```text
$skill-atlas discover competitors closeout
```

Skill Atlas 会保护 `user-authored` Skill：竞品只用于学习和比较，不会自动替换你的作品。

### 场景 C：不知道产品需要哪些 Skill

```text
$skill-atlas recommend product 我想制作一款汽车 HMI 设计工具
```

它会区分：

- 本机现在能用的 Skill
- 建议组合顺序
- 缺失能力
- 需要另外研究的模型、MCP、插件或专业软件接口

再检查组合是否合理：

```text
$skill-atlas orchestrate validate 我想制作一款汽车 HMI 设计工具
```

### 场景 D：Rhino、Blender、SketchUp 等专业软件

```text
$skill-atlas recommend tool 建筑师使用 Rhino、Grasshopper、Blender 和 SketchUp 辅助建模
```

结果可能同时包含 Skill、桌面软件、脚本 API、插件和 MCP。它们不是同一种东西，安装前要分别确认。

## 5. 定期竞品对比

### 第一步：建立监控

```text
$skill-atlas monitor add closeout --interval monthly
```

可选周期：`daily`、`weekly`、`monthly`、`quarterly`。

### 第二步：查看哪些监控到期

```text
$skill-atlas monitor due
```

### 第三步：让 Agent 真正执行研究

不要只在终端运行 `monitor run` 就认为全网对比完成。正确的对话请求是：

```text
$skill-atlas monitor run closeout。请执行研究包中的联网检索，检查来源、作者、许可证、维护活跃度、兼容性和安全性，完成后保存本期结果并和上一期比较。
```

Agent 应完成两段工作：

1. Skill Atlas 生成本期研究包。
2. Agent 联网搜索和审查候选，再把结果录入历史快照。

如果只生成了 `research-required`，说明第一段完成了，第二段还没有完成。此时监控仍保持 `due`，不会被误标成已经比较。

### 第四步：查看历史

```text
$skill-atlas monitor history closeout
```

历史会显示候选的新增、消失和保持不变情况。默认数据目录是：

```text
~/.local/share/skill-atlas
```

### “定期”是否会自动后台运行

Skill Atlas 本身不会偷偷常驻后台。要实现无人值守，需要让 Codex Automation、OpenCode Automation、`cron` 或 macOS `launchd` 定期唤醒 Agent。

最简单的做法是建立一个每月任务，任务内容写成：

```text
使用 Skill Atlas 检查 monitor due。对所有到期监控执行完整联网竞品研究、安全审查和历史差异记录；不要替换用户自研 Skill。
```

## 6. 如何读懂安全状态

- `read-only`：只检查或生成计划，没有修改文件
- `research-required`：研究包已生成，但联网对比尚未完成
- `completed`：经过审查的结果已录入快照
- `user-authored`：用户自研 Skill，只作为竞品比较对象，不替换
- `external-maintained`：第三方维护，可检查上游更新，但更新前必须审查
- `tool-bundled/cache`：平台管理的缓存，不应直接修改
- `unknown-local`：来源不明，更新前先确认作者和仓库

## 7. 常见问题

### 输入 `/` 看不到 Skill Atlas

1. Codex 本来就不提供自定义 `/skill-atlas`，请用 `$skill-atlas` 或自然语言。
2. OpenCode/Claude Code 需要安装时带 `--commands`。
3. 安装后要完全重启 Agent 应用。
4. 检查命令文件是否存在：

```bash
ls -l ~/.config/opencode/commands/skill-atlas.md
ls -l ~/.claude/commands/skill-atlas.md
```

### 提示命令不存在

直接使用绝对路径验证：

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py --help
```

### 报告说有重复，但没有自动合并

这是正常的安全行为。先运行 `manage sync` 查看计划，再明确要求 Agent 根据计划操作。覆盖、删除和创建软链接都必须再次确认。

### 如何更新 Skill Atlas

先查看版本：

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py manage self status
```

当前 beta 版本不会偷偷联网自更新。应先获取并审查新版，再使用 `manage self update` 预览和应用。
