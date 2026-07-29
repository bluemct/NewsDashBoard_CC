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
- **EDM/Temp/ 文件**：进入页面自动加载；检测到新邮件（success 事件）自动刷新
- **已处理 SN**：手动刷新查看历史处理记录

## EDM Listener 注意事项

- 使用 **EWS Streaming**（非轮询），`ews_streaming.ps1` 在项目根目录
- Listener 是 Flask 后台线程，**关闭浏览器后仍在运行**
- 后台线程不依赖 Flask context，通过 `_set_project_root()` 在启动时缓存 PROJECT_ROOT

## 前端行为

| 操作 | 按钮状态 | 事件刷新 |
|------|----------|----------|
| 启动监听 | 点击立即变灰 → 成功后恢复可用 | 快速轮询 3 秒 + 10 秒定期刷新 |
| 停止监听 | 点击立即变灰 → 成功后恢复可用 | 立即刷新一次 |

## 开发修改

- 所有页面和静态文件都带了 `no-cache` 头，F5 刷新即可看到最新变化
- 修改 Python 代码需要重启 Flask 进程
- 修改 CSS/JS 只需刷新浏览器
