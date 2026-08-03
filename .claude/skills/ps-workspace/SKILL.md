# PS Workspace

PS Team 统一 Web 工作平台，集成 EDM 监听、EDM 看板、TFS 工单、ICM 工单管理、统一设置等功能。

## 架构

- Flask Web 应用，运行在 **http://localhost:9000**
- SPA 前端，模板在 `templates/`，JS 在 `static/app.js`，CSS 在 `static/style.css`
- Blueprint 模块化：`routes/auth.py`, `routes/edm_eml.py`（当前活跃）, `routes/edm.py`（旧流程）, `routes/tfs.py`, `routes/icm.py`, `routes/task.py`, `routes/settings.py`

## 启动

```bash
cd PSWorkspace && python app.py
```

配置：`PSWorkspace/ps_workspace_config.json`（端口、认证等）
日志：`Log/ps_workspace.log`

## 持久化存储（SQLite）

数据库：`Log/ps_workspace_tasks.db`（WAL 模式），`app.py` 启动时自动初始化。

| 表 | 说明 |
|----|------|
| `tasks` | 异步任务记录（EDM Process、ICM Create），支持 `run_task()` generator 进度输出 |
| `edm_events` | EDM 监听检测事件（连接、新邮件、成功、错误），重启不丢失 |
| `icm_token_history` | ICM Token 刷新/验证历史记录（分页查询，含 Cookie 续期信息） |

- `utils/task_queue.processed_eml_files()` — 从 tasks 表查询每个 .eml 文件名**最新一次**的 `edm-process-*` 任务状态，仅当最新为 `completed` 才返回 `{filename: latest_completed_at}`
- `temp_files` API 返回 `processed` 和 `processed_at` 字段，`history` API 返回 SN 的 `processed` 字段
- 前端不再用 JS 变量记忆处理状态，从后端 API 获取

## 模块

| 模块 | 功能 |
|------|------|
| EDM 监听 | EWS Streaming 实时推送，自动检测 EDM 邮件并保存到 `EDM/Temp/` |
| EDM 看板 | 按 conversation_id 分组展示 EDM 处理进度（7 步流程），数据源来自 GitHub（bluemct/docs） |
| TFS | 内网 TFS 2010 Request 工单管理（查询、AI 分类、批量更新/Resolve） |
| ICM | Microsoft ICM 工单创建/查询/批量操作/值班人员查询 |

## TFS Request 2010 工单管理

**仅保留内网 TFS 2010 Request 操作**，Azure DevOps REST API（Webhook、Labor Time、WorkItem 查询/更新）已移除。

- **凭据来源**：`TfsRequestPS/TfsRequest.ps1` 使用当前 Windows 域账号凭据（NTLM/Kerberos 自动认证），无需手动配置
- **后端调用**：`routes/tfs.py` → `_run_tfs_ps()` → `subprocess` 调用 PowerShell 脚本，传入 `-ConfigPath` 指向 `ps_workspace_config.json`
- **配置**：`ps_workspace_config.json` 中的 `tfsrequest` 块（server_url, collection, assignee_group, default_assignee）

### AI 自动分类

- **Tier 1**：litellm + Qwen3.5-27B（支持批量分类，8000 char 分片）
- **Tier 2**：关键词回退（17 个分类：GFS-PKI, GFS-Monitoring, PS-EDM 等）
- **工作流**：`batch-classify`（AI 分析）→ 人工确认 → `batch-apply`（写回 TFS）
- **Assign To**：从 TSGLog 提取发件人邮箱，映射到 PS 团队成员

### 反馈学习系统（Feedback Learning）

AI 分类结果经人工审核后，自动记录到反馈库，下次分类时注入相似历史案例作为 few-shot 示例。

