---
name: edm-agent-download
description: Scan EDM folder for forwarded emails from Michael Ma marked with "EDM Agent" keyword, download to EDM/Temp/
capabilities:
  - EWS folder scanning
  - Sender + keyword filtering
  - MIME download to .eml
---

## EDM Agent Download Skill

扫描 EDM 邮箱文件夹，找出 Michael Ma (`ma.chuntao`) 转发的带有 "EDM Agent" 关键词的邮件，下载为 `.eml` 到 `EDM/Temp/`。

### 匹配条件

| 条件 | 值 |
|------|-----|
| 发件人 | `ma.chuntao@oe.21vianet.com` |
| 正文关键词 | `EDM Agent` |
| 附件 | 有附件（HasAttachments=true） |

### 输出

- `EDM/Temp/SN-xxxxx_email.eml` — 外层转发邮件
- 返回 JSON: `{found: true/false, count: N, files: [...]}`

### 用法

```python
from .claude.skills.edm-agent-download.edm_agent_download import scan_and_download
result = scan_and_download()
```

### 配置文件

- `.edm_agent_config.json` — EWS 凭据 + EDM 文件夹
