# ICM Python 开发 TODO

## Phase 1: Token 自动刷新机制

| # | 任务 | 说明 |
|---|------|------|
| 1 | **Token 自动刷新** | Token 3小时过期，需检测并自动用 Cookie 换新的。DLL 里用 `CheckToken()` + `Token()` 实现 |
| 2 | **Cookie 持久化** | 每次换 Token 后服务端返回新的 `CloudESAuthCookie`，要捕获并保存到 `icm_config.json` |
| 3 | **封装 icm_api.py** | 把认证、读取、创建封装成一个统一模块，类似 IcmDll.dll 的结构 |

## Phase 2: 写操作 API（按优先级）

| # | API | DLL 方法 | 说明 |
|---|-----|----------|------|
| 4 | **Ack Incident** | `Post.AckIncident(id, True)` | 确认工单 |
| 5 | **Discussion 添加** | `Post.AddDiscussion(id, desc, True)` | 添加讨论/更新信息 |
| 6 | **Mitigate + Resolve** | `Post.MitigateAndResolved(id, message)` | 解决并关闭工单 |
| 7 | **Change CustomField** | `Post.ChangeCustomField(obj)` | 修改自定义字段 |
| 8 | **Change ImpactStartTime** | `Post.ChangeImpactStartTime(id, time)` | 更新影响开始时间 |
| 9 | **Link Incidents** | `Post.Link(id, linkId, type, desc)` | 关联两个工单 |
| 10 | **Change IncidentType** | `Post.ChangeIncidentType(id, type)` | 修改工单类型 |
| 11 | **Update ImpactedService** | `Post.ImpactedService(id, svcId, teamId)` | 更新影响的服务/团队 |

## Phase 3: 通知 & 协作 API

| # | API | DLL 方法 | 说明 |
|---|-----|----------|------|
| 12 | **Tracking Team** | `Post.TrackingTeams(id, team)` | 添加跟踪团队 |
| 13 | **RequestAssistance** | `Post.RequestAssistance(id, teamId, reason, ...)` | 请求协助 |
| 14 | **Track** | `Post.Track(id, teamId)` | 跟踪工单 |
| 15 | **Transfer WATS** | `Transfer.TransferWATS(id, message)` | 转交 WATS 团队 |

## Phase 4: Bridge 管理（高级功能）

| # | API | DLL 方法 | 说明 |
|---|-----|----------|------|
| 16 | **Create Bridge** | `Post.CreateNewBridge(id, data)` | 创建 Bridge 会议 |
| 17 | **Link to Bridge** | `Post.LinkToExistingBridge(id, data)` | 关联已有 Bridge |
| 18 | **Delete Bridge** | `Post.DeleteBridge(id, bridgeIds)` | 删除 Bridge |

## 关键设计

- **Token 刷新**: 检查 JWT `exp` 字段，`exp - now < 15min` 自动用 Cookie 换新
- **Cookie 持久化**: 每次换 Token 后捕获 `Set-Cookie` 中的新 `CloudESAuthCookie` 保存到 `icm_config.json`
- **模块结构**: `icm_api.py` 主模块 + `icm_create_incident.py` 数据类 + `icm_config.json` 配置
