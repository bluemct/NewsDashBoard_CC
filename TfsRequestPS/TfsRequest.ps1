<#
.SYNOPSIS
TFS Request 2010 PowerShell wrapper for PS Workspace.

.DESCRIPTION
Provides functions to connect to TFS 2010, query work items, update fields,
and resolve tickets. Designed to be called via Python subprocess.

.PARAMETER Action
The action to perform: connect, query, update, resolve

.PARAMETER WorkItemId
The work item ID for update/resolve actions

.PARAMETER State
The state to set (e.g., 'In Process Implementer', 'Resolved')

.PARAMETER AssignedTo
The assignee name

.PARAMETER Property
The property value (e.g., 'PS-EDM')

.PARAMETER ActionField
The action field value (e.g., '1ST Update')

.PARAMETER Solution
The solution description

.PARAMETER WorkingHour
The working hour value

.PARAMETER OutputFormat
Output format: json (default) or text

.EXAMPLE
.\TfsRequest.ps1 -Action query
.\TfsRequest.ps1 -Action update -WorkItemId 12345 -State 'In Process Implementer' -AssignedTo 'Michael Ma'
.\TfsRequest.ps1 -Action resolve -WorkItemId 12345
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('connect', 'query', 'update', 'resolve', 'batch_resolve', 'dump-fields')]
    [string]$Action,

    [string]$WorkItemIds,  # space or comma separated list, split internally

    [string]$State,
    [string]$AssignedTo,
    [string]$Property,
    [string]$ActionField,
    [string]$Solution,
    [int]$WorkingHour,

    [string]$ConfigPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Convert-WorkItemIds {
    param([string]$Ids)
    $result = @()
    if ($Ids) {
        foreach ($p in $Ids -split '[,\s]+') {
            if ($p -ne '') { $result += $p }
        }
    }
    return $result
}

# ─── Config ───────────────────────────────────────────────────

function Get-TfsConfig {
    # Priority: explicit -ConfigPath > script sibling > project root
    if ($ConfigPath -and (Test-Path $ConfigPath)) {
        return (Get-Content $ConfigPath -Raw) | ConvertFrom-Json
    }

    # When called from standalone test: config is alongside test script
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $parentDir = Join-Path $scriptDir ".."
    $candidatePaths = @(
        # Standalone test: config next to test_tfs_request.py (one level up from TfsRequestPS/)
        (Join-Path $parentDir "ps_workspace_config.json"),
        # PS Workspace: PSWorkspace/ps_workspace_config.json
        (Join-Path (Join-Path $scriptDir "..")  "ps_workspace_config.json")
    )

    foreach ($p in $candidatePaths) {
        if (Test-Path $p) {
            return (Get-Content $p -Raw) | ConvertFrom-Json
        }
    }

    Write-Error "Config file 'ps_workspace_config.json' not found. Searched: $($candidatePaths -join "; ")"
    exit 1
}

# ─── TFS Connection ───────────────────────────────────────────

function Connect-TFS2010 {
    [CmdletBinding()]
    param()

    try {
        # Load TFS assemblies
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

        $config = Get-TfsConfig
        $tfsConfig = $config.tfsrequest

        $tfsServerUrl = $tfsConfig.server_url
        $collectionName = $tfsConfig.collection

        if (-not $tfsServerUrl.EndsWith("/")) {
            $tfsServerUrl = $tfsServerUrl + "/"
        }

        $collectionUrl = $tfsServerUrl + $collectionName
        $tfsUri = New-Object System.Uri($collectionUrl)

        $tfsCollection = New-Object Microsoft.TeamFoundation.Client.TfsTeamProjectCollection($tfsUri)
        $tfsCollection.Authenticate()

        return $tfsCollection
    }
    catch {
        Write-Error "Failed to connect to TFS: $($_.Exception.Message)"
        exit 1
    }
}

# ─── Query Open Work Items ────────────────────────────────────

