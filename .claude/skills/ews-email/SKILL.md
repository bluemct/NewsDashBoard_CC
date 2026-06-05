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
# 声明需要的属性
$propertySet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body,
    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,
    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId
)

# 绑定邮件
$email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind(
    $exchService, $evt.ItemId, $propertySet
)

# 提取字段
$subject = $email.Subject
$sender = $email.Sender.Address.ToLower()
$conversationId = $email.ConversationId.UniqueId
$body = $email.Body.ToString()
```

## Related Skills

- `ews-connect` — 建立 EWS 连接
- `email-html2text` — 将 Body HTML 转换为纯文本