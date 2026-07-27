# HANDOVER — EDM Email Processor Project

## 已完成的工作

### 1. EDM Process Skill 创建
- 新建 `.claude/skills/edm-process/` 目录和脚本 `edm_process.py`（~356行）
- 功能: 处理 `.msg` 原始邮件文件，从主题提取 SN 编号，保存目标嵌套 `.msg` 附件，下载 HTML 正文中的 `.xlsx` 链接
- 更新了 `CLAUDE.md` 添加 skill 文档

### 2. 关键修改的文件

| 文件 | 修改内容 |
|------|---------|
| `.claude/skills/edm-process/edm_process.py` | 主脚本，包含完整的 .msg 处理逻辑 |
| `.claude/skills/edm-process/SKILL.md` | Skill 文档，说明用法和依赖 |
| `CLAUDE.md` | 添加 edm-process skill 条目 |

### 3. 已实现的功能（测试通过）

| 功能 | 状态 | 实现方式 |
|------|------|---------|
| SN 编号提取 | ✅ 完成 | 正则 `SN-\d+` 匹配邮件主题 |
| SN 文件夹创建 | ✅ 完成 | `EDM/SN-xxxxx/` 自动创建 |
| 目标附件识别 | ✅ 完成 | olefile 扫描 `__attach_version1.0_#0000000X` 前缀，检查 `__substg1.0_3701000D` 嵌套存储中的 `__recip_version` 条目数量 |
| 目标 .msg 保存 | ✅ 完成 | `extract-msg` 的 `att.data.exportBytes()` 写入原始字节，文件名清洗 Windows 非法字符 |
| xlsx URL 提取 | ✅ 完成 | 从 HTML 正文提取 href 链接和裸 URL，`html.unescape()` + `urllib.parse.unquote()` 解码 |
| 凭据加密存储 | ✅ 完成 | Fernet 对称加密，存于 `.edm_auth/` 目录 |
| 交互式凭据输入 | ✅ 完成 | `--auth` 命令行参数触发 |

### 4. 实际测试结果

- 原始邮件: `EDM/_EDM test and distribution_ Incident 811869714 _ SN-56195...msg`
- SN 提取: `SN-56195`
- 附件保存: `EDM/SN-56195/请在 2026 年 6 月 20 日前...msg`（52.5 KB）
- xlsx URL 提取: 找到 1 个下载链接

## 已做的架构或设计决策

### 为什么用 extract-msg + olefile 而不是 win32com
- win32com 依赖 Outlook 客户端，打开某些 `.msg` 文件会失败（`OpenSharedItem` 返回 COM 错误）
- extract-msg 是纯 Python 库，不依赖 Outlook，可以解析嵌套消息附件
- olefile 用来快速扫描 OLE2 结构确定哪个附件是目标（通过 3701000D 中收件人数量判断）

### 为什么用 Fernet 加密而不是其他
- 轻量级，不需要外部密钥管理服务
- 密钥和项目文件同机存储，简单实用
- 满足 "不需要每次都输入密码" 的需求

### 输出目录设计
- 默认输出到项目根目录 `EDM/`（通过 `os.path.dirname` 从脚本位置往上推4级）
- 每个 SN 创建独立子文件夹 `EDM/SN-xxxxx/`

### 目标附件识别逻辑
- 原始邮件包含两个嵌套 `.msg` 附件：审批邮件（有收件人）和 EDM 模板邮件（无收件人）
- 通过 olefile 扫描 OLE2 结构，检查 `__substg1.0_3701000D` 中是否有 `__recip_version` 条目
- 0 个收件人的那个就是 EDM 模板

### 4. Unimarketing API — 列表创建与联系人关联（2026-06-12）

**已完成**:
- ✅ 创建联系人：`POST /contact/` + `<feed>` 包裹 `<entry>`，201 成功
- ✅ 创建列表：`POST /list/` + `<entry>`（bare，非 feed），201 成功
- ✅ 创建列表支持自定义字段：`<um:attribute name="Token" label="Token" visible="true" public="true" sn="1" type="text"/>`

**API 端点速查**:

| 操作 | 端点 | 请求体格式 | 认证 |
|------|------|-----------|------|
| 创建/更新联系人 | `POST /contact/` | `<feed><entry><email>...` | BasicAuth + `Authorization: OAuth` |
| 创建列表 | `POST /list/` | `<entry><title>...</title>` | BasicAuth + `Authorization: OAuth` |
| 查询列表 | `GET /list/{id}/` | — | 同上 |
| 查询联系人 | `GET /contact/{id}/` 或 `GET /contact/?field=email&q=xxx` | — | 同上 |

**添加联系人到列表 — 服务器端 Bug（🔴 确认 21Vianet 环境 Bug）**:

