---
name: edm-dashboard
description: EDM 邮件状态看板 — 分析 EDM 文件夹邮件，按 conversation_id 分组展示处理进度
model: sonnet
---

# EDM 邮件状态看板

## 依赖

- Python 3 + `pywin32`（`pip install pywin32`）
- Git（从 GitHub 拉取数据）
- 无其他第三方 Python 依赖

## 使用流程

### 1. 准备 JSON 数据文件

将 `edmmailanalyzer.json` 放到 AgentProject 目录。该文件包含邮件数组，每条约：

```json
{
  "date": "2026-06-18 11:35:32",
  "subject": "[EDM test and distribution] Incident 818878381 ...",
  "sender": "lu.xinyu@oe.21vianet.com",
  "conversation_id": "AAQkA...",
  "conversation_step": 1,
  "conversation_total": 7
}
```

> 首次可直接用本地文件，看板启动后点击"Refresh" 按钮会从 GitHub 拉取最新数据。

### 2. 启动看板

```bash
python -X utf8 .claude/skills/edm-dashboard/edm_dashboard.py --port 8765 --json-file edmmailanalyzer.json
```

浏览器自动打开 `http://localhost:8765/`

> Windows 需要 `-X utf8` 以正确显示中文字符。

## 看板页面结构

页面采用 100vh flex 布局，顶部固定 header + 内容区按 **1:2:3** 比例分配高度：

### 顶部 Header（flex-shrink:0）— 固定不压缩

- 标题 + 用户信息（点击退出）+ Refresh 按钮
- 时间显示栏

### 第一部分（flex:1）— 概览卡片

- 3 个可点击卡片：全部 / 进行中 / 已完成
- 点击后跳转详情页（`/detail?filter=...`）
- 完成判定 = emails 数量 ≥ 7

### 第二部分（flex:2）— In Progress 列表

- 显示所有未完成的 EDM 对话
- 每行显示：SN 编号、邮件主题、7 段进度条、当前步骤
- 内容超出时自动出现垂直滚动条（`overflow-y:auto`）
- 每行样式：padding 10px，SN 字体 14px，主题 13px，进度条 6px 高度

### 第三部分（flex:3）— 底部双栏

- **左侧 Process Steps**: 带表头 `Step No. | Step Name | Description`，7 行步骤 `flex:1` 自动铺满面板高度
- **右侧 Monthly Closed by Week**: 柱状图，按 Step 7 日期统计每周关闭数量，图表高度 170px

### 响应式行为

- 窗口最大化 → 内容刚好铺满，无需滚动
- 窗口变小 → 各部分按比例缩小，In Progress 列表和步骤列表内部自动滚动

## 详情页（/detail）

- 完整列表：SN、Subject、Date、Status、Handler
- 支持 `?filter=all|progress|done` 筛选
- 客户端 CSV 导出按钮（`doExport`）

## 看板功能

- 仅展示 subject 含 `[EDM test and distribution]` 的邮件对话
- 屏蔽 2026-05-26 之前的测试对话
- 每行一个 conversation，显示 SN 编号、进度条、状态标签
- 原始 step > 7 的邮件合并到 step 7 显示

## 7 步流程定义

| Step | 名称 | 描述 |
|------|------|------|
| 1 | EDM Request | 初始 EDM 请求收到并记录 |
| 2 | Test Sent, Awaiting Approval | 测试邮件已发送，等待内部审批 |
| 3 | Peer Reviewed, Awaiting Nanbo Approval | Peer 审核完成，等待 Nanbo 审批 |
| 4 | Approved | 所有审批人批准 |
| 5 | Result Notified to PS | 审批结果通知 PS 团队 |
| 6 | Formal EDM Sent | 正式 EDM 邮件发送给客户 |
| 7 | Confirmed, Closed | 客户确认收到，工单关闭 |

## 身份验证

- 打开看板即弹出登录框，使用 `bj-oe.21vianet.com` 域账号登录
- 后端通过 `win32security.LogonUser` 验证域账号密码（`LOGON32_LOGON_NETWORK`）
- 登录成功获得 1 小时有效期的 Bearer token
- 所有 API 请求（`/api/data`、`/api/refresh`、`/api/export`）需携带 token
- 登录态保存在 localStorage，刷新页面自动恢复
- 点击用户名可退出登录

## 手动刷新

页面顶部"Refresh" 按钮，点击后从 GitHub 拉取最新数据：

