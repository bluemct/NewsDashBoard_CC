---
name: edm-agent-sendmail
description: Send email via SMTP — reads config from edm_email_config.json, supports CLI overrides
capabilities:
  - SMTP email sending
  - JSON config (sender, recipients, subject, body)
  - CLI overrides (--subject, --body)
---

## EDM Agent Sendmail Skill

通过 SMTP 发送邮件。配置来自 `edm_email_config.json`，支持命令行覆盖标题和正文。

### 配置文件

`edm_email_config.json`（与脚本同级目录）：

```json
{
  "smtp_server": "svr-ex2019-04.21vianet.com",
  "smtp_port": 25,
  "sender": "ps-tier2.support@oe.21vianet.com",
  "recipients": {
    "to": ["ma.chuntao@oe.21vianet.com"],
    "cc": [],
    "bcc": []
  },
  "subject": "EDM Email",
  "body": ""
}
```

### 用法

```bash
# 使用配置中的默认值发送
python edm_agent_send_email.py

# 覆盖标题
python edm_agent_send_email.py --subject "自定义标题"

# 覆盖正文（HTML 或纯文本）
python edm_agent_send_email.py --body "这是一段测试内容"

# 同时覆盖标题和正文
python edm_agent_send_email.py --subject "测试" --body "<h1>HTML 内容</h1>"
```

### 参数

| 参数 | 必填 | 描述 |
|------|------|------|
| `--subject` | 否 | 覆盖邮件标题 |
| `--body` | 否 | 覆盖邮件正文（HTML 或纯文本） |

### 正文优先级

1. `--body` CLI 参数
2. `edm_email_config.json` 中的 `body` 字段
3. 默认占位符（含时间戳）

### 无 VBS 运行（Windows 双击）

```
双击 edm_agent_send_email.vbs
```

VBS 会自动查找 Python 并执行脚本，弹窗显示结果。

### 依赖

- Python 3.x（标准库，无需 pip install）
