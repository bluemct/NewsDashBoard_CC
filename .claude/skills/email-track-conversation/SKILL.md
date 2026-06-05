---
name: email-track-conversation
description: Track email conversations by ConversationId to distinguish sent mails from replies
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: none
---

# Email Track Conversation Skill

通过 ConversationId 追踪邮件对话线程，区分自己发送的邮件和收到的回复邮件。

## Prerequisites

- `$email` 对象（来自 `ews-email`，需包含 `Sender` 和 `ConversationId`）

## Usage

```powershell
# 初始化追踪字典（全局作用域）
$Global:InitiatedConversations = @{}

# 当前邮箱地址（用于判断是否是自己发送的邮件）
$myAddress = "your@email.com".ToLower()

# 获取邮件信息
$sender = $email.Sender.Address.ToLower()
$conversationId = $email.ConversationId.UniqueId

if ($sender -eq $myAddress) {
    # 自己发送的邮件 → 记录该对话
    $Global:InitiatedConversations[$conversationId] = $true
    Write-Host "Sent mail, tracked conversation: $conversationId"
}
elseif ($Global:InitiatedConversations.ContainsKey($conversationId)) {
    # 收到的回复邮件（对话已追踪）
    Write-Host "Reply received for conversation: $conversationId"
    Write-Host "Sender: $sender"
    # 继续处理回复内容（如提取工单号）
}
else {
    # 其他邮件（非自己发起的对话）
    Write-Host "Untracked mail from: $sender"
    Write-Host "ConversationId: $conversationId"
    Write-Host "Subject: $($email.Subject)"
}
```

## Logic Flow

```
收到邮件事件
  └─ 是本人发送？
       ├─ 是 → 记录 ConversationId → 跳过
       └─ 否 → ConversationId 已记录？
            ├─ 是 → 这是回复 → 处理内容
            └─ 否 → 其他邮件 → 仅记录日志
```

## Related Skills

- `ews-email` — 获取 Sender 和 ConversationId
- `ews-subscribe` — 在事件回调中使用此逻辑
- `email-parse-ticket` — 在回复邮件中提取工单号