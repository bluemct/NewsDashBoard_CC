# ICM API PowerShell Skill (Microsoft ICM — /api2/ + Portal API)

使用 PowerShell 操作 Microsoft ICM REST API，零外部依赖（仅 Invoke-RestMethod）。

## 文件

所有文件位于 `IcMHelperPS/`：

| 文件 | 用途 |
|------|------|
| `IcmTokenRefresh.ps1` | Token 刷新 + Cookie 管理 |
| `IcmIncident.ps1` | `New-IcmIncident` — 生成 PascalCase JSON |
| `IcmApi.ps1` | 统一 API 封装（自动 Token 刷新） |
| `IcmTest.ps1` | 端到端测试脚本 |
| `icm_config.json` | 共享配置（access_token + cookie_string） |

## 加载与使用

```powershell
cd IcMHelperPS
. .\IcmTokenRefresh.ps1
. .\IcmIncident.ps1
. .\IcmApi.ps1
```

### 创建工单

```powershell
$inc = New-IcmIncident `
    -Title "标题" `
    -Description "描述" `
    -ImpactedServices @(@{ ServiceId = 20284 })
$result = New-IcmIncidentApi -Incident $inc
```

### 查询 / Ack / 讨论

```powershell
Get-IcmIncidents -Top 10
Get-IcmIncident -IncidentId $id
Ack-IcmIncident -IncidentId $id
Add-IcmDiscussion -IncidentId $id -Description "备注"
```

### 关闭工单（Resolve 流程）

关闭 ICM 工单需要 **三步**（Portal API + api2 PATCH）：

**方式一：一键关闭（推荐）**
```powershell
Resolve-IcmIncidentFull -IncidentId $id -Message "已完成检查，关闭工单"
```

**方式二：分步执行**
```powershell
# Step 1: Mitigate（Portal API）
Mitigate-IcmIncident -IncidentId $id -Message "已完成检查"

# Step 2: 更新 RootCause（api2 PATCH）
Update-IcmIncidentRootCause -IncidentId $id -Title "已完成检查" -Category "Other"

# Step 3: Resolve（Portal API）
Resolve-IcmIncident -IncidentId $id -RootCauseOption 5
```

> **关键**：必须先 Mitigate，再 Resolve。直接 Resolve 会失败。
> `Resolve-IcmIncidentFull` 自动按顺序执行三步。

### OnCall 查询

```powershell
Get-IcmOnCall -TeamIds @(37883, 37884)
```

### Token 管理

```powershell
.\IcmTokenRefresh.ps1 refresh   # 刷新 Token
.\IcmTokenRefresh.ps1 verify    # 验证 Token
Test-IcmToken                   # 加载后验证
```

## API 端点

| 函数 | 端点 | 域名 |
|------|------|------|
| `Get-IcmIncidents` | GET `/api2/incidentapi/incidents` | `prod.microsofticm.com` |
| `New-IcmIncidentApi` | POST `/api2/incidentapi/incidents` | `prod.microsofticm.com` |
| `Ack-IcmIncident` | POST `/api2/incidentapi/incidents(id)/AcknowledgeIncident` | `prod.microsofticm.com` |
| `Add-IcmDiscussion` | PATCH `/api2/incidentapi/incidents(id)` | `prod.microsofticm.com` |
| `Mitigate-IcmIncident` | POST `/imp/api/incident/Mitigate` | **`portal.microsofticm.com`** |
| `Update-IcmIncidentRootCause` | PATCH `/api2/incidentapi/incidents(id)` | `prod.microsofticm.com` |
| `Resolve-IcmIncident` | POST `/imp/api/incident/Resolve` | **`portal.microsofticm.com`** |
| `Get-IcmOnCall` | POST `/Directory/GetCurrentOnCall...` | `oncallapi.prod.microsofticm.com` |

> Portal API（Mitigate/Resolve）需要额外 `Origin` + `Referer` 请求头。

## Critical Rules

- **`ImpactedServices` 必须至少包含一个 ServiceId**
- **Token 3 小时有效，Cookie 36 小时有效**
- **关闭工单必须按顺序执行：Mitigate → RootCause → Resolve**
- **Acknowledge 必须调 action**
- **不要通过聊天传 Token**
- **如遇到执行策略限制：`powershell -ExecutionPolicy Bypass -File script.ps1`**
