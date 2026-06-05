---
name: ews-folder
description: Find Outlook email folders by name using EWS
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: Microsoft.Exchange.WebServices.dll
---

# EWS Folder Skill

按名称查找 Outlook 邮箱文件夹，支持系统文件夹和自定义文件夹。

## Prerequisites

- `$exchService` 对象（来自 `ews-connect`）

## Usage

```powershell
# 加载 Skill 脚本
. .claude/skills/ews-folder/Get-EwsFolder.ps1

# 使用示例
$inbox = Get-EwsFolder -Name "Inbox" -ExchangeService $exchService
$sent = Get-EwsFolder -Name "Sent Items" -ExchangeService $exchService
$custom = Get-EwsFolder -Name "EDM" -ExchangeService $exchService
```

## Output

返回 `Folder` 对象，可用于订阅或遍历邮件。

## Common Well-Known Folders

| 名称 | WellKnownFolderName 枚举 |
|------|-------------------------|
| Inbox | `WellKnownFolderName::Inbox` |
| Sent Items | `WellKnownFolderName::SentItems` |
| Deleted Items | `WellKnownFolderName::DeletedItems` |
| Drafts | `WellKnownFolderName::Drafts` |
| Junk Email | `WellKnownFolderName::JunkEmail` |

## Related Skills

- `ews-connect` — 建立 EWS 连接
- `ews-subscribe` — 订阅文件夹新邮件事件