1. 优先 SSH 方式 `git@github.com:bluemct/docs.git`（无弹窗，依赖 SSH key）
2. SSH 失败尝试 HTTPS 方式 `https://github.com/bluemct/docs.git`（`GIT_TERMINAL_PROMPT=0` 不弹窗）
3. 都失败则回退 HTTP 直连 `raw.githubusercontent.com`，再失败走 `ghproxy.com` 镜像
4. 全部失败则使用本地已有数据
5. 成功后自动保存到本地 JSON 文件（`--json-file` 指定路径）
6. 刷新状态栏分步显示：GitHub 拉取结果 → 本地保存结果 → 对话加载数量
7. 30 分钟后台自动刷新（同逻辑）

## 数据源

- GitHub 仓库：`bluemct/docs`（master 分支）
- 文件路径：`edmmailanalyzer.json`
- 本地备份：与 `--json-file` 参数路径相同

## 浏览器兼容

- 所有前端使用 `XMLHttpRequest` 而非 `fetch`，兼容 IE11
- 无 Promise/箭头函数/const/let 等现代语法
- CSS flexbox 布局，兼容主流浏览器

## 部署到其他电脑

### 方式一：直接复制文件（推荐）

1. 复制以下文件到目标机器（如 `D:\EDM_Dashboard\`）：
   - `edm_dashboard.py`（主程序，单文件即可运行）
   - `edmmailanalyzer.json`（本地数据备份，可选）
   - `run_dashboard.vbs`（后台启动脚本，可选）
2. 目标电脑安装 Python 3 + Git + `pip install pywin32`
3. VBS 脚本自动检测自身所在目录，不硬编码路径
4. 双击 `run_dashboard.vbs` 后台启动，或命令行运行：
   ```bash
   python -X utf8 edm_dashboard.py --port 8765 --json-file edmmailanalyzer.json
   ```

### 方式二：从 GitHub 克隆

```bash
git clone https://github.com/bluemct/NewsDashBoard_CC.git
cd NewsDashBoard_CC
python -X utf8 .claude/skills/edm-dashboard/edm_dashboard.py --port 8765 --json-file edmmailanalyzer.json
```

### 最小部署

仅需 `edm_dashboard.py` 一个文件。看板会自动从 GitHub 拉取数据。

## 文件

- `edm_dashboard.py` — Python HTTP 看板服务（纯单文件，内嵌 HTML/JS/CSS）
- `run_dashboard.vbs` — 后台启动脚本（自动检测路径）
- `DEPLOY.md` — 部署文档

---

## EDM 邮件分析脚本（数据源）

看板的数据由 `edm_mail_analyzer.ps1` 脚本从 Outlook EDM 文件夹提取并推送到 GitHub。

### 运行方式

```powershell
.\edm_mail_analyzer.ps1          # 增量模式（默认）
.\edm_mail_analyzer.ps1 -Full     # 全量模式
```

### 脚本流程（6 步）

| 步骤 | 操作 | 说明 |
|------|------|------|
| [0] | 获取现有 JSON | git clone SSH → HTTPS → HTTP 直连 → 代理 → 失败降级全量 |
| [1] | 查找 EDM 文件夹 | EWS FindFolders, DisplayName = "EDM" |
| [2] | 读取邮件 | 增量：`IsGreaterThan(lastDate)` 只读新邮件；全量：无过滤 |
| [3] | 提取字段 | EWS Bind：date, subject, sender, conversation_id |
| [4] | 合并 + 去重 + 排序 | 按 `date\|subject\|sender` 组合去重，按 date 升序排序 |
| [5] | 分配步骤编号 | 按 conversation_id 分组顺序编号，回填 conversation_total |
| [6] | 写 JSON + git push | 输出到 `C:\repos\repo\edmmailanalyzer.json`，自动 git add/commit/push |

### JSON 输出格式

```json
{
  "date": "2026-06-29 14:24:18",
  "subject": "[EDM test...] SN-12345",
  "sender": "xxx@oe.21vianet.com",
  "conversation_id": "AAQkA...",
  "conversation_step": 3,
  "conversation_total": 7
}
```

### 全量扫描触发条件

1. 显式指定 `-Full` 参数
2. 增量模式但无法获取现有数据（GitHub 全部失败）
3. 首次运行（GitHub 没有 JSON 文件）

### 依赖

- EWS DLL（路径：`C:\Users\ma.chuntao\Desktop\Services\ews\lib\40\Microsoft.Exchange.WebServices.dll`）
- Git
- 日志输出到 `C:\repos\repo\edmmailanalyzer.log`

### 性能

| 模式 | 耗时 |
|------|------|
| 增量（1 封新邮件） | ~12 秒 |
| 全量（445 封邮件） | ~60-120 秒 |

### 去重机制

按 `date + subject + sender` 组合键去重，解决同一秒多封邮件被重复读取的问题。新增邮件如果与现有记录组合键相同，会被跳过并计入 `duplicates dropped`。
