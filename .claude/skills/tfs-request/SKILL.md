# TFS Request 2010 — TFS 工单智能管理

通过 PowerShell + TFS 2010 .NET 程序集访问内网 TFS Request 系统，支持 AI 分类、工单查询、更新、Resolve 和批量操作。

## 文件位置

| 文件 | 说明 |
|------|------|
| `TfsRequestPS/TfsRequest.ps1` | PowerShell TFS 2010 封装脚本 |
| `PSWorkspace/routes/tfs.py` | Flask 后端端点（`/api/tfs/request/*`） |
| `PSWorkspace/templates/index.html` | 前端 TFS Request 管理 Tab |
| `test_tfs_request.py` | 独立测试脚本（不依赖 Flask） |

## 配置

在 `PSWorkspace/ps_workspace_config.json` 中添加 `tfsrequest` 区块：

```json
{
  "tfsrequest": {
    "server_url": "http://tfs-request.21vbluecloud.com:8080/tfs",
    "collection": "DefaultCollection",
    "assignee_group": "PS",
    "default_assignee": "Michael Ma"
  }
}
```

AI 分类读取 `.edm_agent_llm_config.json`（litellm），不可用时自动降级为关键词匹配。

## 数据源说明

TFS 工单的 `System.Description` 字段为空，**分类数据来自 `Hisoft.21ViaNet.Description` 字段**（邮件往来 HTML）。
PowerShell query 已读取该字段并作为 `tsgLog` 返回，Python 后端做 HTML 剥离后送入 AI。

## 操作流程（Web UI）

三步走：**获取工单 → AI 分析 → 人工确认后更新**

```
┌─ 获取 Open 工单 ──→ 显示工单列表（ID, 标题, 状态, 指派人, Property, 更新时间）
│
├─ AI 智能分析 ──────→ 只分析 "Assigned To Implementer" 的工单
│                     返回每行工单的 AI 建议（黄色高亮）：
│                     ├─ 状态：当前状态，标注 ⚠ → In Process Implementer（需改状态）
│                     ├─ 建议指派人：AI 从邮件 From 提取，对照映射表
│                     ├─ Property：AI 分类（18 个类别）
│                     ├─ Solution：英文解决方案摘要
│                     └─ 工时：预估工时
│                     │
│                     "In Process Implementer" 等状态的工单显示为灰色（跳过，只读）
│                     │
│                     └─ 用户逐行修改 AI 分析结果
│                        │
│                        └─ 确认并更新 ──────→ 调用 /batch-apply，写入 TFS
│                                             只更新 AI 分析的工单，自动改状态
```

## AI 分类：Property（18 个类别）

| Property | 场景 |
|----------|------|
| GFS-Active Directory | AD Group、Domain Controller、OU管理、用户账户 |
| GFS-ADFS | AD FS、Claims、Claims Provider、联合认证 |
| GFS-PKI | PKI、证书、Certificate、Thumbprint、PKCS、CA |
| GFS-Monitoring | SCOM、监控、Monitoring、Alert、事件告警 |
| GFS-Definitive Software Library | DSL、软件分发、Software Library |
| GFS-Imaging | 系统镜像、OS Image、WDS、裸机部署 |
| GFS-WebProxy | Web 代理、反向代理 |
| PS-AAD | Azure AD、Entra ID、云身份、Conditional Access |
| PS-DSTS | DSTS 系统相关 |
| PS-EDM | EDM、邮件模板、Token替换、邮件分发 |
| PS-HYPERV | Hyper-V、虚拟化、VM 宿主 |
| PS-Nethop | Nethop 网络管理 |
| PS-PAW | PAW 平台、Privileged Access |
| PS-Other | 其他无法归类的 |
| PS-Secret Store | 凭据存储、Secret、Password Vault |
| PS-Server Security | 服务器安全、补丁安全、Vulnerability |
| PS-SNMPX | SNMP、SNMPX、网管协议 |

## AI 分类：Assign To 映射

AI 从 TSGLog 邮件的 From 字段提取发件人邮箱，对照映射表返回 Assign To 姓名：

| 邮箱 | Assign To |
|------|-----------|
| teng.jiangtao@oe.21vianet.com | Jerome Teng |
| su.hang3@oe.21vianet.com | Su Hang3 |
| qiao.jinxiu3@oe.21vianet.com | Jancy Qiao |
| ouyang.mengmeng@oe.21vianet.com | Romy Ouyang |
| ma.chuntao@oe.21vianet.com | Michael Ma |
| liu.wenya@oe.21vianet.com | Liu Wenya |

## PowerShell 脚本用法

