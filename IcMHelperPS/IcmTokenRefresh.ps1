# ICM Token 自动刷新 — 用 cookie 换取新的 access_token
# 每次刷新记录完整日志到 refresh_log.jsonl
#
# PowerShell 5.1+ 兼容版本，对应 Python icm_token_refresh.py
# 从 icm_config.json 读取 cookie_string，自动提取 CloudESAuthCookie 换取新 Token
#
# 用法:
#   .\IcmTokenRefresh.ps1 refresh     # 刷新 Token + Cookie
#   .\IcmTokenRefresh.ps1 verify      # 验证 Token 是否有效
#   .\IcmTokenRefresh.ps1 both        # 刷新 + 验证

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("refresh", "verify", "both")]
    [string]$Action = "refresh"
)

# 强制 TLS 1.2 — 旧 Windows Server 默认 Tls1.0，HTTPS 调用会失败
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11

$Script:ConfigPath  = Join-Path $PSScriptRoot "icm_config.json"
$Script:LogPath     = Join-Path $PSScriptRoot "refresh_log.jsonl"
$Script:TokenUrl    = "https://portal.microsofticm.com/sso2/token"
$Script:ApiUrl      = "https://prod.microsofticm.com/api2/incidentapi/incidents"

# 北京时间偏移
$Script:BeijingOffset = [TimeSpan]::FromHours(8)

function Get-NowFormatted {
    $utc  = [DateTimeOffset]::UtcNow
    $bj   = $utc.ToOffset($Script:BeijingOffset)
    return @{
        Utc  = $utc.UtcDateTime.ToString("HH:mm:ss UTC")
        Bj   = $bj.LocalDateTime.ToString("HH:mm:ss CST")
    }
}

function Format-Ts {
    param($Now, [string]$Msg)
    return "[{0}] [{1}] {2}" -f $Now.Utc, $Now.Bj, $Msg
}

function Write-LogEntry {
    param([hashtable]$Entry)
    if ($null -eq $Entry) { return }
    $Entry["timestamp"] = [DateTimeOffset]::UtcNow.ToString("o")
    try {
        $json = $Entry | ConvertTo-Json -Compress -Depth 2 -ErrorAction Stop
        Add-Content -Path $Script:LogPath -Value $json -Encoding UTF8
    } catch { }
}

function Extract-AuthCookie {
    param([string]$CookieString)
    if (-not $CookieString) { return $null }
    $parts = $CookieString -split ';'
    foreach ($part in $parts) {
        $trimmed = $part.Trim()
        if ($trimmed.StartsWith("CloudESAuthCookie=")) {
            return $trimmed.Substring("CloudESAuthCookie=".Length)
        }
    }
    return $null
}

function Load-Config {
    try {
        $json = Get-Content -Path $Script:ConfigPath -Raw -Encoding UTF8
        return $json | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "读取配置失败: $_"
    }
}

function Save-Config {
    param($Config)
    $json = $Config | ConvertTo-Json -Depth 4
    Set-Content -Path $Script:ConfigPath -Value $json -Encoding UTF8
}

