# ICM API PowerShell Skill (Microsoft ICM — /api2/)

使用 PowerShell 操作 Microsoft ICM REST API，基于 `Invoke-RestMethod`，无需 Python 依赖。

## 文件结构

所有文件位于 `IcMHelperPS/`：

| 文件 | 用途 | 对应 Python |
|------|------|-------------|
| `IcmApi.ps1` | 全部 API（Token、工单构造、查询、创建、Ack、Discussion、Resolve、On-Call）| `icm_api.py` |
| `IcmTokenRefresh.ps1` | Token 刷新工具 — 用 Cookie 换新的 access_token，验证 Token 有效性 | `icm_token_refresh.py` |
| `icm_config.json` | 存储 `access_token` + `cookie_string`（与 Python 版共享） | `icm_config.json` |
| `refresh_log.jsonl` | 刷新日志（与 Python 版共享） | `refresh_log.jsonl` |
| `_create_incident.ps1` | 入口脚本示例（展示如何调用 API） | - |
| `IcmTest.ps1` | 测试脚本（已废弃，可删除） | `icm_create_test.py` |

> **注意**：`IcmIncident.ps1` 已合并到 `IcmApi.ps1`，不再需要单独加载。

## 架构

```
浏览器登录 ICM → 复制 Cookie → POST /sso2/token (grant_type=cookie)
    → 返回 access_token (JWT, 3小时有效) + 新 Cookie (36小时有效)
    → 写入 icm_config.json（Python/PowerShell 共享）
    → PowerShell 读取 JWT → Bearer 认证调用 /api2/ API
```

**PowerShell 端只需要：**
1. 从 `icm_config.json` 读取 `access_token`
2. 用 `New-IcmIncident` 构造工单
3. POST 到 `https://prod.microsofticm.com/api2/incidentapi/incidents`

**零外部依赖** — 仅使用 PowerShell 内置 cmdlet (`Invoke-RestMethod`, `ConvertTo-Json`)

## 部署条件

- **PowerShell 5.1**（Windows Server 自带）
- **网络**：能访问 `prod.microsofticm.com`、`portal.microsofticm.com`、`oncallapi.prod.microsofticm.com`
- **TLS 1.2**：脚本自动设置（旧 Windows Server 默认 Tls1.0，不支持）
- **文件编码**：所有 `.ps1` 文件必须为 **UTF-8 with BOM**（否则中文乱码）
- **ExecutionPolicy**：`powershell -ExecutionPolicy Bypass -File .\xxx.ps1`

## 快速开始

### 加载模块

```powershell
cd IcMHelperPS
. .\IcmTokenRefresh.ps1
. .\IcmApi.ps1
```

### 创建工单

```powershell
$inc = New-IcmIncident `
    -Title "工单标题" `
    -Description "详细描述" `
    -Summary "摘要" `
    -Severity 3 `
    -OwningTeamId 37883 `
    -ImpactedServices @(@{ ServiceId = 20284 })  # ⚠️ 必须指定

$result = New-IcmIncidentApi -Incident $inc
$newId = $result.Id
```

### 查询工单

```powershell
# 按 ID 查询
$inc = Get-IcmIncident -IncidentId $newId

# 查询最近 10 个工单
$incidents = Get-IcmIncidents -Top 10

# 带 OData filter 查询
$incidents = Get-IcmIncidents -Filter "Id eq 838833853" -Top 1
```

### Acknowledge 工单

```powershell
# ⚠️ 必须调 AcknowledgeIncident action（OData 风格），直接 PATCH IsAcknowledged 不生效
Ack-IcmIncident -IncidentId $newId
```

### 更新工单描述（Discussion）

```powershell
# 实际是 PATCH 工单的 Description 字段
Add-IcmDiscussion -IncidentId $newId -Description "处理进展更新"
```

### 解决工单

```powershell
Resolve-IcmIncident -IncidentId $newId -Message "已修复服务"
```

### 查询当前值班人员 (On-Call)

```powershell
$oncall = Get-IcmOnCall -TeamIds @(37883)
$oncall.value[0].ShiftCurrentOnCalls | ForEach-Object {
    $_.CurrentOnCallContacts | ForEach-Object {
        "$($_.LastName) $($_.FirstName) ($($_.Alias))"
    }
}
```

> On-call API 域名是 `oncallapi.prod.microsofticm.com`（不同于工单 API 的 `prod.microsofticm.com`）

### Token 管理

```powershell
.\IcmTokenRefresh.ps1 refresh     # 刷新 Token + Cookie
.\IcmTokenRefresh.ps1 verify      # 验证 Token 是否有效
.\IcmTokenRefresh.ps1 both        # 刷新 + 验证
```

## New-IcmIncident 参数说明

