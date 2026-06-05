using namespace System.Collections
using namespace System.Collections.Generic

#Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\ewslibNew\lib\net35\Microsoft.Exchange.WebServices.dll"
Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll"
#$Credentials = New-Object Microsoft.Exchange.WebServices.Data.WebCredentials("ma.chuntao","****","bj-oe.21vianet.com")
$Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
$myAddress = "ma.chuntao@oe.21vianet.com".ToLower()
$Global:InitiatedConversations = @{}
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = 'https://mail.21vianet.com/EWS/Exchange.asmx'
$conn = New-Object Microsoft.Exchange.WebServices.Data.StreamingSubscriptionConnection($exchService,30)

# 定义getfolder 函数
function Get-Folder {
    param (
        [string]$Name
    )
    if ($Name -eq "Inbox") {
        return [Microsoft.Exchange.WebServices.Data.Folder]::Bind(
            $exchService,
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
        )
    }
    else {
            $folderView = New-Object Microsoft.Exchange.WebServices.Data.FolderView(1)
            $folderView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

            $searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsEqualTo(
                [Microsoft.Exchange.WebServices.Data.FolderSchema]::DisplayName,
                $Name
            )

            $folders = $exchService.FindFolders(
                [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::MsgFolderRoot,
                $searchFilter,
                $folderView
            )

            if ($folders.TotalCount -gt 0) {
                return $folders.Folders[0]
            }
            else {
                return $null
            }
    }
    
}
#定义被监听的文件夹
$folders = @(
    Get-Folder -Name "Inbox"
    Get-Folder -Name "dl-ps"
    Get-folder -Name "EDM"
    get-folder -Name "Sent Items"
) | Where-Object { $_ }
$folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]@(
    $folders[0].Id
    $folders[1].Id
    $folders[2].Id
    $folders[3].Id
)
$Subscription = $exchService.SubscribeToStreamingNotifications(
    $folderIds,
    [Microsoft.Exchange.WebServices.Data.EventType]::NewMail
)

$conn.AddSubscription($Subscription)

# 注册事件监听器
Register-ObjectEvent -InputObject $conn -EventName OnNotificationEvent -Action {
    # 获取事件参数
    $eventArgs = $event.SourceEventArgs
    
    foreach ($evt in $eventArgs.Events) {
        Write-Host "--------------------------------------------------"
        Write-Host "$(Get-Date) | Event: $($evt.EventType)"
        
        # 安全检查：确保 ItemId 存在且不为空
        if ($evt.ItemId -ne $null -and $evt.ItemId.UniqueId) {
            try {
                # 【核心修复】使用标准 Bind 方法获取邮件详情
                # 1. 创建一个属性集合，声明我们只需要 "主题(Subject)" 和 "正文(Body)"
                $propertySet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet([Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject, [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body,[Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,[Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId)
                
                # 2. 使用 EmailMessage.Bind 绑定具体的邮件 ID
                # 注意：$evt.ItemId 直接作为参数传入
                $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $evt.ItemId, $propertySet)
                
                $sender = $email.Sender.Address.ToLower()
                $conversationId = $email.ConversationId.UniqueId
                # ✅ 1. 已发送邮件（记录 Conversation）
                if ($sender -eq $myAddress) {
                    $Global:InitiatedConversations[$conversationId] = $true
                    Write-Host "📤 记录对话：$conversationId"
                    continue
                }
                elseif($Global:InitiatedConversations.ContainsKey($conversationId)){
                        # 【3. 判断是否是 HTML 格式，如果是，则转换为纯文本】
                        $html = $email.Body.ToString()
                        $doc = New-Object -ComObject "HTMLFile"
                        # 关键点：直接写 Unicode 字符串
                        $doc.IHTMLDocument2_write($html)
                        $text = $doc.body.innerText
                        # 清理空行
                        $text = ($text -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"
                        if($text -match 'Request\s*#\s*(\d+)') {
                            $ticketNumber = $Matches[1]
                            Write-Host "`n✅ 识别到回复邮件"
                            Write-Host "ConversationId : $conversationId"
                            Write-Host "Sender         : $sender"
                            Write-Host "Ticket Number  : $ticketNumber"
                        }
                        else {
                            Write-Host "`n⚠️  收到邮件，但未识别到工单号"
                            Write-Host "ConversationId : $conversationId"
                            Write-Host "Sender         : $sender"
                            Write-Host "Email Subject  : $($email.Subject)"
                        }
                
                    }  
                else {
                        Write-Host "`n⚠️  收到其他邮件（非对话内）"
                        Write-Host "ConversationId : $conversationId"
                        Write-Host "Sender         : $sender"
                        Write-Host "Email Subject  : $($email.Subject)"
                    }
            } catch {
                # 捕获并打印具体的错误信息，方便调试
                Write-Warning "无法读取邮件详情: $($_.Exception.Message)"
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


$conn.Open()

Write-Host "Streaming subscription started. Press Ctrl+C to stop."
while ($conn.IsOpen) {
    Start-Sleep 1
}