**更新 (2026-06-12)**: 之前的 500 错误变为 201 但仍**忽略 `<link>` 元素**。OAuth HMAC-SHA1 签名（C# SDK 方式）现在可正常工作（不再 401）。

**API 行为**:

| href 格式 | BasicAuth | OAuth | 实际效果 |
|-----------|-----------|-------|---------|
| `{HOST}/list/{id}/` (带斜杠) | 201 | 201 | **忽略 link，只更新联系人** |
| `{HOST}/list/{id}` (不带斜杠) | 500 | 500 | **服务器内部异常** |

**已测试的 30+ 种方案全部失败** (完整列表在 `test_add_to_list_v2.py` 和 `test_add_to_list_v3.py`):
- `POST /contact/` + `<link rel="related" title="addContacts">` — 201 忽略
- `POST /contact/` + `<link rel="adds">`, `<link rel="isPartOf">` — 201 忽略
- `POST /contact/` + `<um:listName>`, `<um:list>`, `<um:addContacts>` — 201 忽略
- `POST /contact/?list={id}` — 201 忽略
- `POST /contact/` + `method=put` / `rel=list` query param — 201 忽略
- `POST /contact/` + JSON body — 400
- `POST /contact/` + relative href — 400
- `POST /contact/` + X-Rel header — 201 忽略
- `POST /contact/` + `<id>` + `<link>` — 201 忽略
- `POST /contact/` + `<source><link>>` — 201 忽略
- `POST /contactimport/` (3种变体) — 400
- `POST /list/{id}/` (2种变体) — 400
- `GET /list/{id}/contact/`, `GET /list/{id}/contacts/` — 404
- `POST /list/{id}/contact/` — 404
- `PUT /contact/{id}/` (3种变体) — 405
- OAuth HMAC-SHA1 签名 (C# SDK) — 500/201（同 BasicAuth）

**OAuth HMAC-SHA1 签名 (C# SDK 方式)**:
- 签名数据: `http://{API_KEY}?{排序的参数}` (含 Header: Authorization, Host, Content-Type)
- HMAC-SHA1(data, API_SECRET) → base64
- URL 参数逐字符 URL 编码（C# `HttpUtility.UrlEncode` 风格）
- 请求不使用 BasicAuth，只用 OAuth 查询参数 + `Authorization: OAuth` header

**待用户操作**:
- 通过 Unimarketing 网页手动添加联系人到列表（API 不可用）
- 联系 21Vianet Unimarketing 技术支持确认 `addContacts` 接口在 21Vianet 环境是否可用

**待完成的 TODO / 下一步目标**

### 1. Unimarketing 添加联系人到列表
- **已确认**: 30+ 种 API 方案全部失败，服务器静默忽略 `<link>` 元素
- OAuth HMAC-SHA1 签名（C# SDK 方式）已实现并正常工作（不再 401）
- 下一步: 通过 Unimarketing 网页手动添加，或使用 CSV 导入
- 联系 21Vianet Unimarketing 技术支持确认 `addContacts` 接口可用性

### 2. SharePoint 认证下载 xlsx（🔴 阻塞中）

**问题**: `microsoftapc.sharepoint.com` 域名属于世纪互联（21Vianet）中国云，但用户账号是国际版，导致 token 受众不匹配。

**已尝试的方案**:
- NTLM 认证（requests-ntlm）→ 401
- MSAL + SharePoint REST API（`microsoftapc.sharepoint.com/.default` scope）→ "Invalid audience Uri"
- MSAL + Graph API 国际版 → 400 "Resource not found for the segment 'microsoftapc.sharepoint.com'"
- MSAL + Graph API 中国版（`microsoftgraph.chinacloudapi.cn`）→ 国际 token 对中国 endpoint 无效
- OBO token 交换 → 需要 client_secret（公有应用不提供）
- Office365-REST-Python-Client → 安装了但未成功测试

**需要解决的问题**:
- 确认 `microsoftapc.sharepoint.com` 实际归属的云环境
- 确定正确的 MSAL authority + token scope + API endpoint 组合
- 可能需要用户提供: SharePoint 站点的国际版 URL、或者确认是否可以使用中国云认证

**需要修改的代码**:
- `edm_process.py` 的 `get_auth_session()` 和 `download_file()` 函数
- 当前使用 NTLM/Basic auth，需要改为 MSAL + Bearer token

### 3. 清理依赖（edm-process 相关）
- `requests-ntlm` 不再需要（SharePoint 不支持 NTLM）
- 需要 `msal`（已安装）
- 需要 `Office365-REST-Python-Client`（已安装但未确认能用）
- 更新 `SKILL.md` 中的依赖列表

### 3. 安装状态
- extract-msg v0.55.0 — 已安装（使用清华源）
- olefile — 已安装
- requests — 已安装
- cryptography — 已安装
- msal — 已安装
- Office365-REST-Python-Client — 已安装
- requests-ntlm — 已安装（可移除）
