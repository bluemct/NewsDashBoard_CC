# ICM API Skill (Microsoft ICM — /api2/)

Operate incidents via Microsoft ICM REST API using a pre-obtained Bearer token. Pure Python `requests`, no DLL dependency.

## Files

All files live in `IcMHelper/`:

| File | Purpose |
|------|---------|
| `icm_create_incident.py` | `CreateIncident` 数据类定义，序列化 JSON（不含 API 调用逻辑） |
| `icm_create_test.py` | 测试脚本 — 读取 config，构造工单，POST 到 ICM API |
| `icm_token_refresh.py` | Token 刷新工具 — 用 Cookie 换新的 access_token，验证 Token 有效性 |
| `icm_config.json` | 存储 `access_token` (JWT) + `cookie_string`（已在 .gitignore） |
| `refresh_log.jsonl` | 刷新日志（每次请求的完整记录） |

## Architecture

```
浏览器登录 ICM → 复制 Cookie → POST /sso2/token (grant_type=cookie)
    → 返回 access_token (JWT, 3小时有效) + 新 Cookie (36小时有效)
    → 写入 icm_config.json
    → Python 读取 JWT → Bearer 认证调用 /api2/ API
```

**Python 端只需要：**
1. 从 `icm_config.json` 读取 `access_token`
2. 构造 `CreateIncident` 对象并序列化 JSON
3. POST 到 `https://prod.microsofticm.com/api2/incidentapi/incidents`

**唯一依赖：** `requests`

## Quick Start

```python
import json
import requests
from icm_create_incident import CreateIncident

# 1. 读取 Token
config = json.load(open("icm_config.json", encoding="utf-8"))
TOKEN = config["access_token"]

HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/json",
    "Content-Type": "application/json",
}
```

### 创建工单

```python
inc = CreateIncident()
inc.Title = "工单标题"
inc.Description = "详细描述"
inc.ImpactedServices = [{"ServiceId": 20284}]  # ⚠️ 必须指定

resp = requests.post(
    "https://prod.microsofticm.com/api2/incidentapi/incidents",
    json=inc.to_dict(),
    headers=HEADERS,
)
# 201 Created → 新工单在 resp.json()["Id"]
new_id = resp.json()["Id"]
```

### 查询工单

```python
# 按 ID 查询（OData ID 路径）
resp = requests.get(
    f"https://prod.microsofticm.com/api2/incidentapi/incidents({new_id})",
    headers=HEADERS,
)
inc = resp.json()

# 查询最近 10 个工单
resp = requests.get(
    "https://prod.microsofticm.com/api2/incidentapi/incidents",
    headers=HEADERS,
)
incidents = resp.json()["value"]  # OData 格式
```

### Acknowledge 工单

```python
# ⚠️ 不能直接 PATCH IsAcknowledged（返回 204 但不生效）
# 必须调用 AcknowledgeIncident action
body = {
    "AcknowledgementParameters": {
        "AcknowledgeContactAlias": None
    }
}
resp = requests.post(
    f"https://prod.microsofticm.com/api2/incidentapi/incidents({new_id})/AcknowledgeIncident",
    json=body,
    headers=HEADERS,
)
# 200 OK → 查询确认 IsAcknowledged = True
```

### 查询当前值班人员 (On-Call)

```python
# 查询指定团队的当前值班人员
resp = requests.post(
    "https://oncallapi.prod.microsofticm.com/Directory/GetCurrentOnCallForCurrentShiftForTeams",
    json={"TeamIds": [37883]},  # TeamId 列表
    headers=HEADERS,
)
# 200 OK
data = resp.json()
for shift in data["value"][0]["ShiftCurrentOnCalls"]:
    for contact in shift["CurrentOnCallContacts"]:
        print(f"{contact['LastName']} {contact['FirstName']} ({contact['Alias']})")
```

> On-call API 域名是 `oncallapi.prod.microsofticm.com`（不同于工单 API 的 `prod.microsofticm.com`）

