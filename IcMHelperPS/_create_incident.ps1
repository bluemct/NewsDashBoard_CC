Set-Location 'C:\Users\SI-Agent\AgentProject\IcMHelperPS'
. .\IcmTokenRefresh.ps1
. .\IcmApi.ps1
. .\IcmIncident.ps1

Write-Output "=== 创建 ICM 工单 ==="
Write-Output ""

$inc = New-IcmIncident `
    -Title "PKI handover session1 By John" `
    -Description "PKI handover session1 By John" `
    -Summary "PKI handover session1 By John" `
    -OwningTeamId 37883 `
    -ImpactedServices @(@{ ServiceId = 20284 }) `
    -ImpactedTeams @(@{ TeamId = 37883 })

$inc.Type = "customerreported"

Write-Output "Title: $($inc.Title)"
Write-Output "Description: $($inc.Description)"
Write-Output "Type: $($inc.Type)"
Write-Output "OwningServiceId: $($inc.OwningServiceId)"
Write-Output "OwningTeamId: $($inc.OwningTeamId)"
Write-Output "ImpactedServices: $($inc.ImpactedServices | ConvertTo-Json -Compress)"
Write-Output ""
Write-Output "--- 发送请求 ---"

try {
    $result = New-IcmIncidentApi -Incident $inc
    Write-Output ""
    Write-Output "OK! 工单创建成功"
    Write-Output "New Incident ID: $($result.Id)"
    Write-Output "Title: $($result.Title)"
    Write-Output "State: $($result.State)"
    Write-Output "Severity: $($result.Severity)"
} catch {
    Write-Output "FAILED: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        Write-Output "HTTP Status: $($_.Exception.Response.StatusCode.value__)"
    }
}
