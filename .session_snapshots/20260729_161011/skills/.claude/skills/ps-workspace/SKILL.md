# PS Workspace

PS Team 统一 Web 工作平台，集成 EDM 监听、EDM 看板、TFS 工单、ICM 工单管理等功能。

## 架构

- Flask Web 应用，运行在 **http://localhost:9000**
- SPA 前端，模板在 `templates/`，JS 在 `static/app.js`，CSS 在 `static/style.css`
- Blueprint 模块化：`routes/auth.py`, `routes/edm.py`, `routes/tfs.py`, `routes/icm.py`, `routes/task.py`

## 启动

```bash
cd PSWorkspace && python app.py
```

配置：`PSWorkspace/ps_workspace_config.json`（端口、TFS PAT、认证等）
日志：`Log/ps_workspace.log`

## 持久化存储（SQLite）

数据库：`Log/ps_workspace_tasks.db`（WAL 模式），`app.py` 启动时自动初始化。

| 表 | 说明 |
|----|------|
| `tasks` | 异步任务记录（EDM Process、ICM Create/Resolve），支持 `run_task()` generator 进度输出 |
| `edm_events` | EDM 监听检测事件（连接、新邮件、成功、错误），重启不丢失 |

- `utils/task_queue.processed_eml_files()` — 从 tasks 表查询 `edm-process-*` 且 `status=completed` 的记录，返回 `{filename: completed_at}`
- `temp_files` API 返回 `processed` 和 `processed_at` 字段，`history` API 返回 SN 的 `processed` 字段
- 前端不再用 JS 变量记忆处理状态，从后端 API 获取

## 模块

| 模块 | 功能 |
|------|------|
| EDM 监听 | EWS Streaming 实时推送，自动检测 EDM 邮件并保存到 `EDM/Temp/` |
| EDM 看板 | 按 conversation_id 分组展示 EDM 处理进度（7 步流程） |
| TFS | Azure DevOps Webhook 日志、更新 Labor Time、查询工单 |
| ICM | Microsoft ICM 工单创建/查询/Ack/Mitigate/Resolve、值班人员查询 |

## EDM Agent 页面功能

- **监听规则**：发件人含 `ma.chuntao`，正文含 `"EDM Agent"`，且有附件（Streaming 实时推送）
- **检测事件**：10 秒自动刷新，启动后快速轮询 3 次（1 秒间隔）捕获连接事件
- **EDM/Temp/ 文件**：进入页面自动加载；检测到新邮件（success 事件）自动刷新；只显示 `.eml` 文件
- **已处理 SN**：手动刷新查看历史处理记录，`processed` 字段标记是否已成功处理

## EDM Process 处理流程

点击 Process 按钮，后台异步执行 3 步流程：

| Step | 操作 | 参考 |
|------|------|------|
| 1/3 | `.eml` → `.msg`（eml_to_msg.py） | `PSWorkspace/routes/edm.py` `_process()` |
| 2/3 | 从 MSG 正文提取 xlsx 文件名（SharePoint URL）→ 本地精确匹配搜索 → 复制到 Temp/ | `PSWorkspace/routes/edm.py` `_discover_xlsx()` |
| 3/3 | 运行 edm_process.py（`--file` 参数指定 .msg，处理 .msg + .xlsx → SN 文件夹） | `.claude/skills/edm-process/edm_process.py` |

**xlsx 发现逻辑**（`_discover_xlsx`）：
- 从 MSG HTMLBody 提取 SharePoint URL 中的 `.xlsx` 文件名
- 读取 `xlsx_search_dir.json` 获取本地搜索目录
- **精确文件名匹配**（忽略大小写），找不到则返回 None（不做模糊匹配 fallback）
- 未提取到文件名时，才用 SN 号匹配文件夹作为兜底

**处理结果弹窗**：完成/失败后弹出模态对话框，展示 3 步状态（✓ 成功/⚠ 警告/✗ 失败）及详情。
- xlsx 未找到 → `ok="warn"`，显示 ⚠ 橙色警告图标
- 整体结果：全成功 → 绿色"处理完成"；有警告 → 橙色"部分完成"；失败 → 红色"处理失败"
- 弹窗关闭按钮修复：直接删除 overlay div，不再误删 document.body

## EDM Listener 注意事项

- 使用 **EWS Streaming**（非轮询），`ews_streaming.ps1` 在项目根目录
- Listener 是 Flask 后台线程，**关闭浏览器后仍在运行**
- 后台线程不依赖 Flask context，通过 `_set_project_root()` 在启动时缓存 PROJECT_ROOT

