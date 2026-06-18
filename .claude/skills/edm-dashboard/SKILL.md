---
name: edm-dashboard
description: EDM 邮件状态看板 — 分析 EDM 文件夹邮件，按 conversation_id 分组展示处理进度
model: sonnet
---

# EDM 邮件状态看板

## 依赖

- EWS DLL（PowerShell 脚本需要）
- Python 3（启动 HTTP 看板，无第三方依赖）

## 使用流程

### 1. 运行 PowerShell 脚本提取邮件数据

```powershell
.\edm_mail_analyzer.ps1
```

输出到 `c:\temp\edmmailanalyzer.json`，每条约包含：

```json
{
  "date": "2026-06-18 11:35:32",
  "subject": "[EDM test and distribution] Incident 818878381 ...",
  "sender": "lu.xinyu@oe.21vianet.com",
  "conversation_id": "AAQkA...",
  "conversation_step": 1,
  "conversation_total": 7
}
```

> `conversation_step` 按时间正序递增（1 = 最早邮件，total = 最新回复）

### 2. 将 JSON 文件放到 AgentProject 目录

```powershell
Copy-Item c:\temp\edmmailanalyzer.json C:\Users\SI-Agent\AgentProject\
```

### 3. 启动看板

```bash
python .claude/skills/edm-dashboard/edm_dashboard.py --port 8765 --json-file edmmailanalyzer.json
```

浏览器打开 `http://localhost:8765/`

## 看板功能

- 仅展示 subject 含 `[EDM test and distribution]` 的邮件
- 每行一个 conversation，显示 SN 编号、进度条、状态标签
- 展开后可看 7 步流程：
  - Step 1: EDM请求发起
  - Step 2: 测试已发送等待确认审批
  - Step 3: Peer reviewed, 等待Nanbo审批
  - Step 4: 审批完成
  - Step 5: 审批结果告知PS
  - Step 6: Formal EDM已发送
  - Step 7: 确认收到最终结束

## 文件

- `edm_dashboard.py` — Python HTTP 看板服务
- `edm_mail_analyzer.ps1` — PowerShell EWS 邮件分析脚本
