<#
.SYNOPSIS
    Email Monitor — End-to-end orchestrator for all 7 EWS/Email Skills

.DESCRIPTION
    Chains all Skills together to monitor new emails, track conversations,
    extract ticket numbers, and output results.

.PARAMETER DllPath
    Path to Microsoft.Exchange.WebServices.dll

.PARAMETER EwsUrl
    EWS endpoint URL

.PARAMETER FolderNames
    Array of folder names to monitor

.PARAMETER MyAddress
    Your email address (for conversation tracking)

.PARAMETER TicketPattern
    Regex pattern to extract ticket numbers. Default: 'Request\s*#\s*(\d+)'

.EXAMPLE
    .\Monitor-Email.ps1 `
        -DllPath "C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll" `
        -EwsUrl "https://mail.21vianet.com/EWS/Exchange.asmx" `
        -FolderNames @("Inbox", "Sent Items", "dl-ps", "EDM") `
        -MyAddress "ma.chuntao@oe.21vianet.com"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$DllPath,

    [Parameter(Mandatory=$true)]
    [string]$EwsUrl,

    [Parameter(Mandatory=$false)]
    [string[]]$FolderNames = @("Inbox", "Sent Items"),

    [Parameter(Mandatory=$true)]
    [string]$MyAddress,

    [Parameter(Mandatory=$false)]
    [string]$TicketPattern = 'Request\s*#\s*(\d+)'
)

# ==================== Load all Skills ====================
$skillPath = Join-Path $PSScriptRoot ".claude\skills"

. (Join-Path $skillPath "ews-connect\Connect-Ews.ps1")
. (Join-Path $skillPath "ews-folder\Get-EwsFolder.ps1")
. (Join-Path $skillPath "ews-email\Get-EwsEmail.ps1")
. (Join-Path $skillPath "ews-subscribe\Start-EwsSubscription.ps1")
. (Join-Path $skillPath "email-html2text\Convert-HtmlToText.ps1")
. (Join-Path $skillPath "email-parse-ticket\Parse-TicketNumber.ps1")
. (Join-Path $skillPath "email-track-conversation\Track-Conversation.ps1")

Write-Host "========================================"
Write-Host "  Email Monitor Starting"
Write-Host "  Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "  Address: $MyAddress"
Write-Host "  Folders: $($FolderNames -join ', ')"
Write-Host "========================================"

# ==================== Step 1: Connect ====================
Write-Host "`n[1/4] Connecting to EWS..."
$exchService = Connect-Ews -DllPath $DllPath -EwsUrl $EwsUrl

# ==================== Step 2: Get Folders ====================
Write-Host "`n[2/4] Loading folders..."
$folders = @()
foreach ($name in $FolderNames) {
    $f = Get-EwsFolder -Name $name -ExchangeService $exchService
    if ($f) {
        $folders += $f
    }
    else {
        Write-Warning "Skipping folder '$name' (not found)"
    }
}
if ($folders.Count -eq 0) {
    Write-Error "No valid folders. Aborting."
    exit 1
}

# ==================== Step 3: Define handler ====================
Write-Host "`n[3/4] Setting up mail handler..."

$onNewMail = {
    param($EmailData)

    $bodyText = $EmailData.BodyText
    $classification = $EmailData.Classification

    # Skip sent mail (just tracked)
    if ($classification -eq "Sent") {
        return
    }

    Write-Host "---"
    Write-Host "Classification : $classification"
    Write-Host "From           : $($EmailData.EmailSender)"
    Write-Host "Subject        : $($EmailData.Subject)"

    # Parse ticket number
    $ticketResult = Parse-TicketNumber -Text $bodyText -Pattern $TicketPattern
    if ($ticketResult.Found) {
        Write-Host "Ticket Number  : $($ticketResult.Number)" -ForegroundColor Green
    }
    else {
        Write-Host "Ticket Number  : (not found)" -ForegroundColor Yellow
    }

    # Show first 200 chars of body
    $preview = if ($bodyText.Length -gt 200) { "$($bodyText.Substring(0, 200))..." } else { $bodyText }
    Write-Host "Body Preview   : `n$preview"
    Write-Host "---"
}

# ==================== Step 4: Start subscription ====================
Write-Host "`n[4/4] Starting subscription..."
Start-EwsSubscription `
    -ExchangeService $exchService `
    -Folders $folders `
    -MyAddress $MyAddress `
    -OnNewMail $onNewMail
