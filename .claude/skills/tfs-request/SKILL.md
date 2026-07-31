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

页面结构：3 个子页签（智能获取 & 处理 / 单个工单编辑 / 批量 Resolve）

### 智能获取 & 处理

```
┌─ 获取 Open 工单 ──→ 显示工单列表（ID 可点击跳转编辑）
│                     支持搜索过滤（ID/指派人/Property）
│                     支持按状态筛选
│                     支持列头排序（ID/状态/指派人/Property 正反序）
│
├─ AI 智能分析 ──────→ 只分析 "Assigned To Implementer" 的工单
│                     返回每行工单的 AI 建议（黄色高亮）：
│                     ├─ 建议指派人：AI 从邮件 From 提取，对照映射表
│                     ├─ Property：AI 分类（17 个类别 + PS-Other）
│                     ├─ Solution：英文解决方案摘要
│                     └─ 工时：预估工时
│                     │
│                     "In Process Implementer" 等状态 → 灰色跳过（只读）
│                     │
│                     └─ 用户逐行修改 → 确认并更新 → 写入 TFS
```

### 单个工单编辑

点击原始表格 ID 自动跳转：回填工单号、标题（只读）、状态、指派人、Property、Solution、工时。

### 批量 Resolve

自动带入已获取的工单 ID 到工单号列表，一键批量 Resolve。

## AI 分类：Property（17 + PS-Other）

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
# Query open tickets — 返回字段：id, title, state, assignedTo, description, property, solution, workingHour, tsgLog, ...
.\TfsRequest.ps1 -Action query

# Dump all fields of a work item (debug)
.\TfsRequest.ps1 -Action dump-fields -WorkItemIds 566426

# Update a single ticket
.\TfsRequest.ps1 -Action update -WorkItemIds 12345 -State 'In Process Implementer' -AssignedTo 'Michael Ma' -Property 'PS-EDM' -ActionField '1ST Update' -Solution 'Fix EDM issue' -WorkingHour 2

# Resolve / Batch resolve
.\TfsRequest.ps1 -Action resolve -WorkItemIds 12345
.\TfsRequest.ps1 -Action batch_resolve -WorkItemIds 12345,12346,12347
```

## Flask API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tfs/request/tickets` | GET | 获取 PS 队列 Open 工单（含 tsgLog、property、solution、workingHour） |
| `/api/tfs/request/batch-classify` | POST | 批量 AI 分类（只分析 Assigned To Implementer），**不写 TFS** |
| `/api/tfs/request/batch-apply` | POST | 逐工单写入 TFS（只更新非 skipped 工单） |
| `/api/tfs/request/classify` | POST | AI 分类单个描述 |
| `/api/tfs/request/update` | POST | 更新单个工单字段 |
| `/api/tfs/request/resolve` | POST | Resolve 单个工单 |
| `/api/tfs/request/batch-resolve` | POST | 批量 Resolve |

### batch-classify 响应关键字段

- `suggestedAssignedTo`：AI 提取的发件人姓名
- `needsStateChange`：true = "Assigned To Implementer"，需改状态
- `skipped`：true = 该工单跳过（非 Assigned To 状态），保留原始值只读展示

## PowerShell 5.1 兼容注意点

- `$WorkItemIds` 参数为 `[string]`（不是 `[int[]]`），由 `Convert-WorkItemIds` 函数内部 split 解析
- 函数返回值需用 `@()` 包裹，防止 PowerShell 5.1 "展开" 单元素数组为标量
- `_run_tfs_ps()` 传参格式：`-WorkItemIds 123,456,789`（逗号分隔字符串）

## 常见问题

- **TSGLog 字段名** — 实际字段名为 `Hisoft.21ViaNet.Description`（不是 TSGLog）
- **"In Process Implementer" 工单被跳过** — 预期行为，只分析 "Assigned To Implementer"
- **`.Count` 报错** — PowerShell 5.1 函数返回值展开导致，用 `@()` 包裹修复
- **AI prompt 全英文** — solution 输出英文

## 依赖

- TFS 2010 .NET 程序集（Team Explorer 2010 / VS 2010）
- PowerShell 5.1+
- `litellm`（可选，AI 分类用，不可用则降级关键词匹配）
