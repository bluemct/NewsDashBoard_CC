using namespace System.Collections
using namespace System.Collections.Generic

Import-Module -Name "C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll"

# --- Mode: add -Full to use full scan, otherwise incremental ---
$Full = ($args -contains "-Full") -or ($args -contains "-FullScan")

$Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = 'https://mail.21vianet.com/EWS/Exchange.asmx'

$LogFile = 'C:\repos\repo\edmmailanalyzer.log'
$StartTime = Get-Date  # timer for total elapsed
function Write-Log {
    param(
        [Parameter(Mandatory=$true)][string]$Message,
        [ValidateSet('Info','Warning','Error','Debug')][string]$Level = 'Info'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $entry = "{0} [{1}] {2}" -f $timestamp, $Level.ToUpper(), $Message
    Write-Host $entry

    try {
        $entry | Out-File -FilePath $LogFile -Encoding utf8 -Append
    } catch {
        $errorMessage = "Failed to write log to {0}: {1}" -f $LogFile, $_
        Write-Host $errorMessage -ForegroundColor Yellow
    }
}

function Write-LogInfo {
    param([string]$Message)
    Write-Log -Message $Message -Level Info
}

function Write-LogWarning {
    param([string]$Message)
    Write-Log -Message $Message -Level Warning
}

function Write-LogError {
    param([string]$Message)
    Write-Log -Message $Message -Level Error
}

# --- Config ---
$RepoPath      = "C:\repos\repo"
$OutputPath    = "$RepoPath\edmmailanalyzer.json"
$GitHubRaw     = "https://raw.githubusercontent.com/bluemct/docs/master/edmmailanalyzer.json"
$GitHubProxy   = "https://ghproxy.com/$GitHubRaw"

# --- 0. Fetch existing JSON from GitHub (all modes — keeps old records as fallback) ---
$lastDate = $null  # only set in incremental mode for EWS time filter
$existingEmails = @()

if ($Full) {
    Write-Host "Running in FULL SCAN mode (existing data loaded as fallback)" -ForegroundColor Cyan
}

# Always try to load existing data from GitHub
$FetchStart = Get-Date
Write-Host "[1/6] Fetching existing data from GitHub..."

# Try git clone first (SSH then HTTPS), then HTTP fallback
$gitOk = $false
$tmpDir = $null
foreach ($repoUrl in @("git@github.com:bluemct/docs.git", "https://github.com/bluemct/docs.git")) {
    if ($tmpDir -and (Test-Path $tmpDir)) { Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue }
    try {
        $tmpDir = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
        $env:GIT_TERMINAL_PROMPT = "0"
        $env:GCM_INTERACTIVE = "never"
        $cloneResult = git clone --depth 1 --filter=blob:none $repoUrl $tmpDir 2>&1
        if ($LASTEXITCODE -eq 0) { $gitOk = $true; break }
        Write-Host "  git clone failed: $($cloneResult -join ', ')" -ForegroundColor DarkGray
    } catch {
        Write-Host "  git clone failed: $_" -ForegroundColor DarkGray
    } finally {
        $env:GIT_TERMINAL_PROMPT = $null
        $env:GCM_INTERACTIVE = $null
        if ($tmpDir -and -not (Test-Path (Join-Path $tmpDir "edmmailanalyzer.json"))) {
            Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
            $tmpDir = $null
        }
    }
}

if ($gitOk -and $tmpDir -and (Test-Path $tmpDir -ErrorAction SilentlyContinue)) {
    $jsonPath = Join-Path $tmpDir "edmmailanalyzer.json"
    $existingEmails = Get-Content -Path $jsonPath -Raw | ConvertFrom-Json
    if ($existingEmails -isnot [Array]) { $existingEmails = @($existingEmails) }
    try { Remove-Item -Recurse -Force $tmpDir } catch {}
    $sorted = $existingEmails | Sort-Object { [datetime]::ParseExact($_.date, "yyyy-MM-dd HH:mm:ss", $null) } -Descending
    if ($sorted.Count -gt 0) {
        $latestDate = [datetime]::ParseExact($sorted[0].date, "yyyy-MM-dd HH:mm:ss", $null)
        Write-Host "  git clone OK: $($existingEmails.Count) emails, latest: $latestDate"
        # Only set lastDate for incremental mode — full scan uses it as pure fallback
        if (-not $Full) {
            $lastDate = $latestDate
            Write-Host "  Incremental: only fetching emails after this time"
        }
    }
} else {
    Write-Host "  git clone failed, trying HTTP..." -ForegroundColor Yellow
    $httpOk = $false
    foreach ($url in @($GitHubRaw, $GitHubProxy)) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
            $existingEmails = ($response.Content | ConvertFrom-Json)
            if ($existingEmails -isnot [Array]) { $existingEmails = @($existingEmails) }
            $sorted = $existingEmails | Sort-Object { [datetime]::ParseExact($_.date, "yyyy-MM-dd HH:mm:ss", $null) } -Descending
            if ($sorted.Count -gt 0) {
                $latestDate = [datetime]::ParseExact($sorted[0].date, "yyyy-MM-dd HH:mm:ss", $null)
                $label = if ($url -eq $GitHubRaw) { "HTTP direct" } else { "HTTP proxy" }
                Write-Host "  $($label) OK: $($existingEmails.Count) emails, latest: $latestDate"
                if (-not $Full) {
                    $lastDate = $latestDate
                    Write-Host "  Incremental: only fetching emails after this time"
                }
                $httpOk = $true
                break
            }
        } catch {}
    }
    if (-not $httpOk) {
        Write-Host "  All methods failed - falling back to full scan" -ForegroundColor Yellow
    }
}