### 运行测试

```bash
cd IcMHelper
python icm_create_test.py
```

## CreateIncident 类说明

精确复刻 C# `IcmDll.CreateIncident` 类的字段名和默认值，序列化输出 PascalCase JSON。

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `Id` | 0 | 新建工单为 0，创建后由 API 返回真实 ID |
| `Title` | `None` | 工单标题 |
| `Description` | `"Incident Created"` | 详细描述 |
| `Summary` | `None` | 摘要 |
| `Severity` | `3` | 严重级别 1-4 |
| `State` | `"ACTIVE"` | 工单状态 |
| `Type` | `"LiveSite"` | 工单类型 |
| `CloudInstanceId` | `3` | 云实例 ID |
| `OwningServiceId` | `20284` | 归属服务 |
| `OwningTeamId` | `37883` | 归属团队 |
| `IsSecurityRisk` | `False` | 是否安全风险 |
| `IsCustomerImpacting` | `False` | 是否影响客户 |
| `ImpactedServices` | `[]` | 影响的服务列表 |
| `ImpactedTeams` | `[]` | 影响的团队列表 |

**序列化方法：**
- `inc.to_dict()` → Python dict (PascalCase key)
- `inc.to_json(indent=2)` → JSON 字符串

## Token 管理

### 刷新 Token + Cookie（推荐）

```bash
cd IcMHelper
python icm_token_refresh.py refresh     # 刷新 Token + Cookie
python icm_token_refresh.py verify      # 验证 Token 是否有效
python icm_token_refresh.py both        # 刷新 + 验证
```

脚本会从 `icm_config.json` 读取 `cookie_string`，自动提取 `CloudESAuthCookie` 换取新 Token，同时将服务端返回的新 Cookie 写回配置。日志追加到 `refresh_log.jsonl`。

### Cookie 续期机制

- Cookie 有效期 **36 小时**（`Set-Cookie` 返回 `expires=当前时间+36h`）
- Cookie **不会因换 Token 失效** — 服务端在接近过期时才会返回新 Cookie（约 24 小时后刷新才给新值）
- 只要**每 24 小时**运行一次 `refresh`，Cookie 就能持续续期
- 日志中 `cookie_changed=true` 表示 Cookie 已更新

### 首次获取 Cookie（浏览器）

如果 `icm_config.json` 中还没有 `cookie_string`，需手动从浏览器获取：

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
# 写入 icm_config.json: {"access_token": token, "cookie_string": "..."}
```

## OData API 端点速查

| 操作 | 方法 | URL | Body |
|------|------|-----|------|
| 创建工单 | POST | `/incidents` | `CreateIncident.to_dict()` |
| 查询工单 | GET | `/incidents({id})` | - |
| 查询列表 | GET | `/incidents` | - |
| Acknowledge | POST | `/incidents({id})/AcknowledgeIncident` | `{"AcknowledgementParameters":{"AcknowledgeContactAlias":null}}` |
| 当前值班人员 | POST | `oncallapi/.../GetCurrentOnCallForCurrentShiftForTeams` | `{"TeamIds":[37883]}` |

## Critical Rules

- **`ImpactedServices` 必须至少包含一个 ServiceId**，否则返回 400 验证失败
- **Token 有效期 3 小时**，过期后运行 `python icm_token_refresh.py refresh` 自动刷新
- **Cookie 有效期 36 小时**，接近过期时刷新才会返回新 Cookie，需每 24 小时至少刷新一次
- **Acknowledge 必须调 action** — 直接 PATCH `IsAcknowledged` 字段不生效
- **不要通过聊天传 Token** — JWT 3000+ 字符会被损坏

## 常见 OwningServiceId / OwningTeamId

| Service | Team | ServiceId | TeamId |
|---------|------|-----------|--------|
| Azure Incident Management China | PS | 20284 | 37883 |
| Azure Incident Management China | wasu-mooncake | 20284 | 22590 |
