---
name: icm-cookie-browser-extractor
description: icm_cookie_extractor.py 通过 WebSocket CDP 提取 ICM CloudESAuthCookie，已集成 PS Workspace 自动触发
metadata:
  type: project
---

# ICM Cookie Browser Extractor

脚本路径: `icm_cookie_extractor.py`（AgentProject 根目录）

## 技术架构

- **纯 Python WebSocket CDP**（零依赖，手写 RFC 6455 帧）
- 端口复用：扫描 19880~19900，已有 Edge 直接复用（`--force-fresh` 跳过）
- `Target.createTarget` 创建标签页，`our_target_id` 锁定追踪
- `Runtime.evaluate` 执行 `window.location.href` 导航
- `Network.getAllCookies` 监测 Cookie（全局，跨所有域名）
- SSO 回调检测：URL 含 `/sso2/?identityProvider` 后自动跳转 ICM 主页触发 Cookie 设置
- Profile 清理：`--force-fresh` 删除旧临时 Profile 目录，避免 lockfile 阻塞启动

## 参数

- `python icm_cookie_extractor.py` — 手动模式，输出到控制台
- `--extract result.json` — 提取模式，结果写入 JSON 文件
- `--config-dir DIR` — 提取后直接更新 `DIR/icm_config.json`
- `--force-fresh` — 不复用已有 Edge，强制启动全新浏览器

## PS Workspace 集成（[[skill-ps-workspace]]）

`PSWorkspace/routes/icm.py` 集成：

- `_browser_extract_cookie(force_fresh)` — 子进程调用提取器，cookie 过期验证 + 自动重试
- `_is_cookie_expired_or_missing()` — 检查 cookie 是否缺失
- `_do_token_refresh(auto_browser=True)` — Cookie 缺失或服务器拒绝时自动触发浏览器提取
- `POST /api/icm/token/browser-extract` — 手动触发端点（提取 Cookie → 刷新 Token）
- `_icm_auto_refresh_loop()` — 后台守护线程，每 15 分钟检查 Token/Cookie 状态

### 过期 Cookie 自动重试流程

1. 第 1 次调用：复用已有 Edge → 提取 cookie → 验证过期时间
2. 未过期 → 直接使用
3. 已过期（< 0.5h）→ 自动第 2 次调用 `--force-fresh` → 清理旧 Profile → 全新 Edge

### Settings 页面改进

- 进入设置页面 / 切换 tab → 自动重新读取配置（无缓存）
- API Key 脱敏显示 + 👁 眼睛按钮切换明文

## 相关

- [[icm-api-python]] — ICM API Python 集成
- [[icm-token-history-feature]] — Token 刷新历史记录
