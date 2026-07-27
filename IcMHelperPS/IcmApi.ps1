# ICM 统一 API 封装 — 自动 Token 刷新，聚合读取 / 创建 / 更新 / Ack 操作
#
# PowerShell 5.1+ 兼容版本，对应 Python icm_api.py (IcmClient)
# 自动管理 Token 刷新（Token 即将过期时自动用 Cookie 换取新 Token）
#
# 用法:
#   . .\IcmTokenRefresh.ps1
#   . .\IcmApi.ps1
#
#   Get-IcmIncidents -Top 10
#   $inc = New-IcmIncident -Title "测试" -Description "测试描述" -ImpactedServices @(@{ ServiceId = 20284 })
#   $result = New-IcmIncidentApi -Incident $inc
#   Ack-IcmIncident -IncidentId $result.Id
#   Add-IcmDiscussion -IncidentId $result.Id -Description "处理中"
#   Resolve-IcmIncident -IncidentId $result.Id -RootCauseOption 5
#   Resolve-IcmIncidentFull -IncidentId $result.Id -Message "已修复"  # Mitigate + RootCause + Resolve 三步
#
# 与 Python 版共享同一个 icm_config.json

# 强制 TLS 1.2 — 旧 Windows Server 默认 Tls1.0，HTTPS 调用会失败
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11

$Script:BaseUri    = "https://prod.microsofticm.com"
$Script:OncallBase = "https://oncallapi.prod.microsofticm.com"
$Script:_Token     = $null
$Script:_Config    = $null

function _Get-ConfigPath {
    return Join-Path $PSScriptRoot "icm_config.json"
}

<#
  PS 5.1 兼容: 递归转换 PSCustomObject -> hashtable
#>
function _PsObjectToHashtable {
    param($Obj)
    if ($null -eq $Obj) { return $null }
    if ($Obj -is [array] -or $Obj -is [System.Collections.IList]) {
        $result = @()
        foreach ($item in $Obj) {
            $result += ,(_PsObjectToHashtable $item)
        }
        return $result
    }
    if ($Obj -is [System.Management.Automation.PSCustomObject]) {
        $dict = @{}
        $Obj.PSObject.Properties | ForEach-Object {
            $dict[$_.Name] = _PsObjectToHashtable $_.Value
        }
        return $dict
    }
    return $Obj
}

function _Ensure-Token {
    if ($Script:_Token) {
        $exp = _Parse-JwtExpiry $Script:_Token
        $remaining = ($exp - [DateTimeOffset]::UtcNow).TotalSeconds
        if ($remaining -lt 900) {
            Write-Verbose "Token 即将过期 (剩余 $([math]::Round($remaining/60, 1)) 分钟)，自动刷新..."
            _Refresh-Token-Internal | Out-Null
        }
        return
    }

    try {
        $configPath = _Get-ConfigPath
        $json = Get-Content -Path $configPath -Raw -Encoding UTF8
        $Script:_Config = _PsObjectToHashtable ($json | ConvertFrom-Json)
        $Script:_Token = $Script:_Config["access_token"]
    } catch {
        throw "无法读取 Token: $_"
    }
}

function _Parse-JwtExpiry {
    param([string]$Token)
    $parts = $Token -split '\.'
    $payload = $parts[1]
    switch ($payload.Length % 4) {
        2 { $payload += '==' }
        3 { $payload += '=' }
    }
    $payload = $payload.Replace('-', '+').Replace('_', '/')
    $decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload))
    $data = $decoded | ConvertFrom-Json
    return [DateTimeOffset]::FromUnixTimeSeconds($data.exp)
}