function Parse-JwtExpiry {
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

function Invoke-RefreshToken {
    $now = Get-NowFormatted
    Write-Host (Format-Ts -Now $now -Msg "开始刷新 Token...")

    # --- Step 1: 读取 config ---
    try {
        $config = Load-Config
    } catch {
        Write-Host "[FAIL] $_"
        return
    }

    # --- Step 2: 提取 CloudESAuthCookie ---
    $authCookie = Extract-AuthCookie -CookieString $config.cookie_string

    if (-not $authCookie) {
        Write-Host "[FAIL] 未找到 CloudESAuthCookie"
        return
    }

    $cookiePrefix = $authCookie.Substring(0, [Math]::Min(40, $authCookie.Length))
    Write-Host (Format-Ts -Now $now -Msg "Cookie: $cookiePrefix... (len=$($authCookie.Length))")

    # --- Step 3: 发送换 Token 请求 (WebClient 可获取 Set-Cookie) ---
    $responseText = ""
    $setCookieHeader = ""

    try {
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("content-type", "application/json;charset=UTF-8")
        $wc.Headers.Add("origin", "https://portal.microsofticm.com")
        $wc.Headers.Add("referer", "https://portal.microsofticm.com/imp/v3/")
        $wc.Headers.Add("Cookie", "CloudESAuthCookie=$authCookie")

        $encoding = [System.Text.Encoding]::UTF8
        $bytes = $encoding.GetBytes("grant_type=cookie")
        $respBytes = $wc.UploadData($Script:TokenUrl, "POST", $bytes)
        $responseText = $encoding.GetString($respBytes)

        # 获取 Set-Cookie
        if ($wc.ResponseHeaders -and $wc.ResponseHeaders["Set-Cookie"]) {
            $setCookieHeader = $wc.ResponseHeaders["Set-Cookie"]
        }
        $wc.Dispose()
    } catch {
        $msg = "[FAIL] 请求异常: $($_.Exception.Message)"
        Write-Host $msg
        if ($_.Exception.Response) {
            $resp = $_.Exception.Response
            Write-Host "[FAIL] HTTP Status: $($resp.StatusCode.value__)"
        }
        return
    }

    # --- Step 4: 解析响应 ---
    $respJson = $responseText | ConvertFrom-Json
    $newToken = $respJson.access_token

    if (-not $newToken) {
        Write-Host "[FAIL] 返回中未找到 access_token"
        Write-Host "Response: $($responseText.Substring(0, [Math]::Min(200, $responseText.Length)))"
        return
    }

    # --- Step 5: 更新 config ---
    $cookieUpdated = $false
    $cookieChanged = $false

    # 提取新 Cookie
    $newCookieFromHeader = $null
    if ($setCookieHeader) {
        $scParts = $setCookieHeader -split ';'
        foreach ($sc in $scParts) {
            $sct = $sc.Trim()
            if ($sct.StartsWith("CloudESAuthCookie=")) {
                $val = $sct.Substring("CloudESAuthCookie=".Length)
                if ($val -ne "") {
                    $newCookieFromHeader = $val
                    break
                }
            }
        }
    }

    if ($newCookieFromHeader) {
        $config.access_token = $newToken
        $config.cookie_string = "CloudESAuthCookie=$newCookieFromHeader"
        $cookieUpdated = $true
        $cookieChanged = ($newCookieFromHeader -ne $authCookie)
    } else {
        $config.access_token = $newToken
    }

    # 从 Set-Cookie 提取 Cookie 过期时间
    if ($setCookieHeader) {
        $scAll = $setCookieHeader -split ';'
        foreach ($sc in $scAll) {
            $sct = $sc.Trim()
            if ($sct.StartsWith("expires=")) {
                $expRaw = $sct.Substring("expires=".Length).Trim()
                try {
                    $expDt = [DateTimeOffset]::Parse($expRaw).ToOffset([TimeSpan]::Zero)
                    $config.cookie_expires = $expDt.UtcDateTime.ToString("o")
                } catch { }
                break
            }
        }
    }

    Save-Config -Config $config

    # --- Step 6: 解析 Token 有效期 ---
    $tokenExp = Parse-JwtExpiry -Token $newToken
    $remainingHours = ($tokenExp - [DateTimeOffset]::UtcNow).TotalHours
    $expBj = $tokenExp.ToOffset($Script:BeijingOffset)

    $expUtcStr = $tokenExp.UtcDateTime.ToString("yyyy-MM-dd HH:mm")
    $expBjStr  = $expBj.LocalDateTime.ToString("yyyy-MM-dd HH:mm")

    Write-Host (Format-Ts -Now $now -Msg "Token 刷新成功，有效期 $([math]::Round($remainingHours, 1)) 小时 (至 $expUtcStr UTC / $expBjStr CST)")

    if ($cookieUpdated) {
        if ($cookieChanged) {
            $changeStr = "已变化"
        } else {
            $changeStr = "未变化"
        }
        Write-Host (Format-Ts -Now $now -Msg "Cookie 已更新 ($changeStr, len=$($newCookieFromHeader.Length))")

        if ($config.cookie_expires) {
            $ceDt = [DateTimeOffset]::Parse($config.cookie_expires)
            $ceBj = $ceDt.ToOffset($Script:BeijingOffset)
            $ceRem = ($ceDt - [DateTimeOffset]::UtcNow).TotalHours
            $ceUtcStr = $ceDt.UtcDateTime.ToString("yyyy-MM-dd HH:mm")
            $ceBjStr  = $ceBj.LocalDateTime.ToString("yyyy-MM-dd HH:mm")
            Write-Host (Format-Ts -Now $now -Msg "Cookie 过期时间: ($ceUtcStr UTC / $ceBjStr CST, 剩余 $([math]::Round($ceRem, 1))h)")
        }
    } else {
        Write-Host (Format-Ts -Now $now -Msg "[WARN] Cookie 未更新")
        if ($config.cookie_expires) {
            $ceDt = [DateTimeOffset]::Parse($config.cookie_expires)
            $ceBj = $ceDt.ToOffset($Script:BeijingOffset)
            $ceRem = ($ceDt - [DateTimeOffset]::UtcNow).TotalHours
            $ceUtcStr = $ceDt.UtcDateTime.ToString("yyyy-MM-dd HH:mm")
            $ceBjStr  = $ceBj.LocalDateTime.ToString("yyyy-MM-dd HH:mm")
            Write-Host (Format-Ts -Now $now -Msg "[WARN] Cookie 过期时间: ($ceUtcStr UTC / $ceBjStr CST, 剩余 $([math]::Round($ceRem, 1))h) (上次记录)")
        }
    }

    # 写日志
    $log = @{
        action                = "refresh"
        status                = "ok"
        token_prefix          = $newToken.Substring(0, [Math]::Min(40, $newToken.Length))
        token_length          = $newToken.Length
        token_exp             = $tokenExp.UtcDateTime.ToString("o")
        token_remaining_hours = [math]::Round($remainingHours, 2)
        cookie_updated        = $cookieUpdated
        cookie_changed        = $cookieChanged
    }
    if ($newCookieFromHeader) {
        $log["new_cookie_length"] = $newCookieFromHeader.Length
    }
    Write-LogEntry @log
}

function Invoke-VerifyToken {
    $now = Get-NowFormatted

    try {
        $config = Load-Config
        $token = $config.access_token
    } catch {
        Write-Host "[FAIL] $_"
        return
    }

    $headers = @{
        "Authorization" = "Bearer $token"
        "Accept"        = "application/json"
    }

    try {
        $verifyUri = "$Script:ApiUrl" + "?" + [System.Web.HttpUtility]::UrlEncode("`$top") + "=1"
        $response = Invoke-RestMethod -Uri $verifyUri -Method Get -Headers $headers -ErrorAction Stop

        $value = $response.value
        $count = if ($value) { @($value).Count } else { 0 }
        Write-Host (Format-Ts -Now $now -Msg "Token 有效，当前 $count 个工单")

        Write-LogEntry @{
            action         = "verify"
            status         = "ok"
            token_prefix   = $token.Substring(0, [Math]::Min(40, $token.Length))
            incident_count = $count
        }
    } catch {
        $statusCode = 0
        $failMsg = $_.Exception.Message
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
        }
        Write-Host (Format-Ts -Now $now -Msg "Token 失效 (HTTP $statusCode) — $failMsg")

        Write-LogEntry @{
            action          = "verify"
            status          = "fail"
            token_prefix    = $token.Substring(0, [Math]::Min(40, $token.Length))
            response_status = $statusCode
            error_message   = $failMsg
        }
    }
}

# ===================== 入口 =====================
# 仅在直接运行时执行（dot-source 时跳过）
if ($MyInvocation.ScriptName -eq $PSCommandPath) {
    switch ($Action) {
        "refresh" { Invoke-RefreshToken }
        "verify"  { Invoke-VerifyToken }
        "both"    { Invoke-RefreshToken; Invoke-VerifyToken }
    }
}
