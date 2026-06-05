---
name: ews-subscribe
description: Create streaming subscription to listen for new mail events on Outlook folders
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: Microsoft.Exchange.WebServices.dll
---

# EWS Subscribe Skill

创建流式订阅，实时监听指定文件夹的新邮件事件。

## Prerequisites

- `$exchService` 对象（来自 `ews-connect`）
- 文件夹列表（来自 `ews-folder`）

## Usage

```powershell
# 加载 Skill 脚本
. .claude/skills/ews-folder/Get-EwsFolder.ps1
. .claude/skills/ews-subscribe/Start-EwsSubscription.ps1

# 获取要监听的文件夹
$folders = @(
    Get-EwsFolder -Name "Inbox" -ExchangeService $exchService
    Get-EwsFolder -Name "Sent Items" -ExchangeService $exchService
    Get-EwsFolder -Name "MyCustomFolder" -ExchangeService $exchService
) | Where-Object { $_ }

# 启动监听
Start-EwsSubscription `
    -ExchangeService $exchService `
    -Folders $folders `
    -MyAddress "user@company.com"
```

## Available Event Types

| 事件类型 | 说明 |
|---------|------|
| `NewMail` | 新邮件到达 |
| `Modified` | 邮件被修改 |
| `Deleted` | 邮件被删除 |
| `Moved` | 邮件被移动 |
| `Copied` | 邮件被复制 |

## Related Skills

- `ews-connect` — 建立 EWS 连接
- `ews-folder` — 获取要监听的文件夹
- `ews-email` — 从事件中获取邮件详情