function _Refresh-Token-Internal {
    $configPath = _Get-ConfigPath
    $json = Get-Content -Path $configPath -Raw -Encoding UTF8
    $config = _PsObjectToHashtable ($json | ConvertFrom-Json)

    $cookieString = $config["cookie_string"]
    $authCookie = $null
    $parts = $cookieString -split ';'
    foreach ($part in $parts) {
        $trimmed = $part.Trim()
        if ($trimmed.StartsWith("CloudESAuthCookie=")) {
            $authCookie = $trimmed.Substring("CloudESAuthCookie=".Length)
            break
        }
    }
    if (-not $authCookie) {
        throw "CloudESAuthCookie not found in config"
    }

    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("content-type", "application/json;charset=UTF-8")
    $wc.Headers.Add("origin", "https://portal.microsofticm.com")
    $wc.Headers.Add("referer", "https://portal.microsofticm.com/imp/v3/")
    $wc.Headers.Add("Cookie", "CloudESAuthCookie=$authCookie")

    $encoding = [System.Text.Encoding]::UTF8
    $bytes = $encoding.GetBytes("grant_type=cookie")
    $respBytes = $wc.UploadData("https://portal.microsofticm.com/sso2/token", "POST", $bytes)
    $respText = $encoding.GetString($respBytes)

    $respJson = $respText | ConvertFrom-Json
    $newToken = $respJson.access_token

    $setCookie = ""
    if ($wc.ResponseHeaders -and $wc.ResponseHeaders.ContainsKey("Set-Cookie")) {
        $setCookie = $wc.ResponseHeaders["Set-Cookie"]
    }
    if ($setCookie) {
        $scParts = $setCookie -split ';'
        foreach ($sc in $scParts) {
            $sct = $sc.Trim()
            if ($sct.StartsWith("CloudESAuthCookie=")) {
                $val = $sct.Substring("CloudESAuthCookie=".Length)
                if ($val -ne "") {
                    $config["cookie_string"] = "CloudESAuthCookie=$val"
                    break
                }
            }
        }
    }

    $config["access_token"] = $newToken
    $jsonOut = $config | ConvertTo-Json -Depth 4
    Set-Content -Path $configPath -Value $jsonOut -Encoding UTF8

    $Script:_Token = $newToken
    $Script:_Config = $config
    $wc.Dispose()
}

function _Get-Headers {
    _Ensure-Token
    return @{
        "Authorization" = "Bearer $Script:_Token"
        "Accept"        = "application/json, text/plain, */*"
        "Content-Type"  = "application/json"
    }
}

function _BuildQueryUri {
    param([string]$Base, [hashtable]$Params)
    if (-not $Params -or $Params.Count -eq 0) {
        return $Base
    }
    $pairs = @()
    $Params.GetEnumerator() | ForEach-Object {
        $pairs += [System.Uri]::EscapeDataString($_.Key) + "=" + [System.Uri]::EscapeDataString($_.Value)
    }
    return "$Base?" + ($pairs -join "&")
}

# ===================== 工单构造 =====================

function ConvertTo-IcmIncidentPsNoteProperty {
    param($Dict)
    $obj = New-Object PSObject
    $Dict.GetEnumerator() | ForEach-Object {
        $obj | Add-Member -NotePropertyName $_.Key -NotePropertyValue $_.Value
    }
    return $obj
}

function New-IcmIncident {
<#
.SYNOPSIS
    创建一个新的 ICM Incident 对象，字段名和默认值与 C# IcmDll.CreateIncident 一致

.EXAMPLE
    $inc = New-IcmIncident -Title "测试工单" -Description "测试描述" -ImpactedServices @(@{ ServiceId = 20284 })
    $inc | ConvertTo-Json -Depth 4

.EXAMPLE
    $inc = New-IcmIncident `
        -Title "Azure 服务异常" `
        -Description "中国区 Azure 服务出现异常" `
        -Summary "Azure 异常工单" `
        -Severity 2 `
        -OwningTeamId 37883 `
        -ImpactedServices @(@{ ServiceId = 20284 }) `
        -ImpactedTeams @(@{ TeamId = 37883 })
    $inc | ConvertTo-Json -Depth 4
#>
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

    # PS 5.1: OrderedDictionary 不能通过管道传递，必须直接参数调用
    return ConvertTo-IcmIncidentPsNoteProperty -Dict $dict
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

# ===================== 公开 API 函数 =====================

function Get-IcmIncidents {
    param(
        [string]$Filter,
        [int]$Top = 10
    )

    $headers = _Get-Headers
    $uri = "$Script:BaseUri/api2/incidentapi/incidents"

    # Build query string manually for PS 5.1 compatibility
    $queryParts = @([System.Web.HttpUtility]::UrlEncode("$top") + "=$Top")
    if ($Filter) {
        $queryParts += [System.Web.HttpUtility]::UrlEncode("$filter") + "=" + [System.Web.HttpUtility]::UrlEncode($Filter)
    }
    $uri += "?" + ($queryParts -join "&")

    $response = Invoke-RestMethod -Uri $uri -Method Get -Headers $headers -ErrorAction Stop

    if ($response.value) {
        return $response.value
    }
    return $response
}

function Get-IcmIncident {
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId
    )

    $incidents = Get-IcmIncidents -Filter "Id eq $IncidentId" -Top 1
    if ($incidents -and @($incidents).Count -gt 0) {
        return $incidents[0]
    }
    return $null
}

function New-IcmIncidentApi {
    param(
        [Parameter(Mandatory = $true)]
        $Incident
    )

    $headers = _Get-Headers
    $body = $Incident | ConvertTo-Json -Depth 4
    $uri = "$Script:BaseUri/api2/incidentapi/incidents"

    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Post `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $response
}

