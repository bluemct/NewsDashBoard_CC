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
# 1. 获取要监听的文件夹
$folders = @(
    Get-Folder -Name "Inbox"
    Get-Folder -Name "Sent Items"
    Get-Folder -Name "MyCustomFolder"
) | Where-Object { $_ }

# 2. 提取 FolderId 数组
$folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]@(
    $folders[0].Id, $folders[1].Id, $folders[2].Id
)

# 3. 创建流式订阅（监听 NewMail 事件）
$subscription = $exchService.SubscribeToStreamingNotifications(
    $folderIds,
    [Microsoft.Exchange.WebServices.Data.EventType]::NewMail
)

# 4. 创建连接（最多同时保持 30 个连接）
$conn = New-Object Microsoft.Exchange.WebServices.Data.StreamingSubscriptionConnection(
    $exchService, 30
)
$conn.AddSubscription($subscription)

# 5. 注册事件处理
Register-ObjectEvent -InputObject $conn -EventName OnNotificationEvent -Action {
    foreach ($evt in $event.SourceEventArgs.Events) {
        Write-Host "Event: $($evt.EventType) | ItemId: $($evt.ItemId.UniqueId)"
        # 用 ews-email 获取邮件详情
    }
}

# 6. 断线重连
Register-ObjectEvent -InputObject $conn -EventName OnDisconnect -Action {
    Write-Warning "Disconnected, reconnecting..."
    Start-Sleep 5
    $conn.Open()
}

# 7. 启动监听
$conn.Open()
Write-Host "Streaming subscription started. Press Ctrl+C to stop."
while ($conn.IsOpen) {
    Start-Sleep 1
}
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