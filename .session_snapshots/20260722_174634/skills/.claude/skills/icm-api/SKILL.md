# ICM API Skill

Connect to Microsoft ICM (Incident Command Center) API and read/create incidents.

## Overview

ICM API 使用 Token + Cookie 双认证。认证流程：

```
登录 ICM 浏览器 → 获取 Cookie → POST /sso2/token → 返回 access_token (3小时有效) → 调用 /api2/ API
```

## 关键信息

| 配置 | 值 |
|------|------|
| API 域名 | `https://prod.microsofticm.com` |
| Token 端点 | `https://portal.microsofticm.com/sso2/token` |
| Token 有效期 | **3 小时** |
| Cookie 有效期 | **一次性**（换 Token 后立即被服务端更新） |
| 认证方式 | `Authorization: Bearer {token}` |
| 返回格式 | OData JSON，数据在 `value` 数组中 |

## How To Use

1. **获取 Cookie** — 从 Edge 浏览器登录 ICM 后，F12 → Network → 任意请求 → 右键 Copy as cURL
2. **更新配置** — 把新鲜 Cookie 更新到 `icm_config.json` 的 `cookie_string` 字段
3. **换 Token** — 运行 `python test_icm_quick_fetch.py` 自动从 Cookie 换取 Token（需新鲜 Cookie）
4. **调用 API** — Token 有效期 3 小时，期间只用 Token 即可，不需要 Cookie

### 读取工单

```python
import requests

headers = {"Authorization": "Bearer {token}"}

# 搜索 Incident
requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?top=10", headers=headers)

# 按 Id 查找
requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?filter=Id eq 838833853", headers=headers)

# 按条件搜索
requests.get("https://prod.microsofticm.com/api2/incidentapi/incidents?filter=State eq 'ACTIVE' and Severity eq 2", headers=headers)
```

### 创建工单

```python
payload = {
    "Title": "工单标题",
    "Description": "工单描述",
    "Summary": "摘要",
    "Severity": 2,        # 1-4, 1 最严重
    "Type": "LiveSite",
    "OwningServiceId": 20284,
    "OwningTeamId": 22590,
}
requests.post("https://prod.microsofticm.com/api2/incidentapi/incidents", json=payload, headers=headers)
```

## 常见 OwningServiceId / OwningTeamId

| Service | Team | ServiceId | TeamId |
|---------|------|-----------|--------|
| Azure Incident Management China | PS | 20284 | 37883 |
| Azure Incident Management China | wasu-mooncake | 20284 | 22590 |

## 注意事项

- Token 过期后需要用 Cookie 重新换，但 Cookie 是一次性的，换过就不能再用
- 如果 Cookie 已过期，需要重新从浏览器登录 ICM 获取新的 Cookie
- 聊天窗口传 Token 会损坏（太长），用浏览器 Console 直接请求 `/sso2/token` 获取 Token
- Cookie 中关键的是 `CloudESAuthCookie`
