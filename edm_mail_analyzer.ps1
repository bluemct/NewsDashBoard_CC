using namespace System.Collections
using namespace System.Collections.Generic

Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll"

$Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = 'https://mail.21vianet.com/EWS/Exchange.asmx'

# --- 1. Find EDM folder ---
function Get-Folder {
    param([string]$Name)
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
    if ($folders.TotalCount -gt 0) { return $folders.Folders[0] }
    return $null
}

$edmFolder = Get-Folder -Name "EDM"
if (-not $edmFolder) {
    Write-Host "Error: EDM folder not found." -ForegroundColor Red
    exit 1
}

# --- 2. Read ALL emails in EDM folder ---
$ItemView = New-Object Microsoft.Exchange.WebServices.Data.ItemView(1000)
$ItemView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

$result = $exchService.FindItems($edmFolder.Id, $ItemView)
Write-Host "Folder: EDM"
Write-Host "Total items found: $($result.Items.Count)"

# --- 3. Extract date, subject, sender, conversation_id ---
$allEmails = @()

foreach ($item in $result.Items) {
    $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $item.Id)

    $emailProps = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,
        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::DateTimeReceived,
        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId
    )
    [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $item.Id, $emailProps)

    $senderAddress = ""
    if ($email.Sender) {
        $senderAddress = $email.Sender.Address
    }

    $conversationId = ""
    if ($email.ConversationId) {
        $conversationId = $email.ConversationId.UniqueId
    }

    $record = [Ordered]@{
        date               = $email.DateTimeReceived.ToString("yyyy-MM-dd HH:mm:ss")
        subject            = $email.Subject
        sender             = $senderAddress
        conversation_id    = $conversationId
    }

    $allEmails += [PSCustomObject]$record
}

# --- 4. Sort emails by date ASCENDING (oldest first) so step 1 = first email in conversation ---
$allEmails = $allEmails | Sort-Object { [datetime]::ParseExact($_.date, "yyyy-MM-dd HH:mm:ss", $null) }

# --- 5. Assign sequential step number per conversation ---
$convStep = @{}
$outputRecords = @()

foreach ($email in $allEmails) {
    $cid = $email.conversation_id
    if ($convStep.ContainsKey($cid)) {
        $convStep[$cid]++
    } else {
        $convStep[$cid] = 1
    }

    $record = [Ordered]@{
        date                = $email.date
        subject             = $email.subject
        sender              = $email.sender
        conversation_id     = $cid
        conversation_step   = $convStep[$cid]
        conversation_total  = $null  # will be filled below
    }
    $outputRecords += [PSCustomObject]$record
}

# --- 5. Fill in conversation_total (the final step count) ---
foreach ($record in $outputRecords) {
    $record.conversation_total = $convStep[$record.conversation_id]
}

# --- 6. Summary: list all conversations with counts ---
Write-Host ""
Write-Host "=== Conversations ($($convStep.Count) total) ==="
$convStep.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object {
    Write-Host "  [$($_.Value)] $($_.Key)"
}

# --- 7. Write to JSON ---
$outputPath = "c:\temp\edmmailanalyzer.json"
$outputRecords | ConvertTo-Json -Depth 3 | Out-File -FilePath $outputPath -Encoding utf8

Write-Host ""
Write-Host "Written $($outputRecords.Count) records to $outputPath"
