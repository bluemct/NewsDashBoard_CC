$baseDir = 'C:\Users\SI-Agent\AgentProject\IcMHelperPS'

. (Join-Path $baseDir "IcmTokenRefresh.ps1")
. (Join-Path $baseDir "IcmApi.ps1")

Write-Host "Step 1: Token check"
$ok = Test-IcmToken
Write-Host ("Token valid: " + $ok)

Write-Host ""
Write-Host "Step 2: List 2 incidents"
$incs = Get-IcmIncidents -Top 2
foreach ($i in $incs) {
    Write-Host ("  [ID:" + $i.Id + "] " + $i.Title)
}

Write-Host ""
Write-Host "Step 3: New-IcmIncident"
$inc = New-IcmIncident -Title "TLS12 Test" -Description "test" -ImpactedServices @(@{ ServiceId = 20284 })
Write-Host ("Title=" + $inc.Title + " State=" + $inc.State)

Write-Host ""
Write-Host "All OK"
