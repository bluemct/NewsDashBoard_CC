---
name: usage
description: Query recent Claude Code session token usage — shows session count, turns, input, output tokens from the usage database
---

# Claude Code Usage

查询最近 session 的 Token 使用量（Turns、Input、Output）。

## Usage

```bash
python .claude/skills/usage/usage.py [--n N] [--model MODEL] [--project PROJECT]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--n` | 10 | 显示最近 N 个 session |
| `--model` | 无 | 按模型过滤 |
| `--project` | 无 | 按项目过滤 |

输出表格包含 Session、Project、Last Active、Model、Turns、Input、Output Tokens。

## Database

SQLite 数据库位置：`~/.claude/usage.db`

由 [claude-usage](https://github.com/phuryn/claude-usage) 项目扫描并维护。
