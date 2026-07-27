---
name: edm-dashboard-features
description: EDM 看板新增手动刷新按钮、git clone 拉取数据、本地保存功能
metadata:
  type: project
---

EDM 看板 edm_dashboard.py 已增加手动刷新功能：

- 页面顶部蓝色"手动刷新"按钮 + 状态展示栏
- 数据源优先 `git clone` 拉取 `bluemct/docs` (master) 的 `edmmailanalyzer.json`，回退 HTTP 直连 `raw.githubusercontent.com`，再回退 `ghproxy.com` 镜像
- 拉取成功后自动保存到本地 JSON 文件（`--json-file` 指定路径）
- 30 分钟后台自动刷新复用同一逻辑
- 分支名已改为 `master`（`main` 不可用）
