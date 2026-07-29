<#
.SYNOPSIS
    Update TFS Work Item Labor Time field via TFS API
.DESCRIPTION
    Connects to TFS 2010+ using .NET API and updates the Labor Time field.
    Much simpler and more reliable than scraping web pages.
.NOTES
    Usage:
      .\tfs_update_labor_time.ps1 -Id 565667 -Time "2.1 hrs"
      .\tfs_update_labor_time.ps1 -Id 565667 -Time "3.0 hrs" -Credential (Get-Credential)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "Work item ID, e.g. 565752")]
    [Alias("Id")]
    [int]$WorkItemId,

    [Parameter(Mandatory = $true, Position = 1, HelpMessage = "Labor time value, e.g. '2.1 hrs'")]
    [Alias("Time")]
    [string]$LaborTime,

    # TFS server URL (without collection name)
    [string]$TFSServerUrl  = "http://tfs-request.21vbluecloud.com:8080/tfs",

    # TFS collection name
    [string]$CollectionName = "DefaultCollection",

    # TFS field name for Labor Time (display format, e.g. "2.1 hrs")
    [string]$LaborTimeFieldName = "Hisoft.21ViaNet.TotalLaborTimeShow",

    # Numeric part of Labor Time (the number without " hrs")
    [string]$LaborTimeNumFieldName = "Hisoft.21ViaNet.TotalLaborTime",

    [PSCredential]$Credential

# ============================================================
# Connect to TFS via .NET API (same as your existing script)
# ============================================================
function Connect-TFS2010 {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$TFSServerUrl,

        [Parameter(Mandatory = $true)]
        [string]$CollectionName,

        [Parameter(Mandatory = $false)]
        [System.Management.Automation.PSCredential]$Credential
    )

    try {
        # Load TFS client assemblies (TFS 2010)
        $tfsAssemblies = @(
            "Microsoft.TeamFoundation.Client, Version=10.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a",
            "Microsoft.TeamFoundation.Common, Version=10.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a",
            "Microsoft.TeamFoundation.WorkItemTracking.Client, Version=10.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a"
        )

        foreach ($assembly in $tfsAssemblies) {
            try {
                [System.Reflection.Assembly]::LoadWithPartialName($assembly) | Out-Null
            }
            catch {
                Write-Warning "Could not load assembly: $assembly"
            }
        }

        # Construct the full collection URL
        if (-not $TFSServerUrl.EndsWith("/")) {
            $TFSServerUrl = $TFSServerUrl + "/"
        }

        $collectionUrl = $TFSServerUrl + $CollectionName
        Write-Host ">>> Connecting to TFS: $collectionUrl" -ForegroundColor Cyan

        $tfsUri = New-Object System.Uri($collectionUrl)

        if ($Credential) {
            $networkCredential = $Credential.GetNetworkCredential()
            $tfsCredentials = New-Object System.Net.NetworkCredential(
                $networkCredential.UserName,
                $networkCredential.Password,
                $networkCredential.Domain)

            $tfsCollection = New-Object Microsoft.TeamFoundation.Client.TfsTeamProjectCollection($tfsUri, $tfsCredentials)
        }
        else {
            $tfsCollection = New-Object Microsoft.TeamFoundation.Client.TfsTeamProjectCollection($tfsUri)
        }

        Write-Host "    Connected as: $($tfsCollection.AuthenticatedUser.DisplayName)" -ForegroundColor Green
        return $tfsCollection

    }
    catch [System.Management.Automation.RuntimeException] {
        if ($_.Exception.Message -like "*Could not load file or assembly*") {
            Write-Error "TFS 2010 client assemblies not found. Install Team Explorer 2010 or Visual Studio 2010."
        }
        else {
            Write-Error "Runtime error: $($_.Exception.Message)"
        }
    }
    catch [System.IO.FileNotFoundException] {
        Write-Error "Required TFS assemblies not found. Ensure Team Explorer 2010 is installed."
    }
    catch {
        Write-Error "Error connecting to TFS: $($_.Exception.Message)"
    }
}

# ============================================================
# Main
# ============================================================

# Connect
$tfsCollection = Connect-TFS2010 -TFSServerUrl $TFSServerUrl -CollectionName $CollectionName -Credential $Credential
if (-not $tfsCollection) {
    Write-Host "ERROR: Failed to connect to TFS." -ForegroundColor Red
    exit 1
}

# Get Work Item Store
$witStore = $tfsCollection.GetService([Microsoft.TeamFoundation.WorkItemTracking.Client.WorkItemStore])
$workItem = $witStore.GetWorkItem($WorkItemId)

Write-Host "    Work Item #${WorkItemId}: $($workItem.Title)" -ForegroundColor Green
Write-Host "    State: $($workItem.State) | Type: $($workItem.Type.Name)" -ForegroundColor Green

# Find the labor time field
$laborTimeField = $workItem.Fields[$LaborTimeFieldName]
if (-not $laborTimeField) {
    Write-Host ""
    Write-Host "ERROR: Field '$LaborTimeFieldName' not found on this work item." -ForegroundColor Red
    Write-Host "    Available fields:" -ForegroundColor Yellow
    foreach ($field in $workItem.Fields) {
        $val = if ($field.Value) { $field.Value.ToString().Substring(0, [Math]::Min(60, $field.Value.ToString().Length)) } else { "(empty)" }
        Write-Host "      RefName: $($field.RefName)  Value: $val"
    }

    Write-Host ""
    Write-Host "    Fields matching labor/time:" -ForegroundColor Yellow
    foreach ($field in $workItem.Fields) {
        if ($field.RefName -match '(?i)labor|time|effort|hours') {
            $val = if ($field.Value) { "`"$($field.Value)`"" } else { "(empty)" }
            Write-Host "      *** RefName: $($field.RefName)  Value: $val" -ForegroundColor Green
        }
    }
    exit 1
}

# Update
$oldValue = if ($laborTimeField.Value) { $laborTimeField.Value.ToString() } else { "(empty)" }
Write-Host ""
Write-Host ">>> Updating: $LaborTimeFieldName" -ForegroundColor Cyan
Write-Host "    Old value: $oldValue" -ForegroundColor Green
Write-Host "    New value: $LaborTime" -ForegroundColor Yellow

$laborTimeField.Value = $LaborTime

# Save
try {
    $workItem.Save()
    Write-Host ""
    Write-Host ">>> Work Item #${WorkItemId} updated successfully (History: $($workItem.History))" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "ERROR: Save failed - $($_.Exception.Message)" -ForegroundColor Red
}
