---
name: ews-email
description: Retrieve email details by ItemId using EWS EmailMessage.Bind
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: Microsoft.Exchange.WebServices.dll
---

# EWS Email Bind Skill

通过邮件 ItemId 获取指定邮件的详情。

## Prerequisites

- `$exchService` 对象（来自 `ews-connect`）
- 邮件 `$evt.ItemId`

## Usage

```powershell
# 加载 Skill 脚本
. .claude/skills/ews-email/Get-EwsEmail.ps1

# 获取邮件详情（默认属性）
$email = Get-EwsEmail -ItemId $evt.ItemId -ExchangeService $exchService

# 提取字段
$subject = $email.Subject
$sender = $email.Sender.Address.ToLower()
$conversationId = $email.ConversationId.UniqueId
$body = $email.Body.ToString()

# 只获取指定属性（更快）
$email = Get-EwsEmail -ItemId $evt.ItemId -ExchangeService $exchService `
    -Properties @('Subject', 'Sender')
```

## Related Skills

- `ews-connect` — 建立 EWS 连接
- `email-html2text` — 将 Body HTML 转换为纯文本