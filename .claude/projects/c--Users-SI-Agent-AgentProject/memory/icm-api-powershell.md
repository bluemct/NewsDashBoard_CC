---
name: icm-api-powershell
description: ICM API PowerShell 实现 (IcMHelperPS/) — 零依赖, 自动 Token 刷新, 工单 CRUD
metadata:
  type: project
---

# ICM API PowerShell (IcMHelperPS/)

PowerShell 5.1 零依赖实现 Microsoft ICM REST API (/api2/) 客户端，与 Python 版 (IcMHelper/) 共享 icm_config.json。

## 文件结构

- `IcmApi.ps1` — 统一 API 封装（Token 管理、读取、创建、Ack、Discussion、Resolve、On-Call）
- `IcmIncident.ps1` — `New-IcmIncident` 函数，构造工单 JSON（复刻 C# IcmDll.CreateIncident）
- `IcmTokenRefresh.ps1` — Token 刷新工具（Cookie 换 access_token）
- `IcmTest.ps1` — 端到端测试脚本
- `_create_incident.ps1` — 实际创建工单脚本
- `icm_config.json` — Token + Cookie 配置
- `SKILL.md` — 文档（含用法、参数、Critical Rules）

## 关键用法

```powershell
. .\IcmTokenRefresh.ps1; . .\IcmIncident.ps1; . .\IcmApi.ps1
$inc = New-IcmIncident -Title "标题" -Description "描述" -ImpactedServices @(@{ ServiceId = 20284 })
$result = New-IcmIncidentApi -Incident $inc
Ack-IcmIncident -IncidentId $result.Id
```

## 关键修复

**PS 5.1 `[ordered]@{}` 管道 Bug**: OrderedDictionary 不能通过 `|` 管道传给函数（接收端得 `$null`）。必须用参数调用 `Func -Dict $dict` 而非 `$dict | Func`。详见 [[icm-api-powershell]] SKILL.md 中的已知 Bug 与修复。

## 状态

所有 API 已测试通过：
- Token 验证 ✓
- 读取工单 (Get-IcmIncidents, Get-IcmIncident) ✓
- 创建工单 (New-IcmIncidentApi) ✓
- Acknowledge (Ack-IcmIncident) ✓

## 相关

- Python 版: [[icm-api-python]]
- SKILL: `.claude/skills/icm-api-ps/`
