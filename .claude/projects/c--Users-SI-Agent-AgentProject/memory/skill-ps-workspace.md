---
name: skill-ps-workspace
description: PS Workspace Flask Web 平台，EDM 监听、看板、TFS、ICM、会议室预定、List 导入验证
metadata:
  type: project
---

PS Workspace Flask Web 应用，统一工作平台。

- 入口: `PSWorkspace/app.py`，运行在 http://localhost:9000
- 配置: `PSWorkspace/ps_workspace_config.json`
- EDM Listener 使用 EWS Streaming（非轮询），后台独立运行
- SQLite: `Log/ps_workspace_tasks.db`（tasks, edm_events, icm_token_history, activity_log, tfs_classify_feedback, meeting_rooms, recurring_plans, booking_history, ai_suggestions, edm_list_history）

**模块蓝图 (routes/):**
- `auth.py` — Windows 登录，Bearer token
- `edm_eml.py` — EDM 监听 + 邮件处理（EML 模式）
- `edm_list.py` — List 导入 + 验证（见下）
- `tfs.py` — TFS 工单 (PS 模式)
- `icm.py` — ICM 工单 + Token 自动刷新
- `task.py` — 异步任务 + 活动日志
- `settings.py` — EDM/ICM/AI 配置读写（含测试邮箱管理）
- `calendar.py` — 会议室预定模块

**List 导入验证模块 (routes/edm_list.py):**
- 前端: EDM 页面 3 个 Tab（监听/邮件处理/List导入验证），List Tab 含 3 个子 Tab（导入/验证/历史）
- 验证 Tab 通过单选按钮切换 Email 验证和深度验证模式，共用一套输入框和日志面板
- xlsx 自动发现: 按 SN 在 `EDM/Temp/` 找 .eml，从 EML 正文提取 xlsx 文件名，在 `xlsx_search_dir` 精确匹配；回退到 SN 文件夹模糊搜索
- xlsx 浏览: 服务端弹窗，以目录树结构展示 `xlsx_search_dir` 下的 xlsx 文件，点 ✓ 选择填入真实路径
- 导入: 支持 Test（测试邮箱）/ Formal（全部邮箱）模式，后台异步任务，测试邮箱从 `.edm_agent_config.json` 的 `test_emails` 字段读取
- Email 验证: 按 xlsx 每个 email 并行查 Unimarketing API 确认存在
- 深度验证: 逐字段比对 xlsx 与 API 返回的 Token/SubId 等属性
- 验证结果弹窗: 完成后弹出模态窗口，展示验证摘要统计和详细对比表，后端输出 `__RESULT__{JSON}` 结构化结果
- 历史记录: 按任务类型分列展示（导入/Email 验证/深度验证），支持 Tab 筛选
- 进度显示: 黑底绿字控制台风格（EDM Dashboard debug-log 风格），时间戳前缀，逐行追加，自动滚动，`requestAnimationFrame` 确保可靠滚动
- 日志彩色高亮: `===` 分隔线蓝色、`Test emails:` 金色加粗、`SN:`/`List:` 紫色、SUCCESS 绿色、FAILED 红色
- 复用模块: `verify_list_contacts.py`、`deep_verify_list.py`、`unimarketing_test_list.py`（均在项目根目录，通过 importlib 加载）
- API: `/api/edm/list/import`, `/api/edm/list/discover`, `/api/edm/list/info`, `/api/edm/list/xlsx-discover`, `/api/edm/list/xlsx-browse`, `/api/edm/list/verify-email`, `/api/edm/list/verify-deep`, `/api/edm/list/history`
- 路径格式: 所有路径统一使用正斜杠 `/`（`os.sep.replace` 归一化）
- 后台线程通过 `_set_project_root()` 缓存 project_root，不依赖 Flask app context

**设置页 (Settings → EDM Tab):**
- 监听规则: 发件人、主题关键词、正文关键词
- 测试邮箱: 独立配置项，逗号分隔，保存至 `.edm_agent_config.json` 的 `test_emails` 字段
- 路径配置: EDM 输出基础目录、XLSX 检索目录

**修改代码需重启 Flask；修改 CSS/JS 刷新浏览器即可（no-cache 头已开启）**
