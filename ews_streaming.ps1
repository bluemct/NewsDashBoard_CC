using namespace System.Collections
using namespace System.Collections.Generic

param(
    [string]$DllPath = "",
    [string]$EwsUrl = "https://mail.21vianet.com/EWS/Exchange.asmx",
    [string]$DomainUser = "",
    [string]$Password = "j1ux1@nM10/09/24",
    [string]$FolderName = "EDM"
)

# Default DLL path — auto-detect if not specified
if (-not $DllPath) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $dll40 = Join-Path $ScriptDir "EWS\lib\40\Microsoft.Exchange.WebServices.dll"
    $dll35 = Join-Path $ScriptDir "EWS\extracted\lib\net35\Microsoft.Exchange.WebServices.dll"
    if (Test-Path $dll40) {
        $DllPath = $dll40
    } elseif (Test-Path $dll35) {
        $DllPath = $dll35
    }
}

#Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\ewslibNew\lib\net35\Microsoft.Exchange.WebServices.dll"
Import-Module -Name $DllPath
$Credentials = New-Object Microsoft.Exchange.WebServices.Data.WebCredentials("ps-tier2.support",$Password,"21vianet.com")
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = $EwsUrl
<#
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.UseDefaultCredentials = $true
$exchService.AutodiscoverUrl('ps-tier2.support@oe.21vianet.com')
#>

#$WellKnownFolderName = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
$conn = New-Object Microsoft.Exchange.WebServices.Data.StreamingSubscriptionConnection($exchService,30)

# $folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]@(
#     [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
# )
# $subscription = $exchservice.SubscribeToStreamingNotifications(
#     $folderIds,
#     [Microsoft.Exchange.WebServices.Data.EventType]::NewMail
# )


# 1️⃣ 查找自定义文件夹
$folderView = New-Object Microsoft.Exchange.WebServices.Data.FolderView(1)
$folderView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

$searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsEqualTo(
    [Microsoft.Exchange.WebServices.Data.FolderSchema]::DisplayName,
    $FolderName
)

# 从 Inbox 开始找
$folders = $exchService.FindFolders(
    [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::MsgFolderRoot,
    $searchFilter,
    $folderView
)

if ($folders.TotalCount -eq 0) {
    throw "未找到自定义文件夹：EDM"
}

$customFolder = $folders.Folders[0]

# 2️⃣ 创建 Streaming Subscription
$folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]@(
    [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox,
    $customFolder.Id
)

$subscription = $exchService.SubscribeToStreamingNotifications(
    $folderIds,
    [Microsoft.Exchange.WebServices.Data.EventType]::NewMail
)


$conn.AddSubscription($subscription)

# ═══════════════════════════════════════════════════════
# 用临时文件桥接事件 runspace → 主循环 stdout
# Register-ObjectEvent 的 Action 在独立 runspace 运行，
# $script: 变量跨 runspace 无效，所以用文件 IPC
# ═══════════════════════════════════════════════════════

$eventFile = [System.IO.Path]::Combine($env:TEMP, "ews_events_$PID.txt")
if (Test-Path $eventFile) { Remove-Item $eventFile -Force }
$env:ews_event_file = $eventFile  # Make visible to Register-ObjectEvent runspace

Register-ObjectEvent -InputObject $conn -EventName OnNotificationEvent -Action {
    $eventArgs = $event.SourceEventArgs

    foreach ($evt in $eventArgs.Events) {
        Write-Host "--------------------------------------------------"
        Write-Host "$(Get-Date) | Event: $($evt.EventType)"

        if ($evt.ItemId -ne $null -and $evt.ItemId.UniqueId) {
            try {
                $propertySet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::DateTimeReceived,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::HasAttachments,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId
                )
                $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $evt.ItemId, $propertySet)

                $html = $email.Body.ToString()
                if ($html) {
                    $doc = New-Object -ComObject "HTMLFile"
                    $doc.IHTMLDocument2_write($html)
                    $text = $doc.body.innerText
                    $text = ($text -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"
                } else {
                    $text = ""
                }

                Write-Host "Found New Mail!"
                Write-Host "  Item ID : $($evt.ItemId.UniqueId)"
                Write-Host "  Subject : $($email.Subject)"
                Write-Host "  From    : $($email.Sender.Address)"
                Write-Host "  HasAttachments : $($email.HasAttachments)"
                Write-Host "Body: $text"

                $bodyPreview = ""
                if ($text.Length -gt 0) {
                    $bodyPreview = $text.Substring(0, [Math]::Min($text.Length, 3000))
                }

                $senderAddr = if ($email.Sender) { $email.Sender.Address } else { "" }
                $dtReceived = if ($email.DateTimeReceived) { $email.DateTimeReceived.ToString("o") } else { "" }
                $hasAtt = if ($email.HasAttachments) { $email.HasAttachments } else { $false }
                $convId = if ($email.ConversationId) { $email.ConversationId.UniqueId } else { "" }

                $eventJson = @{
                    type = "newmail"
                    item_id = $evt.ItemId.UniqueId
                    subject = $email.Subject
                    from = $senderAddr
                    has_attachments = $hasAtt
                    datetime_received = $dtReceived
                    body_preview = $bodyPreview
                    conversation_id = $convId
                } | ConvertTo-Json -Compress

                # Write to temp file for main loop to pick up
                Add-Content -Path $env:ews_event_file -Value $eventJson -Force

            } catch {
                Write-Warning "无法读取邮件详情: $($_.Exception.Message)"
                Add-Content -Path $env:ews_event_file -Value ('{"type":"error","message":"' + $_.Exception.Message.Replace('"', "'") + '"}') -Force
            }
        } else {
            Write-Warning "收到一个没有 ItemId 的事件，跳过处理。"
        }
    }
}

Register-ObjectEvent -InputObject $conn -EventName OnDisconnect -Action {
    Write-Warning "Connection disconnected, reconnecting..."
    Start-Sleep 5
    $conn.Open()
}

# 打开连接
$conn.Open()

Write-Output ('{"type":"connected","subscription_id":"' + $subscription.Id + '"}')
Write-Host "Streaming subscription started. Press Ctrl+C to stop."

# 主循环：轮询临时文件，输出 JSON 到 stdout
$lastLength = 0
while ($conn.IsOpen) {
    if (Test-Path $eventFile) {
        $content = Get-Content $eventFile -Raw
        if ($content -and $content.Length -gt $lastLength) {
            $newLines = $content.Substring($lastLength).TrimEnd("`r`n")
            foreach ($line in $newLines -split "`n") {
                $line = $line.Trim()
                if ($line) {
                    Write-Output $line
                }
            }
            $lastLength = $content.Length
        }
    }
    Start-Sleep 1
}

# 清理
if (Test-Path $eventFile) { Remove-Item $eventFile -Force -ErrorAction SilentlyContinue }