```powershell
# Query open tickets (State != Closed, State != Canceled, Assignee Group = PS)
# 返回字段：id, title, state, assignedTo, description, property, tsgLog, workItemType, createdDate, changedDate
.\TfsRequest.ps1 -Action query

# Dump all fields of a work item (debug)
.\TfsRequest.ps1 -Action dump-fields -WorkItemIds 566426

# Update a single ticket
.\TfsRequest.ps1 -Action update -WorkItemIds 12345 -State 'In Process Implementer' -AssignedTo 'Michael Ma' -Property 'PS-EDM' -ActionField '1ST Update' -Solution 'Fix EDM issue' -WorkingHour 2

# Resolve a single ticket
.\TfsRequest.ps1 -Action resolve -WorkItemIds 12345

# Batch resolve
.\TfsRequest.ps1 -Action batch_resolve -WorkItemIds 12345,12346,12347
```

## Flask API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tfs/request/tickets` | GET | 获取 PS 队列 Open 工单（含 tsgLog、property） |
| `/api/tfs/request/batch-classify` | POST | 批量 AI 分类（只分析 Assigned To Implementer），**不写 TFS** |
| `/api/tfs/request/batch-apply` | POST | 逐工单写入 TFS（支持逐工单指派、自动改状态） |
| `/api/tfs/request/classify` | POST | AI 分类单个描述（body: `{"description": "..."}`） |
| `/api/tfs/request/update` | POST | 更新单个工单字段 |
| `/api/tfs/request/resolve` | POST | Resolve 单个工单 |
| `/api/tfs/request/batch-resolve` | POST | 批量 Resolve（body: `{"work_item_ids": [...]}`） |
| `/api/tfs/request/auto-process` | POST | **已废弃**，用 batch-classify + batch-apply 替代 |

### batch-classify 请求/响应

**请求（前端自动传递 tfsTickets 全量，含 tsgLog、property）：**
```json
{
  "tickets": [
    { "id": 123, "title": "...", "description": "", "property": "PS-EDM", "tsgLog": "<html>...</html>", ... }
  ]
}
```

**响应：**
```json
{
  "ok": true,
  "classifications": [
    {
      "id": 123,
      "title": "...",
      "state": "Assigned To Implementer",
      "assignedTo": "",
      "property": "PS-EDM",
      "solution": "Follow EDM guidance...",
      "workingHour": 1,
      "suggestedAssignedTo": "Liu Wenya",
      "needsStateChange": true,
      "skipped": false
    },
    {
      "id": 456,
      "state": "In Process Implementer",
      "property": "GFS-PKI",
      "skipped": true
    }
  ]
}
```

- `suggestedAssignedTo`：AI 从邮件 TSGLog 提取的发件人姓名
- `needsStateChange`：true 表示当前为 "Assigned To Implementer"，需改为 "In Process Implementer"
- `skipped`：true 表示该工单已被跳过（非 Assigned To Implementer 状态），保留原始值只读展示

### batch-apply 请求/响应

**请求（支持逐工单指派，只更新非 skipped 工单）：**
```json
{
  "classifications": [
    {
      "id": 123,
      "property": "PS-EDM",
      "solution": "...",
      "workingHour": 1,
      "assigned_to": "Liu Wenya",
      "state": "In Process Implementer"
    }
  ],
  "assigned_to": "Michael Ma",    // 默认值，per-ticket 为空时回退
  "action_field": "1ST Update"
}
```

**响应：**
```json
{
  "ok": true,
  "total": 3,
  "success": 3,
  "failed": 0,
  "results": [
    { "workItemId": 123, "ok": true, "property": "PS-EDM", "assignedTo": "Liu Wenya" }
  ]
}
```

## 独立测试（不依赖 Flask）

```bash
python test_tfs_request.py query
python test_tfs_request.py classify "EDM template token replacement failed"
python test_tfs_request.py update <工单号>
python test_tfs_request.py resolve <工单号>
python test_tfs_request.py batch_resolve <工单号1> <工单号2> ...
```

需要拷贝：`test_tfs_request.py`、`ps_workspace_config.json`、`.edm_agent_llm_config.json`、`TfsRequestPS/TfsRequest.ps1`

## 常见问题

- **`找不到驱动器` 错误** — PowerShell 脚本找不到配置文件，确保 `ps_workspace_config.json` 包含 `tfsrequest` 区块
- **AI 分类返回空** — Qwen reasoning model 把输出写到 `reasoning_content` 而非 `content`，代码已处理
- **`Subprocess error: 'NoneType' object has no attribute 'strip'`** — PowerShell 编码问题，已改为 bytes 模式 UTF-8/GBK 解码
- **工单 description 为空** — 正常现象，TFS Description 字段为空，分类数据来自 `Hisoft.21ViaNet.Description`
- **TSGLog 是 HTML** — 后端 `_strip_html()` 自动剥离标签，保留纯文本送入 AI
- **TSGLog 字段名** — TFS 字段名为 `Hisoft.21ViaNet.Description`（不是 TSGLog）
- **"In Process Implementer" 工单被跳过** — 预期行为，只分析 "Assigned To Implementer" 的工单

## 依赖

- TFS 2010 .NET 程序集（Team Explorer 2010 / VS 2010）
- PowerShell 5.1+
- `litellm`（可选，AI 分类用，不可用则降级关键词匹配）
