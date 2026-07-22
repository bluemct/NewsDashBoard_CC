# ICM API Skill

Connect to Microsoft ICM (Incident Command Center) API to read and create incidents via Python.

## Files

| File | Purpose |
|------|---------|
| `icm_create_incident.py` | `CreateIncident` 类定义，字段与 C# `IcmDll.CreateIncident` 一致 |
| `icm_config.json` | Token + Cookie 存储（已在 .gitignore） |

## Architecture

ICM API **只需要 Token** 即可调用，Cookie 仅在首次换 Token 时使用：

```
浏览器登录 ICM → 复制 Cookie → POST /sso2/token (grant_type=cookie)
    → 返回 access_token (3小时有效)
    → 调用 /api2/ API (只用 Token, 不需要 Cookie)
```

| 配置 | 值 |
|------|------|
| API 域名 | `https://prod.microsofticm.com` |
| Token 端点 | `https://portal.microsofticm.com/sso2/token` |
| Token 有效期 | **3 小时** |
| Cookie 有效期 | **一次性**（换 Token 后 `CloudESAuthCookie` 被服务端更新） |
| 认证 Header | `Authorization: Bearer {token}` |
| 返回格式 | OData JSON，列表数据在 `value` 数组中，单条在根对象 |

## Quick Start

### 1. 获取 Token

```python
import requests

cookies = {"CloudESAuthCookie": "从浏览器复制..."}
headers = {
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://portal.microsofticm.com",
    "referer": "https://portal.microsofticm.com/imp/v3/",
}
resp = requests.post(
    "https://portal.microsofticm.com/sso2/token",
    data="grant_type=cookie",
    headers=headers,
    cookies=cookies,
)
token = resp.json()["access_token"]
```

### 2. 读取工单

```python
headers = {"Authorization": "Bearer " + token}

# 搜索 Incident
resp = requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?top=10", headers=headers)
data = resp.json()
incidents = data["value"]  # OData 格式

# 按 Id 查找
resp = requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?filter=Id eq 838833853", headers=headers)

# 按条件搜索
resp = requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?filter=State eq 'ACTIVE' and Severity eq 2&top=5", headers=headers)
```

### 3. 创建工单

```python
from icm_create_incident import CreateIncident

inc = CreateIncident()
inc.Title = "工单标题"
inc.Description = "详细描述"
inc.Summary = "摘要"
inc.Severity = 3          # 1-4, 1 最严重 (默认 3)
inc.ImpactedServices = [{"ServiceId": 20284}]   # ⚠️ 必须指定
inc.ImpactedTeams = [{"TeamId": 37883}]

headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
resp = requests.post(
    "https://prod.microsofticm.com/api2/incidentapi/incidents",
    json=inc.to_dict(),
    headers=headers,
)
# 201 Created → 新工单在 resp.json()["Id"]
```

## Critical Rules

- **`ImpactedServices` 必须至少包含一个 ServiceId**，否则返回 400 验证失败
- Token 是唯一的认证方式，Cookie 只在换 Token 时用
- Cookie 是一次性的，换 Token 后旧的 `CloudESAuthCookie` 失效，服务端会返回新的
- 聊天窗口传 JWT Token 会损坏（3000+ 字符），不要通过聊天传 Token

## 常见 OwningServiceId / OwningTeamId

| Service | Team | ServiceId | TeamId |
|---------|------|-----------|--------|
| Azure Incident Management China | PS | 20284 | 37883 |
| Azure Incident Management China | wasu-mooncake | 20284 | 22590 |
