<#
.SYNOPSIS
    Connect to Exchange Web Services (EWS)

.DESCRIPTION
    Load EWS DLL, authenticate, and create an ExchangeService object.

.PARAMETER DllPath
    Path to Microsoft.Exchange.WebServices.dll

.PARAMETER CredentialType
    'Default' = use Windows default credentials (recommended for intranet)
    'Custom'  = use explicit username/password/domain

.PARAMETER UserName
    Username for custom credentials

.PARAMETER Password
    Password for custom credentials

.PARAMETER Domain
    Domain for custom credentials

.PARAMETER EwsUrl
    EWS endpoint URL

.EXAMPLE
    Connect-Ews -DllPath "C:\path\to\Microsoft.Exchange.WebServices.dll" -EwsUrl "https://mail.example.com/EWS/Exchange.asmx"
#>
function Connect-Ews {
    param(
        [Parameter(Mandatory=$true)]
        [string]$DllPath,

        [Parameter(Mandatory=$false)]
        [ValidateSet('Default', 'Custom')]
        [string]$CredentialType = 'Default',

        [Parameter(Mandatory=$false)]
        [string]$UserName,

        [Parameter(Mandatory=$false)]
        [SecureString]$Password,

        [Parameter(Mandatory=$false)]
        [string]$Domain,

        [Parameter(Mandatory=$true)]
        [string]$EwsUrl
    )

    # Load EWS DLL
    Import-Module -Name $DllPath -ErrorAction Stop
    Write-Host "EWS DLL loaded: $DllPath"

    # Setup credentials
    if ($CredentialType -eq 'Default') {
        $Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    }
    elseif ($CredentialType -eq 'Custom') {
        if (-not $UserName -or -not $Password) {
            throw "UserName and Password are required for Custom credentials."
        }
        $securePassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password))
        $Credentials = New-Object Microsoft.Exchange.WebServices.Data.WebCredentials($UserName, $securePassword, $Domain)
    }

    # Create ExchangeService
    $exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
    $exchService.Credentials = $Credentials
    $exchService.Url = [System.Uri]$EwsUrl

    # Verify connection
    try {
        $folder = [Microsoft.Exchange.WebServices.Data.Folder]::Bind(
            $exchService,
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
        )
        Write-Host "Connected successfully. Inbox found: $($folder.DisplayName) ($($folder.UnreadCount) unread)"
    }
    catch {
        Write-Warning "Connection established but mailbox access test failed: $($_.Exception.Message)"
    }

    return $exchService
}