function Query-OpenTickets {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $TfsCollection
    )

    try {
        $workItemStore = $TfsCollection.GetService(
            [Microsoft.TeamFoundation.WorkItemTracking.Client.WorkItemStore]
        )

        # Query: State != Closed, Assignee Group = PS
        $witql = @"
SELECT
    [System.Id],
    [System.Title],
    [System.State],
    [System.AssignedTo],
    [System.Description],
    [Hisoft.21ViaNet.Description],
    [System.WorkItemType],
    [System.CreatedDate],
    [System.ChangedDate],
    [Property]
FROM WorkItems
WHERE
    [System.State] <> 'Closed'
    AND [System.State] <> 'Canceled'
    AND [Assignee Group] = 'PS'
ORDER BY
    [System.ChangedDate] DESC
"@

        $query = New-Object Microsoft.TeamFoundation.WorkItemTracking.Client.Query($workItemStore, $witql)
        $workItems = $query.RunQuery()

        $results = @()
        foreach ($wi in $workItems) {
            $tsgRaw = $wi.Fields["Hisoft.21ViaNet.Description"].Value
            $tsgStr = if ($tsgRaw) { [string]$tsgRaw } else { "" }
            # Truncate to 5000 chars to avoid JSON serialization issues
            if ($tsgStr.Length -gt 5000) { $tsgStr = $tsgStr.Substring(0, 5000) }
            $results += [PSCustomObject]@{
                id          = $wi.Id
                title       = $wi.Title
                state       = $wi.Fields["System.State"].Value
                assignedTo  = $wi.Fields["System.AssignedTo"].Value
                description = $wi.Fields["System.Description"].Value
                property    = $wi.Fields["Property"].Value
                solution    = $wi.Fields["Solution"].Value
                workingHour = $wi.Fields["Hisoft.21ViaNet.TotalLaborTimeShow"].Value
                tsgLog      = $tsgStr
                workItemType = $wi.Fields["System.WorkItemType"].Value
                createdDate = $wi.Fields["System.CreatedDate"].Value.ToString("yyyy-MM-ddTHH:mm:ss")
                changedDate = $wi.Fields["System.ChangedDate"].Value.ToString("yyyy-MM-ddTHH:mm:ss")
            }
        }

        return $results
    }
    catch {
        Write-Error "Query failed: $($_.Exception.Message)"
        exit 1
    }
}

# ─── Update Work Item ─────────────────────────────────────────

function Update-WorkItem {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $TfsCollection,

        [Parameter(Mandatory = $true)]
        [int]$WorkItemId,

        [string]$State,
        [string]$AssignedTo,
        [string]$Property,
        [string]$ActionField,
        [string]$Solution,
        [int]$WorkingHour
    )

    try {
        $workItemStore = $TfsCollection.GetService(
            [Microsoft.TeamFoundation.WorkItemTracking.Client.WorkItemStore]
        )

        $wi = $workItemStore.GetWorkItem($WorkItemId)

        $updates = [ordered]@{}
        if ($State) {
            $wi.Fields["System.State"].Value = $State
            $updates["state"] = $State
        }
        if ($AssignedTo) {
            $wi.Fields["System.AssignedTo"].Value = $AssignedTo
            $updates["assignedTo"] = $AssignedTo
        }
        if ($Property) {
            $wi.Fields["Property"].Value = $Property
            $updates["property"] = $Property
        }
        if ($ActionField) {
            $wi.Fields["Action"].Value = $ActionField
            $updates["action"] = $ActionField
        }
        if ($Solution) {
            $wi.Fields["Solution"].Value = $Solution
            $updates["solution"] = $Solution
        }
        if ($WorkingHour) {
            $wi.Fields["Hisoft.21ViaNet.TotalLaborTimeShow"].Value = $WorkingHour
            $wi.Fields["Hisoft.21ViaNet.TotalLaborTime"].Value = $WorkingHour
            $updates["workingHour"] = $WorkingHour
        }

        $wi.Save()

        $updates["workItemId"] = $WorkItemId
        $updates["title"] = $wi.Title
        return [PSCustomObject]$updates
    }
    catch {
        $err = $_.Exception.Message
        Write-Error "Update failed for WI ID $($WorkItemId): $err"
        return [PSCustomObject]@{ workItemId = $WorkItemId; error = $err }
    }
}

# ─── Resolve Work Item ────────────────────────────────────────

