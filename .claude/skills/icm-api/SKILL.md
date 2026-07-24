# ICM API Skill (Microsoft ICM — /api2/)

Create incidents via Microsoft ICM REST API using a pre-obtained Bearer token. Pure Python `requests`, no DLL dependency.

## Files

All files live in `IcMHelper/`:

| File | Purpose |
|------|---------|
| `icm_api.py` | `IcmClient` 统一 API 封装 — 自动 Token 刷新、读取、创建、更新 |
| `icm_create_incident.py` | `CreateIncident` 数据类定义，序列化 JSON（不含 API 调用逻辑） |
| `icm_create_test.py` | 测试脚本 — 读取 config，构造工单，POST 到 ICM API |
| `icm_token_refresh.py` | Token 刷新工具 — 用 Cookie 换新的 access_token，验证 Token 有效性 |
| `icm_config.json` | 存储 `access_token` + `cookie_string`（已在 .gitignore） |

## Architecture

```
浏览器登录 ICM → 复制 Cookie → POST /sso2/token (grant_type=cookie)
    → 返回 access_token (3小时有效)
    → 写入 icm_config.json
    → Python 读取 token → Bearer 认证调用 /api2/ API
```

**Python 端只需要：**
1. 从 `icm_config.json` 读取 `access_token`
2. 构造 `CreateIncident` 对象并序列化 JSON
3. POST 到 `https://prod.microsofticm.com/api2/incidentapi/incidents`

**唯一依赖：** `requests`

## Quick Start

### Option A: IcmClient (推荐 — 自动 Token 刷新)

```python
import sys
sys.path.insert(0, "IcMHelper")
from icmhelper import IcmClient, CreateIncident

client = IcmClient()

# 读取工单
incidents = client.get_incidents(top=10)
inc = client.get_incident(838833853)

# 创建工单
new = CreateIncident()
new.Title = "工单标题"
new.Description = "详细描述"
new.Summary = "摘要"
new.ImpactedServices = [{"ServiceId": 20284}]  # 必须指定
client.create_incident(new)

# 确认 / 添加讨论 / 关闭
client.ack_incident(inc_id)
client.add_discussion(inc_id, "update message")
client.mitigate_and_resolve(inc_id, "resolved")
```

### Option B: 直接 requests（无需 import IcMHelper）

```python
import json
import requests
from icm_create_incident import CreateIncident

# 1. 读取 Token
config = json.load(open("icm_config.json", encoding="utf-8"))
TOKEN = config["access_token"]

# 2. 构造工单
inc = CreateIncident()
inc.Title = "工单标题"
inc.Description = "详细描述"
inc.ImpactedServices = [{"ServiceId": 20284}]

# 3. 发送请求
resp = requests.post(
    "https://prod.microsofticm.com/api2/incidentapi/incidents",
    json=inc.to_dict(),
    headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
)
```

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

### 刷新 Token

用已有的 Cookie 自动换取新 Token（**推荐**）：

```bash
cd IcMHelper
python icm_token_refresh.py refresh     # 刷新 Token
python icm_token_refresh.py verify      # 验证 Token 是否有效
```

脚本会从 `icm_config.json` 读取 `cookie_string`，自动提取 `CloudESAuthCookie` 换取新 Token。

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

## Critical Rules

- **`ImpactedServices` 必须至少包含一个 ServiceId**，否则返回 400 验证失败
- **Token 有效期 3 小时**，过期后运行 `python icm_token_refresh.py refresh` 自动刷新
- **Cookie 不会因换 Token 失效** — 每次换 Token 服务端返回新 Cookie（有效期 1 天），刷新脚本自动更新
- **不要通过聊天传 Token** — JWT 3000+ 字符会被损坏

## 常见 OwningServiceId / OwningTeamId

| Service | Team | ServiceId | TeamId |
|---------|------|-----------|--------|
| Azure Incident Management China | PS | 20284 | 37883 |
| Azure Incident Management China | wasu-mooncake | 20284 | 22590 |