if ($existingEmails.Count -eq 0) {
    Write-Host "  No existing data found from GitHub" -ForegroundColor Yellow
}

$FetchElapsed = (New-TimeSpan -Start $FetchStart -End (Get-Date)).TotalSeconds
Write-Host "  Fetch done in ${FetchElapsed}s"

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
    Write-LogError "EDM folder not found."
    exit 1
}

# --- EWS: Read emails from EDM folder ---
$EwsStart = Get-Date
$ItemView = New-Object Microsoft.Exchange.WebServices.Data.ItemView(5000)
$ItemView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

$searchFilter = $null
if ($lastDate) {
    $searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsGreaterThan(
        [Microsoft.Exchange.WebServices.Data.ItemSchema]::DateTimeReceived,
        $lastDate
    )
    $modeLabel = "Incremental (since $lastDate)"
} else {
    $modeLabel = "Full scan"
}

$result = $exchService.FindItems($edmFolder.Id, $searchFilter, $ItemView)
Write-LogInfo "[$modeLabel] Folder: EDM"
Write-LogInfo "  Items found: $($result.Items.Count)"

# --- 3. Extract new email fields ---
$newEmails = @()

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

    $newEmails += [PSCustomObject]$record
}

Write-LogInfo "[3/6] Extracted $($newEmails.Count) new email records"
$EwsElapsed = (New-TimeSpan -Start $EwsStart -End (Get-Date)).TotalSeconds
Write-LogInfo "  EWS read+extract done in ${EwsElapsed}s"

# --- 4. Merge existing + new emails, dedup by date+subject+sender, then sort ---
Write-LogInfo "[4/6] Merging emails..."
$allEmails = @()
$seenKeys = @{}

# Keep existing emails (strip step/total fields, will recompute)
foreach ($e in $existingEmails) {
    $key = "$($e.date)|$($e.subject)|$($e.sender)"
    $seenKeys[$key] = $true
    $record = [Ordered]@{
        date               = $e.date
        subject            = $e.subject
        sender             = $e.sender
        conversation_id    = $e.conversation_id
    }
    $allEmails += [PSCustomObject]$record
}

# Add new emails, skip duplicates by date+subject+sender
$duplicates = 0
foreach ($n in $newEmails) {
    $key = "$($n.date)|$($n.subject)|$($n.sender)"
    if ($seenKeys.ContainsKey($key)) { $duplicates++; continue }
    $seenKeys[$key] = $true
    $allEmails += $n
}

$allEmails = $allEmails | Sort-Object { [datetime]::ParseExact($_.date, "yyyy-MM-dd HH:mm:ss", $null) }
Write-LogInfo "  Total: $($allEmails.Count) emails ($($existingEmails.Count) existing + $($newEmails.Count) new, $duplicates duplicates dropped)"

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
Write-LogInfo "[5/6] Conversations ($($convStep.Count) total):"
$convStep.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object {
    Write-LogInfo "  [$($_.Value)] $($_.Key)"
}

# --- 7. Write to JSON ---
$outputPath = "C:\repos\repo\edmmailanalyzer.json"
$outputRecords | ConvertTo-Json -Depth 3 | Out-File -FilePath $outputPath -Encoding utf8

Write-LogInfo "[6/6] Written $($outputRecords.Count) records to $outputPath"
Write-LogInfo "Changing location to $RepoPath"
Set-Location $RepoPath

Write-LogInfo "Staging JSON output for git"
$gitAddOutput = git add . 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-LogError "git add failed: $gitAddOutput"
    exit 1
} else {
    Write-LogInfo "git add completed successfully"
    if ($gitAddOutput) { Write-LogInfo $gitAddOutput }
}

Write-LogInfo "Committing git changes"
$gitCommitOutput = git commit -m "Update EDM mail analysis data" 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($gitCommitOutput -match "nothing to commit") {
        Write-LogInfo "git commit: nothing to commit"
    } else {
        Write-LogError "git commit failed: $gitCommitOutput"
        exit 1
    }
} else {
    Write-LogInfo "git commit completed successfully"
    if ($gitCommitOutput) { Write-LogInfo $gitCommitOutput }
}

Write-LogInfo "Pushing git changes to origin/master"
$gitPushOutput = git push origin master 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-LogError "git push failed: $gitPushOutput"
    exit 1
} else {
    Write-LogInfo "git push succeeded"
    if ($gitPushOutput) { Write-LogInfo $gitPushOutput }
}

$TotalElapsed = (New-TimeSpan -Start $StartTime -End (Get-Date)).TotalSeconds
Write-LogInfo "Git push done"
Write-LogInfo "===== Total elapsed: ${TotalElapsed}s ====="