精确复刻 C# `IcmDll.CreateIncident` 类的字段名和默认值，输出 PascalCase JSON。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `Title` | `$null` | 工单标题 |
| `Description` | `"Incident Created"` | 详细描述 |
| `Summary` | `$null` | 摘要 |
| `Severity` | `3` | 严重级别 1-4 |
| `OwningServiceId` | `20284` | 归属服务 |
| `OwningTeamId` | `37883` | 归属团队 |
| `IsSecurityRisk` | `$false` | 是否安全风险 |
| `IsCustomerImpacting` | `$false` | 是否影响客户 |
| `ImpactedServices` | `@()` | 影响的服务列表 |
| `ImpactedTeams` | `@()` | 影响的团队列表 |
| `ImpactedComponents` | `@()` | 影响的组件列表 |
| `CustomFields` | `@()` | 自定义字段 |
| `Keywords` | `$null` | 关键词 |
| `CustomerName` | `$null` | 客户名称 |
| `SupportTicketId` | `$null` | 支持工单号 |
| `SubscriptionId` | `$null` | 订阅 ID |

## API 函数速查

| 函数 | 操作 | 方法 | URL |
|------|------|------|-----|
| `Get-IcmIncidents` | 查询工单列表 | GET | `/incidents?$top=N` |
| `Get-IcmIncident` | 按 ID 查询工单 | GET | `/incidents?filter=Id eq {id}` |
| `New-IcmIncidentApi` | 创建工单 | POST | `/incidents` |
| `Ack-IcmIncident` | Acknowledge | POST | `/incidents({id})/AcknowledgeIncident` |
| `Add-IcmDiscussion` | 更新描述 | PATCH | `/incidents({id})` |
| `Resolve-IcmIncident` | 解决工单 | POST | `/incidents({id})/mitigate` |
| `Get-IcmOnCall` | 查询值班人员 | POST | `oncallapi/.../GetCurrentOnCall...` |
| `Test-IcmToken` | 验证 Token | GET | `/incidents?$top=1` |
| `Reset-IcmToken` | 清除缓存 Token | - | - |

## 与 Python 版对比

| 特性 | Python (IcMHelper/) | PowerShell (IcMHelperPS/) |
|------|---------------------|---------------------------|
| 依赖 | `requests` | 无（仅 PowerShell 内置 cmdlet） |
| 配置 | 共享 `icm_config.json` | 共享 `icm_config.json` |
| 日志 | 共享 `refresh_log.jsonl` | 共享 `refresh_log.jsonl` |
| Token 刷新 | `python icm_token_refresh.py refresh` | `.\IcmTokenRefresh.ps1 refresh` |
| 数据类 | `CreateIncident` class | `New-IcmIncident` → hashtable (OrderedDictionary) |
| 序列化 | `inc.to_json()` | `\| ConvertTo-Json -Depth 4` |
| HTTP 客户端 | `requests.post()` | `Invoke-RestMethod` |
| 自动 Token 刷新 | `IcmClient._ensure_token()` | `IcmApi.ps1::_Ensure-Token` |
| 适合场景 | CI/CD、跨平台 | Windows 原生、无需安装 Python |

## Critical Rules

- **`ImpactedServices` 必须至少包含一个 ServiceId**，否则返回 400 验证失败
- **Token 有效期 3 小时**，过期后运行 `.\IcmTokenRefresh.ps1 refresh`
- **Cookie 有效期 36 小时**，接近过期时刷新才会返回新 Cookie，需每 24 小时至少刷新一次
- **Acknowledge 必须调 action** — 直接 PATCH `IsAcknowledged` 字段不生效
- **Discussion = PATCH Description** — 实际是 PATCH `incidents({id})`，Body 包含 `{"Id":{id},"Description":"..."}`
- **不要通过聊天传 Token** — JWT 3000+ 字符会被损坏

## 已知 Bug 与修复

### PowerShell 5.1 `[ordered]@{}` 管道传递问题（2026-07-27 修复）

**症状**: `New-IcmIncident` 报错 "无法对 Null 数组进行索引"

**根因**: PS 5.1 中 `[ordered]@{}` (OrderedDictionary) 通过管道 `|` 传给函数时，接收端得到 `$null`

**修复**: 直接参数调用 `ConvertTo-IcmIncidentPsNoteProperty -Dict $dict`，不走管道

### 文件拷贝后 URL 解析失败（2026-07-27 修复）

**症状**: `Invoke-VerifyToken` 报 "无效的 URI: 未能分析主机名"

**根因**: PowerShell 反引号 `` `$top=1 `` 转义在文件拷贝过程中可能损坏

**修复**: URL 拼接改用 `[System.Web.HttpUtility]::UrlEncode()`，不再依赖反引号转义

### Add-IcmDiscussion 实际是 PATCH 描述（2026-07-27 修复）

**症状**: 报 404，`/incidents/{id}/discussion` 端点不存在

**根因**: 浏览器抓包确认 ICM Discussion 实际是 PATCH `incidents({id})`，更新 Description 字段

**修复**: 改为 `PATCH` 方法 + OData 风格 URL + Body 包含 Id 和 Description

## 常见 OwningServiceId / OwningTeamId

| Service | Team | ServiceId | TeamId |
|---------|------|-----------|--------|
| Azure Incident Management China | PS | 20284 | 37883 |
| Azure Incident Management China | wasu-mooncake | 20284 | 22590 |
