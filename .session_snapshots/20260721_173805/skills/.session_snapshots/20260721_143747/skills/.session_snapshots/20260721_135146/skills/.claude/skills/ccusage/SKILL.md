# CC Usage

查询 CC Switch 代理日志的每轮 Token 使用量（Input、Output、Latency）。

直接从 `~/.cc-switch/cc-switch.db` 的 `proxy_request_logs` 表读取，数据实时可用，无需等 session 结束。

## Usage

```bash
python .claude/skills/ccusage/ccusage.py [--n N] [--session SESSION_ID] [--model MODEL]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--n` | 20 | 显示最近 N 条记录 |
| `--session` | 当前 session | 指定 session_id（不指定则自动检测最新 session） |
| `--model` | 无 | 按模型过滤（opus / haiku） |

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

## Database

SQLite 数据库位置：`~/.cc-switch/cc-switch.db`