function Ack-IcmIncident {
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId
    )

    $headers = _Get-Headers
    $body = @{
        AcknowledgementParameters = @{
            AcknowledgeContactAlias = $null
        }
    } | ConvertTo-Json

    $uri = "$Script:BaseUri/api2/incidentapi/incidents($IncidentId)/AcknowledgeIncident"
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Post `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $true
}

function Add-IcmDiscussion {
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $headers = _Get-Headers
    $body = @{ Id = $IncidentId; Description = $Description } | ConvertTo-Json
    $uri = "$Script:BaseUri/api2/incidentapi/incidents($IncidentId)"

    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Patch `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $true
}

function Mitigate-IcmIncident {
<#
.SYNOPSIS
    对 ICM 工单执行 Mitigate（Portal API）
    对应: POST https://portal.microsofticm.com/imp/api/incident/Mitigate

.EXAMPLE
    Mitigate-IcmIncident -IncidentId 841557607 -Message "已完成检查"
#>
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId,
        [string]$Message = "",
        [string]$HowFixed = "Other",
        [bool]$IsCustomerImpacting = $false,
        [bool]$IsNoise = $false,
        [bool]$RootCauseNeedsInvestigation = $false,
        [bool]$AutoResolve = $false,
        [array]$CustomFields = @()
    )

    $headers = _Get-Headers
    $headers["Origin"] = "https://portal.microsofticm.com"
    $headers["Referer"] = "https://portal.microsofticm.com/"

    $mitigationTime = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")

    # 将纯文本消息包装为 HTML，匹配 Portal 前端格式
    $htmlMessage = if ($Message) {
        "<div style=`"font-family: Calibri, Arial, Helvetica, sans-serif; font-size: 11pt; color: rgb(0, 0, 0);`">$Message<br></div>"
    } else {
        ""
    }

    $body = @{
        Description                  = $htmlMessage
        incidentIds                  = @($IncidentId)
        HowFixed                     = $HowFixed
        IsCustomerImpacting          = $IsCustomerImpacting
        MitigationTimeStamp          = $mitigationTime
        CustomFields                 = $CustomFields
        IsNoise                      = $IsNoise
        RootCauseNeedsInvestigation  = $RootCauseNeedsInvestigation
        AutoResolve                  = $AutoResolve
    } | ConvertTo-Json

    $uri = "https://portal.microsofticm.com/imp/api/incident/Mitigate"
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Post `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $response
}

function Update-IcmIncidentRootCause {
<#
.SYNOPSIS
    更新 ICM 工单的 RootCause 信息（api2 PATCH）

.EXAMPLE
    Update-IcmIncidentRootCause -IncidentId 841557607 -Title "已完成检查" -Category "Other"
#>
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId,
        [string]$Title = "",
        [string]$Category = "Other",
        [string]$Description = "",
        [string]$SubCategory = "",
        [string]$IsCausedByChange = "false",
        [string]$AdditionalData = "{}",
        [array]$ImpactedEntities = @()
    )

    $headers = _Get-Headers
    $headers["Origin"] = "https://portal.microsofticm.com"
    $headers["Referer"] = "https://portal.microsofticm.com/"

    $body = @{
        Id               = $IncidentId
        ImpactedEntities = $ImpactedEntities
        RootCause        = @{
            Category       = $Category
            Description    = $Description
            Title          = $Title
            IsCausedByChange = $IsCausedByChange
            SubCategory    = $SubCategory
            AdditionalData = $AdditionalData
        }
    } | ConvertTo-Json -Depth 3

    $uri = "$Script:BaseUri/api2/incidentapi/incidents($IncidentId)"
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Patch `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $response
}

function Resolve-IcmIncident {
<#
.SYNOPSIS
    对 ICM 工单执行 Resolve（Portal API）
    对应: POST https://portal.microsofticm.com/imp/api/incident/Resolve

.EXAMPLE
    Resolve-IcmIncident -IncidentId 841557607 -RootCauseOption 5
#>
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId,
        [int]$RootCauseOption = 5,
        [string]$HowFixed = "Other",
        [string]$Description = "",
        [bool]$IsCustomerImpacting = $false,
        [string]$ImpactStartTime,
        [bool]$IsNoise = $false,
        [array]$CustomFields = @()
    )

    # 如果未指定 ImpactStartTime，使用工单创建时间
    if (-not $ImpactStartTime) {
        $ImpactStartTime = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    }

    $headers = _Get-Headers
    $headers["Origin"] = "https://portal.microsofticm.com"
    $headers["Referer"] = "https://portal.microsofticm.com/"

    $body = @{
        HowFixed             = $HowFixed
        Description          = $Description
        incidentIds           = @($IncidentId)
        IsCustomerImpacting  = $IsCustomerImpacting
        ImpactStartTime      = $ImpactStartTime
        IsNoise              = $IsNoise
        CustomFields         = $CustomFields
        RootCauseOption      = $RootCauseOption
    } | ConvertTo-Json

    $uri = "https://portal.microsofticm.com/imp/api/incident/Resolve"
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Post `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $response
}

