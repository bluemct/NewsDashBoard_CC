---
name: unimarketing-api-contact-create
description: Unimarketing API POST /contact/ 联系人创建/更新的调用方式、字段限制、查询限制、添加联系人到列表
metadata:
  node_type: memory
  type: reference
  originSessionId: 0242ff25-709e-4bba-bfd9-e2495b5ce4e6
---

## Unimarketing API 联系人创建

### 正确调用方式

- **Endpoint**: `POST http://services.unimarketing.com.cn/contact/`
- **Query params**: `apikey=customersupport&method=post&alt=atom`
- **Content-Type**: `application/atom+xml; charset=utf-8`
- **Auth**: `BasicAuth(API_KEY, API_SECRET)` + Header `Authorization: OAuth`
- **Body**: Atom **Feed** 包裹 Entry（不是裸 Entry），包含 `<email>` 和 `<um:attribute name="FieldName">Value</um:attribute>`
- **响应**: 201 Created, `<feed xmlns="http://www.w3.org/2005/Atom"></feed>`（空 feed 表示成功）

### 关键限制

1. **不能带 `<um:attribute name="Name">`** — Name 是系统保留字段
2. **Attribute name 必须匹配列表模板已定义字段** — 如 `Token`, `TokenT`, `TokenH` 等
3. **Attribute name 只能纯英文字母** — 带数字（如 `Token1`）被拒绝
4. **裸 Entry 返回 400** — 服务器期望 Feed 而非 Entry

### 更新联系人

- **POST /contact/ 只需 email 即可更新现有联系人** — API 通过 email 匹配并更新已有记录
- **xlsx Token1~Token15 映射**: Token1→Token, Token2→TokenT, Token3→TokenH, Token4→TokenF, Token5→TokenI, Token6→TokenS, Token7→TokenE, Token8→TokenG, Token9→TokenN, Token10→TokenTEN, Token11→TokenL, Token12→TokenW, Token13→TokenR, Token14→TokenO, Token15→TokenV

### 查询联系人的限制

- **`GET /contact/?field=email&q=xxx` 无效** — `/contact/` 端点不支持 email 过滤
- **`GET /contact/{id}/` 按 ID 精确查询** — 返回单个 `<entry>` 根元素（不是 `<feed>`）

### 添加联系人到列表 — 服务器端 Bug（🔴 确认 21Vianet 环境 Bug）

**更新 (2026-06-12)**: 之前的 500 错误变为 201 但仍**忽略 `<link>` 元素**。OAuth HMAC-SHA1 签名（C# SDK 方式）现在可正常工作。

**API 行为**:

| href 格式 | 结果 | 实际效果 |
|-----------|------|---------|
| `{HOST}/list/{id}/` (带斜杠) | 201 | **忽略 link，只更新联系人** |
| `{HOST}/list/{id}` (不带斜杠) | 500 | **服务器内部异常** |

**已尝试的 30+ 种方案全部失败**: link rel="related", rel="adds", rel="isPartOf", um:listName, um:list, um:addContacts, query param list=, method=put, POST /list/{id}/, POST /contactimport/, PUT /contact/{id}/, JSON body, X-Rel header, OAuth vs BasicAuth, etc.

**OAuth HMAC-SHA1 签名 (C# SDK 方式)**:
- 签名数据: `http://{API_KEY}?{排序的参数}` (包含 Header: Authorization, Host, Content-Type)
- HMAC-SHA1(data, API_SECRET) → base64
- URL 参数逐字符 URL 编码（C# `HttpUtility.UrlEncode` 风格）
- 请求不使用 BasicAuth，只用 OAuth 查询参数 + `Authorization: OAuth` header

**待解决的替代方案**:
- 登录 Unimarketing 网页手动添加联系人到列表
- 使用 CSV 导入功能
- 联系 21Vianet Unimarketing 技术支持

See also: [[unimarketing-account-info]]
