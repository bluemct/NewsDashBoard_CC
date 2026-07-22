# CC Usage

查询 CC Switch 代理日志的每轮 Token 使用量（Input、Output、Latency）。

直接从 `~/.cc-switch/cc-switch.db` 的 `proxy_request_logs` 表读取，数据实时可用，无需等 session 结束。

## Usage

```bash
python .claude/skills/ccusage/ccusage.py [--n N] [--session SESSION_ID] [--model MODEL] [--latest]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--n` | 2 | 显示最近 N 条记录（仅 `--model` 模式下生效） |
| `--session` | 当前 session | 指定 session_id（不指定则自动检测最新 session） |
| `--model` | 无 | 按模型过滤（opus / sonnet / haiku） |
| `--latest` | 否 | 显示每个模型最近一轮的 token 用量 |

### 默认输出（每模型最新一轮 + 上下文用量进度条）

不传参数时，显示每个模型（Sonnet、Opus、Haiku）最近一轮的 input/output token 用量，并附带上下文用量进度条（上限 262.1K）：

```
=== Context Usage Bar ===
  Opus     In [███████████████░░░░░░░░░░░░░░░]  49.4% (129.5K)
           Out[░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   0.0% (86)
  Sonnet   In [█████░░░░░░░░░░░░░░░░░░░░░░░░░]  17.2% (45.1K)
           Out[░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   0.2% (571)
```

进度条颜色：`<60%` 绿色 → `60-80%` 黄色 → `≥80%` 红色

## Context Guard

后台守护进程，每 30 秒轮询 CC Switch 数据库，预估上下文用量，接近 262K 限制时自动备份 skill 和 memory。

```bash
python .claude/skills/ccusage/context_guard.py                 # 启动 daemon（默认 30s 轮询）
python .claude/skills/ccusage/context_guard.py --interval 60   # 每 60s 轮询
python .claude/skills/ccusage/context_guard.py --status        # 一次显示上下文用量
python .claude/skills/ccusage/context_guard.py --backup        # 立即手动备份
python .claude/skills/ccusage/context_guard.py --check         # 一次检查+自动备份
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--interval` | 30 | 轮询间隔（秒） |
| `--limit` | 262144 | 上下文限制（tokens） |
| `--warn` | 80 | 预警阈值（百分比），超过自动备份 |
| `--session` | 自动检测 | 指定 session_id |

### 行为

- **< 60%**：正常轮询（每 30s）
- **60-80%**：加速轮询（每 10s）
- **≥ 80%**：触发自动备份（skills/、memory/、git status），仅备份一次
- **下一轮预估超限**：立即触发备份
- 备份保存到 `.claude_backups/context_YYYYMMDD_HHMMSS/`，保留最近 5 份

## Floating Monitor (GUI)

悬浮窗，每 5 秒轮询 CC Switch 数据库，按模型显示最新 token 用量进度条。

```bash
python .claude/skills/ccusage/usage_monitor.py
python .claude/skills/ccusage/usage_monitor.py --interval 3  # 3s poll
python .claude/skills/ccusage/usage_monitor.py --limit 1000000  # 1M context (Opus 1M)
```

**功能：**
- 每 5 秒自动刷新 session（自动检测最新活跃 session，无需手动重开窗口）
- 底部显示 `Session: <name>`（优先读取 `/rename` 后的名称，取最新一次 rename；无 rename 则显示 session ID 前 8 位）
- 无边框圆角（半径 20）、暗色主题、80% 不透明（alpha 0.8）
- 窗口置顶，支持拖拽移动（`winfo_pointerx/y` + `_dragging` 锁防止拖拽期间位置重置）
- 模型数据按名称匹配（Opus/Sonnet/Haiku），不再依赖数据库返回顺序
- 进度条颜色：`<60%` 绿色 → `60-80%` 黄色 → `≥80%` 红色