function Resolve-IcmIncidentFull {
<#
.SYNOPSIS
    完整关闭 ICM 工单：Mitigate → 更新 RootCause → Resolve

.EXAMPLE
    Resolve-IcmIncidentFull -IncidentId 841557607 -Message "已完成检查，关闭工单"
#>
    param(
        [Parameter(Mandatory = $true)]
        [long]$IncidentId,
        [string]$Message = "",
        [string]$HowFixed = "Other",
        [int]$RootCauseOption = 5,
        [string]$RootCauseCategory = "Other",
        [bool]$IsCustomerImpacting = $false,
        [bool]$IsNoise = $false
    )

    Write-Verbose "Step 1/3: Mitigating incident $IncidentId..."
    $mitigateResult = Mitigate-IcmIncident `
        -IncidentId $IncidentId `
        -Message $Message `
        -HowFixed $HowFixed `
        -IsCustomerImpacting $IsCustomerImpacting `
        -IsNoise $IsNoise

    Write-Verbose "Step 2/3: Updating root cause for incident $IncidentId..."
    $rootCauseResult = Update-IcmIncidentRootCause `
        -IncidentId $IncidentId `
        -Title $Message `
        -Category $RootCauseCategory

    Write-Verbose "Step 3/3: Resolving incident $IncidentId..."
    $resolveResult = Resolve-IcmIncident `
        -IncidentId $IncidentId `
        -RootCauseOption $RootCauseOption `
        -HowFixed $HowFixed `
        -IsCustomerImpacting $IsCustomerImpacting `
        -IsNoise $IsNoise

    return @{
        Mitigate = $mitigateResult
        RootCause = $rootCauseResult
        Resolve  = $resolveResult
    }
}

function Get-IcmOnCall {
    param(
        [Parameter(Mandatory = $true)]
        [int[]]$TeamIds
    )

    $headers = _Get-Headers
    $body = @{ TeamIds = $TeamIds } | ConvertTo-Json

    $uri = "$Script:OncallBase/Directory/GetCurrentOnCallForCurrentShiftForTeams"
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method Post `
        -Body $body `
        -Headers $headers `
        -ErrorAction Stop

    return $response
}

function Test-IcmToken {
    try {
        $headers = _Get-Headers
        $uri = "$Script:BaseUri/api2/incidentapi/incidents?" + [System.Web.HttpUtility]::UrlEncode("$top") + "=1"
        Invoke-RestMethod -Uri $uri -Method Get -Headers $headers -ErrorAction Stop | Out-Null
        return $true
    } catch {
        Write-Warning "Test-IcmToken failed: $($_.Exception.Message)"
        return $false
    }
}

function Reset-IcmToken {
    $Script:_Token = $null
    $Script:_Config = $null
}

# ===================== 直接运行示例 =====================
if ($MyInvocation.ScriptName -eq $PSCommandPath) {
    Write-Host "=== ICM API PowerShell 客户端 ==="
    Write-Host ""
    Write-Host "用法:"
    Write-Host '  . "$PSScriptRoot\IcmTokenRefresh.ps1"'
    Write-Host '  . "$PSScriptRoot\IcmApi.ps1"'
    Write-Host ""
    Write-Host "  Get-IcmIncidents -Top 5"
    Write-Host "  Get-IcmIncident -IncidentId 123456789"
    Write-Host '  $inc = New-IcmIncident -Title "标题" -Description "描述" -ImpactedServices @(@{ ServiceId = 20284 })'
    Write-Host "  New-IcmIncidentApi -Incident \$inc"
    Write-Host "  Ack-IcmIncident -IncidentId \$inc.Id"
    Write-Host "  Test-IcmToken"
}