- **SQLite 表** `tfs_classify_feedback`：存储 AI 原始值 vs 人工修正值，`diff_flag=1` 表示有修正
- **自动反馈**：点击"确认并更新"时，每条工单（无论是否修改）自动提交反馈记录
- **Few-shot 注入**：AI 分类前，从反馈库检索 5 条最相似的历史案例（关键词重叠度匹配）注入 prompt
- **前端指示器**：分类结果表每行末尾显示反馈状态（✓ 确认 / ● 已修改），实时更新
- **反馈历史 Tab**：可查看、删除历史反馈，显示统计（总反馈 / 修正 / 确认）
- **API 路由**：
  - `POST /api/tfs/request/feedback` — 提交反馈
  - `GET /api/tfs/request/feedback` — 分页查询
  - `GET /api/tfs/request/feedback/stats` — 统计
  - `GET /api/tfs/request/feedback/similar` — 相似检索
  - `DELETE /api/tfs/request/feedback/<id>` — 删除

### API 路由

| 路由 | 说明 |
|------|------|
| `GET /api/tfs/request/tickets` | 查询 Open 工单 |
| `POST /api/tfs/request/classify` | AI 分类单条 |
| `POST /api/tfs/request/batch-classify` | AI 批量分类 |
| `POST /api/tfs/request/batch-apply` | 确认并批量更新 TFS |
| `POST /api/tfs/request/update` | 更新单个工单 |
| `POST /api/tfs/request/resolve` | Resolve 单条 |
| `POST /api/tfs/request/batch-resolve` | 批量 Resolve |
| `GET /api/tfs/request/get/<id>` | 获取单个工单详情 |

## EDM Agent 页面功能

- **监听规则**：发件人含 `ma.chuntao`，正文含 `"EDM Agent"`，且有附件（Streaming 实时推送）
- **检测事件**：10 秒自动刷新，启动后快速轮询 3 次（1 秒间隔）捕获连接事件
- **EDM/Temp/ 文件**：进入页面自动加载；检测到新邮件（success 事件）自动刷新；只显示 `.eml` 文件
- **已处理 SN**：手动刷新查看历史处理记录，`processed` 字段标记是否已成功处理

## EDM Process 处理流程

### 流程 A：原流程（依赖 Outlook COM）— `routes/edm.py`（已弃用）

⚠ 此流程已弃用，仅保留作为参考。切回方式：将 `app.py` 的 blueprint 注册从 `routes.edm_eml` 改回 `routes.edm`。

点击 Process 按钮，后台异步执行 3 步流程：

| Step | 操作 | 参考 |
|------|------|------|
| 1/3 | `.eml` → `.msg`（eml_to_msg.py，需要 Outlook COM CreateItem+SaveAs） | `PSWorkspace/routes/edm.py` `_process()` |
| 2/3 | 从 MSG HTMLBody 提取 xlsx 文件名（SharePoint URL）→ 本地精确匹配搜索 → 复制到 Temp/ | `PSWorkspace/routes/edm.py` `_discover_xlsx()` |
| 3/3 | 运行 edm_process.py（`--file` 参数指定 .msg，需要 Outlook COM OpenSharedItem 读 HTMLBody） | `.claude/skills/edm-process/edm_process.py` |

**xlsx 发现逻辑**（`_discover_xlsx`）：
- 从 MSG HTMLBody 提取 SharePoint URL 中的 `.xlsx` 文件名
- 读取 `xlsx_search_dir.json` 获取本地搜索目录
- **精确文件名匹配**（忽略大小写），找不到则返回 None（不做模糊匹配 fallback）
- 未提取到文件名时，才用 SN 号匹配文件夹作为兜底

### 流程 B：纯 Python 流程（无需 Outlook COM）— `routes/edm_eml.py`

直接处理 `.eml`，跳过 `.msg` 转换，**零 Outlook COM 依赖**。

| Step | 操作 | 参考 |
|------|------|------|
| 1/2 | 从 .eml 的 text/html 提取 xlsx 文件名（SharePoint URL）→ 本地搜索 → 复制到 Temp/ | `PSWorkspace/routes/edm_eml.py` `_discover_xlsx()` |
| 2/2 | 运行 edm_process_eml.py（纯 Python：从 .eml MIME 结构提取 EDM template HTML + Token 替换） | `.claude/skills/edm-process/edm_process_eml.py` |

**流程 B 核心逻辑**：
- 解析 .eml MIME 结构，找到 `message/rfc822` 中无 To/Cc 收件人的子邮件（EDM template）
- 从 EDM template 的 `text/html` 部分提取 HTML body
- Token 替换（`Tokenmapping.json`）、插入 Subject 行、清理 `_MailOriginal` 锚点
- 保存嵌套邮件为 `.eml` 参考文件
- 处理 xlsx → CSV → formal/test CSV

