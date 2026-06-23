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

## 看板功能

- 仅展示 subject 含 `[EDM test and distribution]` 的邮件对话
- 自动屏蔽包含 sender `21V-WAPHYNET@oe.21vianet.com` 的整个 conversation
- 顶部 3 个卡片可点击筛选：全部 / 进行中 / 已完成
- 每行一个 conversation，显示 SN 编号、进度条、状态标签
- 展开后可看 7 步流程：
  - Step 1: EDM Request
  - Step 2: Test Sent, Awaiting Approval
  - Step 3: Peer Reviewed, Awaiting Nanbo Approval
  - Step 4: Approved
  - Step 5: Result Notified to PS
  - Step 6: Formal EDM Sent
  - Step 7: Confirmed, Closed
- 原始 step > 7 的邮件合并到 step 7 显示

## 身份验证

- 打开看板即弹出登录框，使用 `bj-oe.21vianet.com` 域账号登录
- 后端通过 `win32security.LogonUser` 验证域账号密码（`LOGON32_LOGON_NETWORK`）
- 登录成功获得 1 小时有效期的 Bearer token
- 所有 API 请求（`/api/data`、`/api/refresh`）需携带 token
- 点击用户名可退出登录

## 手动刷新

页面顶部蓝色"手动刷新"按钮，点击后从 GitHub 拉取最新数据：

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

1. 复制 `edm_dashboard.py`、`edmmailanalyzer.json`、`run_dashboard.vbs` 到 `D:\EDM_Dashboard\`
2. 目标电脑安装 Python 3 + Git + `pip install pywin32`
3. VBS 脚本自动检测自身所在目录，不硬编码路径
4. 双击 `run_dashboard.vbs` 后台启动

## 文件

- `edm_dashboard.py` — Python HTTP 看板服务
- `run_dashboard.vbs` — 后台启动脚本（自动检测路径）
- `DEPLOY.md` — 部署文档
