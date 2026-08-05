# ICM Cookie Browser Extractor

通过 Chrome DevTools Protocol (WebSocket) 自动启动 Edge 浏览器，从 ICM Portal 提取 `CloudESAuthCookie`。

## 用途

ICM Token 刷新依赖 `CloudESAuthCookie`，Cookie 过期后（通常 7 天），此工具可自动提取新 Cookie。

已集成到 PS Workspace — Cookie 过期时自动触发浏览器提取。

## 原理

1. 扫描已有 Edge 调试端口，无则启动新 Edge（临时 Profile）
2. 通过浏览器级 WebSocket 连接 CDP，创建新标签页打开 ICM Portal
3. 页面级 WebSocket 连接，启用 Page/Runtime/Network 域
4. 用户完成 AAD SSO + MFA 登录
5. 检测到 SSO 回调后自动跳转 ICM 主页（触发 CloudESAuthCookie 设置）
6. 提取 Cookie 并输出

## 用法

### 手动运行

```bash
cd AgentProject
python icm_cookie_extractor.py
```

### 提取模式（供 PS Workspace 调用）

```bash
python icm_cookie_extractor.py --extract result.json --config-dir IcMHelper
```

### 强制全新浏览器

```bash
python icm_cookie_extractor.py --extract result.json --config-dir IcMHelper --force-fresh
```

| 参数 | 说明 |
|------|------|
| `--extract RESULT_JSON` | 提取结果写入 JSON 文件（含 cookie_string, cookie_expires） |
| `--config-dir DIR` | 提取后直接更新 `DIR/icm_config.json` 中的 cookie |
| `--force-fresh` | 不复用已有 Edge，强制启动全新浏览器（清理旧 Profile 目录） |

## 运行流程

1. 脚本自动找空闲端口 → 启动 Edge（临时 Profile）
2. 通过 WebSocket CDP 创建标签页，打开 `portal.microsofticm.com/`
3. **首次运行**：手动完成 AAD SSO 登录 + MFA
4. **后续运行**：临时 Profile 无记忆，每次需重新登录
5. 检测到 SSO 回调后自动跳转 ICM 主页
6. 检测到 `CloudESAuthCookie` 后输出结果 → Edge 窗口保持打开

## 输出示例

```
============================================================
Cookie extraction successful!
============================================================

Cookie Name: CloudESAuthCookie
Cookie Value (first 50 chars): AAEAADHuzUCBq...
Cookie Length: 3842 chars
Expires: 2026-08-13 17:04:01 UTC
Expires (ISO): 2026-08-13T17:04:01+00:00
Remaining: 167.5 hours (10050 minutes)
============================================================

To update IcMHelper/icm_config.json, set:
  "cookie_string": "CloudESAuthCookie=AAEAADHuzUCBq..."
  "cookie_expires": "2026-08-13T17:04:01+00:00"
============================================================
```

## PS Workspace 集成

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/icm/token/browser-extract` | POST | 启动浏览器提取 Cookie → 刷新 Token |
| `/api/icm/token/refresh` | POST | 刷新 Token（Cookie 过期时自动触发浏览器提取） |

### 自动触发机制

`_do_token_refresh(auto_browser=True)` 在以下情况自动启动浏览器提取：

1. **Cookie 缺失** — `icm_config.json` 中无 `CloudESAuthCookie`
2. **Cookie 被服务器拒绝** — Token 刷新返回 HTTP 401/400

提取成功后自动重试 Token 刷新，无需人工干预。

### 过期 Cookie 自动重试

提取流程会验证 Cookie 过期时间：
1. **第 1 次**：尝试复用已有 Edge → 提取到 cookie → 验证过期时间
2. **Cookie 未过期** → 直接使用
3. **Cookie 已过期**（< 0.5h）→ 判定为旧 Edge 缓存，自动第 2 次调用 `--force-fresh`
4. **第 2 次**：清理旧 Profile 目录，启动全新 Edge → 用户完成登录 → 新 Cookie

### 自动刷新循环

后台守护线程每 15 分钟检查一次：
- Token 剩余 < 60 分钟 → 自动刷新
- Cookie 剩余 < 48 小时 → 尝试通过 API 续期
- Cookie 缺失 → 自动触发浏览器提取
- Cookie 剩余 < 2 小时 → 仍尝试 API 续期（不触发浏览器）

### Settings 页面自动刷新

- 进入"设置"页面 → 三个配置全部重新读取
- 切换 "EDM配置" / "ICM Token & Cookie" / "AI Model" tab → 对应配置重新读取
- API Key 默认脱敏显示，点击 👁 眼睛按钮切换明文

## 技术架构

| 组件 | 说明 |
|------|------|
| 端口发现 | 扫描 19880~19900，已有 Edge 直接复用（`--force-fresh` 跳过） |
| CDP 连接 | **纯 Python WebSocket**（零依赖，手写 RFC 6455 帧） |
| 目标管理 | `Target.createTarget` 创建标签页，`our_target_id` 锁定追踪 |
| 页面导航 | `Runtime.evaluate` 执行 `window.location.href` |
| Cookie 监测 | `Network.getAllCookies`（全局，跨所有域名） |
| SSO 检测 | URL 含 `/sso2/?identityProvider` 后自动跳转主页 |
| Profile 清理 | `--force-fresh` 删除旧临时 Profile，避免 lockfile 阻塞启动 |

## 注意事项

- 零依赖（纯 Python + urllib + socket，无需 Selenium/浏览器驱动/websocket 库）
- 临时 Profile 不影响现有 Edge 浏览器和标签页
- 已集成 PS Workspace，Cookie 过期时自动触发提取
- 提取结果自动写入 `IcMHelper/icm_config.json`
- 过期缓存 Cookie 自动检测并重试