**何时使用流程 B**：新机器 Outlook COM 不可用时（如 McAfee 拦截、DCOM 权限不足等），将 `app.py` 的 blueprint 注册从 `routes.edm` 改为 `routes.edm_eml` 即可切换。

**产出文件**（两种流程一致）：
```
EDM/SN-xxxxx/
├── EDM_template.html           ← 含 Token 替换 + Subject 行
├── 嵌套邮件 (.msg 或 .eml)    ← 参考用
├── .xlsx                       ← 联系人列表
├── .csv                        ← xlsx 转换
├── formal_*.csv                ← 正式版（全部行）
└── test_*.csv                  ← 测试版（每测试邮箱一行）
```

### EDM 看板刷新机制

看板数据来自 GitHub 仓库 `bluemct/docs/master/edmmailanalyzer.json`，后端复用 `.claude/skills/edm-dashboard/edm_dashboard.py` 的 `do_refresh()` 函数。

**处理结果弹窗**：完成/失败后弹出模态对话框，展示 3 步状态（✓ 成功/⚠ 警告/✗ 失败）及详情。
- xlsx 未找到 → `ok="warn"`，显示 ⚠ 橙色警告图标
- 整体结果：全成功 → 绿色"处理完成"；有警告 → 橙色"部分完成"；失败 → 红色"处理失败"
- 弹窗关闭按钮修复：直接删除 overlay div，不再误删 document.body

## EDM Listener 注意事项

- 使用 **EWS Streaming**（非轮询），`ews_streaming.ps1` 在项目根目录
- Listener 是 Flask 后台线程，**关闭浏览器后仍在运行**
- 后台线程不依赖 Flask context，通过 `_set_project_root()` 在启动时缓存 PROJECT_ROOT

## ICM 工单管理

ICM 模块：**所有操作已转为纯 Python**（Token 验证、搜索、创建、单条操作、批量操作、值班查询、Token 刷新），**0 PowerShell 依赖**，速度快且支持中文。

ICM 配置已统一到 `IcMHelper/icm_config.json`，不再使用 `IcMHelperPS/` 目录。

### 纯 Python API 调用函数

| 函数 | 说明 |
|------|------|
| `_get_token()` | 读取 `IcMHelper/icm_config.json` 获取 access_token |
| `_icm_get(url)` | GET 请求 api2，返回 `(data, status)`，空 body 返回 `{}` |
| `_icm_post(url, body)` | POST 请求 api2，`ensure_ascii=False` + `charset=utf-8`，空 body 返回 `{}` |
| `_icm_patch(url, body)` | PATCH 请求 api2，空 body 返回 `{}` |
| `_icm_post_portal(url, body)` | POST Portal API（带 Origin/Referer 头），空 body 返回 `{}` |
| `_icm_patch_portal(url, body)` | PATCH Portal API（带 Origin/Referer 头），空 body 返回 `{}` |

### 共享操作 Helper（单条 + batch 共用）

| Helper | 说明 |
|--------|------|
| `_ack_incident(iid)` | Ack 确认单票 |
| `_update_description(iid, desc)` | 更新描述（PATCH api2） |
| `_mitigate_incidents(ids, message)` | 缓解（Portal API，支持多票） |
| `_set_rootcause(iid, cat, desc, title)` | 设置根因（PATCH Portal 头） |
| `_resolve_incidents(ids, message)` | 解决（Portal API，支持多票） |
| `_resolve_full(iid, message, rc_cat)` | 完整解决流程：Mitigate → RootCause → Resolve |

### Token 管理（自动 + 手动刷新）

**自动刷新**：`_start_auto_refresh()` 在 `app.py` 启动时调用，启动守护线程：
- 每 **15 分钟**检查 `IcMHelper/icm_config.json` 中 Token 的 JWT expiry
- 剩余时间 **< 1 小时**时自动调用 `_do_token_refresh()` 换新 Token
- 每 **15 分钟**检查 `cookie_expires`，剩余 **< 48 小时**时主动发起刷新，尝试从 `Set-Cookie` 获取新 Cookie
- 从 `IcMHelper/icm_config.json` 读取 CloudESAuthCookie → Portal SSO 换新 Token → 写入 `IcMHelper/icm_config.json`
- 日志记录：`ICM token auto-refresh: Token refreshed, expires in X min`