function Resolve-WorkItem {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $TfsCollection,

        [Parameter(Mandatory = $true)]
        [int]$WorkItemId
    )

    return Update-WorkItem `
        -TfsCollection $TfsCollection `
        -WorkItemId $WorkItemId `
        -State 'Resolved'
}

# ─── Get Single Work Item ─────────────────────────────────────

function Get-SingleWorkItem {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $TfsCollection,

        [Parameter(Mandatory = $true)]
        [int]$WorkItemId
    )

    try {
        $workItemStore = $TfsCollection.GetService(
            [Microsoft.TeamFoundation.WorkItemTracking.Client.WorkItemStore]
        )

        $wi = $workItemStore.GetWorkItem($WorkItemId)

        return [PSCustomObject]@{
            id          = $wi.Id
            title       = $wi.Title
            state       = $wi.Fields["System.State"].Value
            assignedTo  = $wi.Fields["System.AssignedTo"].Value
            description = $wi.Fields["System.Description"].Value
            property    = $wi.Fields["Property"].Value
            action      = $wi.Fields["Action"].Value
            solution    = $wi.Fields["Solution"].Value
            workingHour = $wi.Fields["Hisoft.21ViaNet.TotalLaborTimeShow"].Value
            workItemType = $wi.Fields["System.WorkItemType"].Value
            createdDate = $wi.Fields["System.CreatedDate"].Value.ToString("yyyy-MM-ddTHH:mm:ss")
            changedDate = $wi.Fields["System.ChangedDate"].Value.ToString("yyyy-MM-ddTHH:mm:ss")
        }
    }
    catch {
        $err = $_.Exception.Message
        Write-Error "Get work item failed for WI ID $WorkItemId $err"
        return [PSCustomObject]@{ workItemId = $WorkItemId; error = $err }
    }
}

# ─── Main ─────────────────────────────────────────────────────

try {
    $tfs = Connect-TFS2010

    # Parse WorkItemIds string into array of IDs
    if ($WorkItemIds) {
        $WorkItemIdsArr = @(Convert-WorkItemIds -Ids $WorkItemIds)
    } else {
        $WorkItemIdsArr = @()
    }

    switch ($Action) {
        'connect' {
            Write-Output (@{ ok = $true; message = "Connected to TFS" } | ConvertTo-Json -Compress)
        }

        'query' {
            $tickets = @(Query-OpenTickets -TfsCollection $tfs)
            Write-Output (@{ ok = $true; count = $tickets.Count; tickets = $tickets } | ConvertTo-Json -Depth 4 -Compress)
        }

        'update' {
            if ($WorkItemIdsArr.Count -ne 1) {
                Write-Error "Update action requires exactly one WorkItemId"
                exit 1
            }
            $result = Update-WorkItem `
                -TfsCollection $tfs `
                -WorkItemId $WorkItemIdsArr[0] `
                -State $State `
                -AssignedTo $AssignedTo `
                -Property $Property `
                -ActionField $ActionField `
                -Solution $Solution `
                -WorkingHour $WorkingHour
            Write-Output (@{ ok = $true; result = $result } | ConvertTo-Json -Depth 3 -Compress)
        }

        'resolve' {
            if ($WorkItemIdsArr.Count -ne 1) {
                Write-Error "Resolve action requires exactly one WorkItemId"
                exit 1
            }
            $result = Resolve-WorkItem -TfsCollection $tfs -WorkItemId $WorkItemIdsArr[0]
            Write-Output (@{ ok = $true; result = $result } | ConvertTo-Json -Depth 3 -Compress)
        }

        'dump-fields' {
            $workItemStore = $tfs.GetService(
                [Microsoft.TeamFoundation.WorkItemTracking.Client.WorkItemStore]
            )
            $results = @()
            foreach ($wid in $WorkItemIdsArr) {
                $wi = $workItemStore.GetWorkItem($wid)
                $fields = @()
                foreach ($f in $wi.Fields) {
                    $fields += [PSCustomObject]@{
                        name  = $f.ReferenceName
                        value = if ($f.Value) {
                            $v = $f.Value.ToString()
                            if ($v.Length -gt 300) { $v.Substring(0, 300) } else { $v }
                        } else { "" }
                    }
                }
                $results += [PSCustomObject]@{
                    workItemId = $wid
                    fields     = $fields
                }
            }
            Write-Output (@{ ok = $true; tickets = $results } | ConvertTo-Json -Depth 3 -Compress)
        }

        'batch_resolve' {
            $results = @()
            foreach ($wid in $WorkItemIdsArr) {
                $r = Resolve-WorkItem -TfsCollection $tfs -WorkItemId $wid
                $results += $r
            }
            $successCount = ($results | Where-Object { -not $_.error }).Count
            $failCount = ($results | Where-Object { $_.error }).Count
            Write-Output (@{
                ok      = $true
                total   = $results.Count
                success = $successCount
                failed  = $failCount
                results = $results
            } | ConvertTo-Json -Depth 3 -Compress)
        }
    }
}
catch {
    Write-Output (@{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 1
}
