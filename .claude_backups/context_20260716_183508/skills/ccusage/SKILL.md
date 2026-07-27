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

## Database

SQLite 数据库位置：`~/.cc-switch/cc-switch.db`
