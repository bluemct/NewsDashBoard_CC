<#
.SYNOPSIS
    ICM 创建 Incident 测试 — PowerShell 版本

.DESCRIPTION
    读取 icm_config.json 中的 Token，构造工单，POST 到 ICM API
    对应 Python icm_create_test.py

.USAGE
    .\IcmTest.ps1

.NOTES
    需要先 dot-source 依赖脚本
#>

# 加载依赖
. (Join-Path $PSScriptRoot "IcmTokenRefresh.ps1")
. (Join-Path $PSScriptRoot "IcmIncident.ps1")
. (Join-Path $PSScriptRoot "IcmApi.ps1")

Write-Host "=== ICM PowerShell API 测试 ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: 验证 Token ---
Write-Host "--- Step 1: 验证 Token ---"
$tokenValid = Test-IcmToken
if ($tokenValid) {
    Write-Host "[OK] Token 有效" -ForegroundColor Green
} else {
    Write-Host "[WARN] Token 可能过期，尝试刷新..." -ForegroundColor Yellow
    Invoke-RefreshToken
    $tokenValid = Test-IcmToken
    if ($tokenValid) {
        Write-Host "[OK] 刷新后 Token 有效" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Token 无效，请检查 icm_config.json" -ForegroundColor Red
        exit 1
    }
}
Write-Host ""

# --- Step 2: 读取最近 5 个工单 ---
Write-Host "--- Step 2: 读取最近 5 个工单 ---"
try {
    $incidents = Get-IcmIncidents -Top 5
    foreach ($inc in $incidents) {
        Write-Host "  [$($inc.Id)] $($inc.Title) (Severity: $($inc.Severity), State: $($inc.State))"
    }
    Write-Host "[OK] 共读取 $($incidents.Count) 个工单" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] 读取工单失败: $_" -ForegroundColor Red
}
Write-Host ""

# --- Step 3: 构造新工单 ---
Write-Host "--- Step 3: 构造工单 JSON ---"
$inc = New-IcmIncident `
    -Title "[PowerShell Test] ICM Ticket via PowerShell" `
    -Description "This is a test incident created from PowerShell using the ICM API directly, replicating the C# IcmDll.CreateIncident class." `
    -Summary "PowerShell API test incident" `
    -Severity 3 `
    -OwningTeamId 37883 `
    -ImpactedServices @(@{ ServiceId = 20284 }) `
    -ImpactedTeams @(@{ TeamId = 37883 })

$json = $inc | ConvertTo-Json -Depth 4
Write-Host $json
Write-Host ""

# --- Step 4: 发送 POST 请求 ---
Write-Host "--- Step 4: 发送 POST 请求创建工单 ---"
try {
    $result = New-IcmIncidentApi -Incident $inc
    $newId = $result.Id
    Write-Host ""
    Write-Host "[OK] Incident created! New ID: $newId" -ForegroundColor Green

    # --- Step 5: 验证新工单 ---
    Write-Host ""
    Write-Host "--- Step 5: 验证新工单 ---"
    $fetched = Get-IcmIncident -IncidentId $newId
    if ($fetched) {
        Write-Host "  查询结果: [$($fetched.Id)] $($fetched.Title)" -ForegroundColor Green
        Write-Host "  State: $($fetched.State), Severity: $($fetched.Severity)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] 无法查询到新工单" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] 创建工单失败: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $respBody = $reader.ReadToEnd()
        $reader.Close()
        Write-Host "Response: $respBody" -ForegroundColor Red
    }
}