**手动刷新**：前端 ICM 页面「刷新 Token」按钮 → POST `/api/icm/token/refresh`：
- 复用 `_do_token_refresh()` 函数
- 刷新成功显示"已刷新 · 剩余 X 分钟"（绿色/橙色），失败显示红色错误

**Cookie 续期**：每次刷新检查响应 `Set-Cookie` 头：
- 提取 `CloudESAuthCookie=xxx` → 更新配置中 `cookie_string`
- 解析 `expires=Thu, 30-Jul-2026 23:20:35 GMT` → 存为 ISO 格式到 `cookie_expires`
- API 不总是返回新 Cookie（需服务端判定），未返回则保留旧值

### Token 历史（SQLite 持久化）

- **SQLite 表** `icm_token_history`（`Log/ps_workspace_tasks.db`），启动时自动创建（ALTER TABLE 兼容旧库）
- **字段**：action (refresh/verify), success, got_new_token, token_obtained_at, token_expires_at, remaining_min, cookie_updated, cookie_expires_at, error_message, detail (JSON: source), created_at
- **记录时机**：验证操作（`_save_verify_history`）、手动刷新、自动刷新（`_record_token_history`, source: manual/auto/auto-cookie）
- **分页 API**：`GET /api/icm/token/history?page=1&size=10` → `{ok, total, page, pages, size, data}`
- **前端**：ICM 卡片 "Token 历史" Tab，切换时自动加载，每页 10 条，分页控件（首页/上一页/下一页/尾页），验证/刷新后自动刷新当前页
- **读取函数**：`task_queue.list_icm_token_history(page, page_size)` — 支持 OFFSET 分页

### Token 验证

- **验证按钮**：GET `/api/icm/token/verify`，纯 Python JWT 解析 + API 调用（<1 秒）
- 显示剩余分钟数，绿色（>30min）或橙色警告（<30min）

### 后台线程安全

所有 ICM 函数不依赖 Flask `current_app`：
- `_PROJECT_ROOT` — 模块级全局变量，`app.py` 启动时调用 `_set_project_root()` 设置
- `_BASE_DIR` — import 时从 `__file__` 计算（PSWorkspace/ 目录）
- 后台线程（`task_queue.submit()`）可直接调用 `_get_token()`、`_icm_*` 等函数

### 搜索工单

- 后端强制过滤 `OwningTeamId eq 37883`
- 前端下拉框：状态（Active/Mitigated/Closed）、严重度（1-4）、已确认（是/否）、标题关键词、客户名称
- 条件自动用 `and` 组合

### 创建工单

- 纯 Python 构造 JSON 直接 POST `api2/incidentapi/incidents`，`Content-Type: application/json; charset=utf-8`
- 模板功能：选择 "Disable SAE Account" → 弹窗输入 Account 名称 → 自动填充 Title、Description、Severity(4)、Type(Customer Reported)
- **中文支持**：`json.dumps(ensure_ascii=False)` + `charset=utf-8` 发送 UTF-8

### 单条操作

| 操作 | 实现 | 友好错误处理 |
|------|------|------|
| Ack | `_ack_incident()` → `_icm_post` | 400 → "工单已被 Ack，无需重复操作" |
| 更新描述 | `_update_description()` → `_icm_patch` | — |
| Mitigate | `_mitigate_incidents()` → `_icm_post_portal` | 400 → "工单可能已被 Mitigate" |
| Resolve | `_resolve_full()` → 3 步纯 Python（后台任务） | — |

前端 `doIcmAction()` / `submitAction()` 显示逻辑：
- `data.ok === true` → 绿色"✓ 成功"
- `data.error` 存在 → 红色"失败: ..."
- 无以上 → 显示 `data.stderr / data.stdout`

### 批量操作

