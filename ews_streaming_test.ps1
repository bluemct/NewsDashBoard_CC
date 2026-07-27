using namespace System.Collections
using namespace System.Collections.Generic

#Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\ewslibNew\lib\net35\Microsoft.Exchange.WebServices.dll"
Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll"
$Credentials = New-Object Microsoft.Exchange.WebServices.Data.WebCredentials("ps-tier2.support","j1ux1@nM10/09/09/24","21vianet.com")
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = 'https://mail.21vianet.com/EWS/Exchange.asmx'
$conn = New-Object Microsoft.Exchange.WebServices.Data.StreamingSubscriptionConnection($exchService,30)

$folderView = New-Object Microsoft.Exchange.WebServices.Data.FolderView(1)
$folderView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

$searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsEqualTo(
    [Microsoft.Exchange.WebServices.Data.FolderSchema]::DisplayName,
    "EDM"
)

$folders = $exchService.FindFolders(
    [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::MsgFolderRoot,
    $searchFilter,
    $folderView
)

if ($folders.TotalCount -eq 0) {
    throw "Folder not found: EDM"
}

$customFolder = $folders.Folders[0]

$folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]@(
    [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox,
    $customFolder.Id
)

$subscription = $exchService.SubscribeToStreamingNotifications(
    $folderIds,
    [Microsoft.Exchange.WebServices.Data.EventType]::NewMail
)

$conn.AddSubscription($subscription)

Register-ObjectEvent -InputObject $conn -EventName OnNotificationEvent -Action {
    $eventArgs = $event.SourceEventArgs
    foreach ($evt in $eventArgs.Events) {
        Write-Host "---"
        Write-Host "$(Get-Date) | Event: $($evt.EventType)"
        if ($evt.ItemId -ne $null -and $evt.ItemId.UniqueId) {
            try {
                $propertySet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body
                )
                $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $evt.ItemId, $propertySet)
                $html = $email.Body.ToString()
                $doc = New-Object -ComObject "HTMLFile"
                $doc.IHTMLDocument2_write($html)
                $text = $doc.body.innerText
                $text = ($text -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"
                Write-Host "Found New Mail!"
                Write-Host "  Item ID : $($evt.ItemId.UniqueId)"
                Write-Host "  Subject : $($email.Subject)"
                Write-Host "Body: $text"
            } catch {
                Write-Warning "Failed to read email: $($_.Exception.Message)"
            }
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