## ICM 工单管理

ICM 模块通过 dot-source `IcMHelperPS/IcmApi.ps1` 调用 PowerShell 函数。

### ICM 配置

- Token/Cookie 存储：`IcMHelperPS/icm_config.json`（PS Workspace 使用）
- 原始 Token/Cookie 存储：`IcMHelper/icm_config.json`（手动更新源）
- Token 刷新：`IcMHelper/icm_token_refresh.py`（Python，在 IcMHelper 目录运行）或 `IcMHelperPS/IcmTokenRefresh.ps1`（PowerShell）
- **Token 过期后**：从浏览器 ICM Portal 获取新 Cookie，更新 `IcMHelper/icm_config.json`，运行刷新脚本

### Token 验证

- 前端按钮：点击后立即显示 `⏳ 验证中...`，结果内联显示 `有效 ✓` 或 `无效: 401`
- 后端：`token_verify()` 解析 PowerShell 返回值（`Test-IcmToken` 返回 True/False），检查 stdout 为 `"true"` 且 stderr 不包含 `"401"`
- **注意**：PowerShell 即使命令报错也返回 exit code 0，不能只看 returncode

### 创建工单

- 两步流程：`New-IcmIncident`（构造 PS 对象）→ `New-IcmIncidentApi`（发送 HTTP POST）
- 使用 PowerShell 原生 hashtable 语法（`@{ ServiceId = 20284 }`），**不是 JSON 字符串**
- `-Type` 参数正确传递前端选择的值（`LiveSite` 或 `customerreported`）

### PowerShell 参数传递注意事项

- `utils/script_runner.py` 的 `run_powershell_function()` 使用 `f-string` 拼接命令（已修复 `.format()` 问题）
- 参数中的 JSON 花括号 `{}` 曾被 `.format()` 当作占位符解析导致 `KeyError`
- ICM 函数参数名使用 `-IncidentId`（不是 `-Id`）

## 前端行为

| 操作 | 按钮状态 | 事件刷新 |
|------|----------|----------|
| 启动监听 | 点击立即变灰 → 成功后恢复可用 | 快速轮询 3 秒 + 10 秒定期刷新 |
| 停止监听 | 点击立即变灰 → 成功后恢复可用 | 立即刷新一次 |
| Process 处理 | 处理中 → 灰色「✓ 已完成」/ 红色「✗ 失败」 | 弹窗展示结果 |
| 创建 ICM 工单 | 显示"创建中..." → 轮询任务状态 → 显示日志（stdout + stderr） | — |

### 任务日志显示

- `startTask()`：completed 状态下也显示 stderr（标记为 `[Stderr]`），failed 状态标记为 `[Error]`
- PowerShell 命令即使报错也返回 rc=0，所以 completed 状态的 stderr 也需要展示

## 关键文件

| 文件 | 说明 |
|------|------|
| `PSWorkspace/utils/task_queue.py` | SQLite 任务队列（tasks + edm_events 表），`run_task()` 支持 generator 进度 |
| `PSWorkspace/utils/script_runner.py` | PowerShell/Python 脚本运行器，`run_powershell_function()` dot-source 调用函数 |
| `PSWorkspace/routes/edm.py` | EDM 路由，`_process()` 编排 3 步流程，`_discover_xlsx()` xlsx 精确发现 |
| `PSWorkspace/routes/icm.py` | ICM 路由，创建/查询/操作工单，inline PowerShell 命令构建 |
| `PSWorkspace/static/app.js` | 前端公用 JS，`startTask()` 任务轮询，`pollTask()` 异步轮询 |
| `PSWorkspace/templates/index.html` | 前端模板，`processTempFile()` 处理函数，`showProcessResultDialog()` 结果弹窗 |
| `IcMHelperPS/IcmApi.ps1` | ICM API PowerShell 封装，`New-IcmIncident` → `New-IcmIncidentApi` 两步创建 |
| `IcMHelper/icm_config.json` | ICM Token/Cookie 配置文件（手动更新源） |
| `IcMHelperPS/icm_config.json` | PS Workspace 使用的 ICM 配置（从 IcMHelper 同步） |

## 开发修改

- 所有页面和静态文件都带了 `no-cache` 头，F5 刷新即可看到最新变化
- 修改 Python 代码需要重启 Flask 进程
- 修改 CSS/JS 只需刷新浏览器