- 搜索结果的复选框选择 → 操作栏出现（选择 ≥1 条）
- 批量 Ack、更新描述、Mitigate、Resolve（纯 Python，复用上述 Helper）
- Resolve 三步流程独立 try/catch + 日志：Mitigate → RootCause（每票）→ Resolve
- RootCause PATCH 需用 `_icm_patch_portal`（带 Portal Origin/Referer 头）
- per-ID 错误结果：`{"id": xxx, "ok": false, "error": "..."}`，前端逐条展示

### 前端行为

| 操作 | 按钮状态 | 事件刷新 |
|------|----------|----------|
| 搜索工单 | 查询中 → 显示表格 + 批量操作栏 | — |
| 创建 ICM 工单 | 显示"创建中..." → 轮询任务状态 → 显示结果 | — |
| 批量操作 | 执行中 → 显示成功/失败数量 → 自动刷新搜索结果 | — |
| 单条操作 | 执行中 → 显示成功/失败 | — |

## 关键文件

| 文件 | 说明 |
|------|------|
| `PSWorkspace/utils/task_queue.py` | SQLite 任务队列（tasks + edm_events + icm_token_history + activity_log 表），`run_task()` 支持 generator 进度，`list_icm_token_history(page, size)` 分页查询，`save_activity(category, title, detail, status)` / `list_activities(max)` 跨模块活动日志 |
| `PSWorkspace/utils/script_runner.py` | PowerShell/Python 脚本运行器（ICM 模块已不再使用） |
| `PSWorkspace/routes/edm.py` | EDM 路由，`_process()` 编排 3 步流程，`_discover_xlsx()` xlsx 精确发现 |
| `PSWorkspace/routes/edm_eml.py` | EDM 路由（纯 Python 流程，当前使用） |
| `PSWorkspace/routes/tfs.py` | TFS 2010 Request 工单管理（AI 分类 + PowerShell 调用，无 Azure DevOps REST API） |
| `PSWorkspace/routes/icm.py` | ICM 路由，纯 Python `_icm_*` 辅助函数 + 共享 Helper + 自动 Token 刷新 + activity 日志 |
| `PSWorkspace/routes/settings.py` | 配置管理 API，读取/写入 EDM（`.edm_agent_config.json`、`xlsx_search_dir.json`）、ICM（`IcMHelper/icm_config.json`）、AI（`.edm_agent_llm_config.json`）配置，敏感字段脱敏 |
| `PSWorkspace/routes/task.py` | 异步任务 API，新增 `GET /api/task/activities` 跨模块活动查询 |
| `IcMHelper/icm_config.json` | ICM Token/Cookie 配置文件（唯一配置源） |

## 设置页面（Settings）

顶栏 ⚙️ 按钮 + 侧边栏「设置」入口，SPA 页面 `page-settings`，三个 Tab：

| Tab | 管理的 JSON 文件 | 字段 |
|-----|------------------|------|
| EDM 配置 | `.edm_agent_config.json` + `xlsx_search_dir.json` | EWS URL、域账号、密码、邮箱、文件夹名、监听规则（sender/subject/body keywords）、输出目录、XLSX 检索目录 |
| ICM Token & Cookie | `IcMHelper/icm_config.json` | Access Token（只读脱敏）、Cookie String、Cookie 过期时间 |
| AI Model | `.edm_agent_llm_config.json` | Model、API Base、API Key、Timeout |

- 密码/API Key 等敏感字段返回时脱敏（`_mask()`），写入时空值不覆盖原值
- 每次保存自动记录到 `activity_log` 表

## 活动日志（Activity Log）

`activity_log` SQLite 表，统一记录跨模块操作，首页"最近任务"展示。

| 字段 | 说明 |
|------|------|
| category | 模块标签：`edm`, `icm`, `tfs`, `settings`, `dashboard` |
| title | 活动标题，如 "EDM Process SN-55247" |
| detail | 可选详情 |
| status | `ok` / `warn` / `error` |
| created_at | UNIX 时间戳 |

**API**：`GET /api/task/activities?max=15` → `{activities: [...]}`
**写入**：`task_queue.save_activity(category, title, detail, status)`

**当前记录点**：EDM Process 完成、ICM Token 验证/刷新/创建工单、TFS 批量更新/Resolve、Dashboard 刷新、Settings 保存
