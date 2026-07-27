function New-IcmIncident {
    [CmdletBinding()]
    param(
        [string]$Title,
        [string]$Description = "Incident Created",
        [string]$Summary,
        [int]$Severity = 3,
        [int]$OwningServiceId = 20284,
        [int]$OwningTeamId = 37883,
        [bool]$IsSecurityRisk = $false,
        [bool]$IsCustomerImpacting = $false,
        [array]$ImpactedServices = @(),
        [array]$ImpactedTeams = @(),
        [array]$ImpactedComponents = @(),
        [array]$CustomFields = @(),
        [array]$Attachments = @(),
        [string]$Keywords,
        [string]$CustomerName,
        [string]$SupportTicketId,
        [string]$SubscriptionId
    )

    $utcNow = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")

    $location = @{
        Environment  = "PROD"
        Datacenter   = $null
        Role         = $null
        Instance     = $null
        Slice        = $null
    }

    $dict = [ordered]@{}
    $dict["Id"] = 0
    $dict["Title"] = $Title
    $dict["Description"] = $Description
    $dict["Summary"] = $Summary
    $dict["CreatedDate"] = $utcNow
    $dict["LastModifiedDate"] = $utcNow
    $dict["OccuringLocation"] = $location
    $dict["IsSecurityRisk"] = $IsSecurityRisk
    $dict["IsCustomerImpacting"] = $IsCustomerImpacting
    $dict["IsNoise"] = $false
    $dict["State"] = "ACTIVE"
    $dict["Severity"] = $Severity
    $dict["Attachments"] = $Attachments
    $dict["CloudInstanceId"] = 3
    $dict["Type"] = "LiveSite"
    $dict["OwningServiceId"] = $OwningServiceId
    $dict["OwningTeamId"] = $OwningTeamId
    $dict["IsAcknowledged"] = $false
    $dict["Keywords"] = $Keywords
    $dict["SubscriptionId"] = $SubscriptionId
    $dict["SupportTicketId"] = $SupportTicketId
    $dict["CustomerName"] = $CustomerName
    $dict["LinkedIncidentCount"] = 0
    $dict["ExternalLinksCount"] = 0
    $dict["SourceCreateTime"] = $utcNow
    $dict["HitCount"] = 0
    $dict["ChildCount"] = 0
    $dict["ImpactedServices"] = $ImpactedServices
    $dict["ImpactedTeams"] = $ImpactedTeams
    $dict["ImpactedComponents"] = $ImpactedComponents
    $dict["CustomFields"] = $CustomFields

    # Call ConvertTo-IcmIncidentPsNoteProperty directly (not via pipe) to avoid PS 5.1 treating
    # OrderedDictionary as IEnumerable and breaking it into individual items in the pipeline.
    return ConvertTo-IcmIncidentPsNoteProperty -Dict $dict
}

function ConvertTo-IcmIncidentPsNoteProperty {
    param($Dict)
    $obj = New-Object PSObject
    $Dict.GetEnumerator() | ForEach-Object {
        $obj | Add-Member -NotePropertyName $_.Key -NotePropertyValue $_.Value
    }
    return $obj
}

function ConvertTo-IcmIncidentJson {
    param(
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        $Incident
    )
    process {
        return $Incident | ConvertTo-Json -Depth 4 -Compress:$false
    }
}

# ===================== 使用示例 =====================
if ($MyInvocation.ScriptName -eq $PSCommandPath) {
    Write-Host "=== CreateIncident JSON ==="
    $inc = New-IcmIncident `
        -Title "PowerShell Test - ICM Ticket" `
        -Description "Test incident from PowerShell" `
        -Summary "PowerShell API test" `
        -Severity 3 `
        -OwningTeamId 37883 `
        -ImpactedServices @(@{ ServiceId = 20284 })

    $inc | ConvertTo-IcmIncidentJson
}
