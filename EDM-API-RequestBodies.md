# EDM 联系人批量导入 — 实际请求体文档

> 基于真实导入测试整理
> 源文件: `vivian_test_Token1-15 - SN-56230.xlsx`（2 条联系人，15 个 Token 属性）
> 列表 ID: 349793 | 导入任务 ID: 155092

---

## 通用说明

| 项目 | 值 |
|------|------|
| Base URL | `http://services.unimarketing.com.cn` |
| Content-Type | `application/atom+xml` |
| Authorization | `Basic {base64(apiKey:apiSecret)}` |
| 通用 URL 参数 | `apikey=xxx&method=get\|post\|put&alt=atom` |
| Atom 命名空间 | `xmlns="http://www.w3.org/2005/Atom"` |
| UM 命名空间 | `xmlns:um="http://www.unimarketing.com.cn/xmlns/"` |

> **关键注意事项**
> - `<email>` 使用 Atom 默认命名空间，不带 `um:` 前缀
> - XML 请求体编码：UTF-8；CSV 文件编码：GBK

---

## 完整导入流程（5 步）

```
┌─────────────────────────────────────────────────────────────────────┐
│  0. xlsx → CSV 转换 (本地)                                          │
│     ↓                                                               │
│  1. 创建联系人列表 (含属性定义)                                      │
│     POST /list/ → 返回 listId                                       │
│     ↓                                                               │
│  2. 创建导入任务 (building)                                         │
│     POST /contactimport/ → 返回 importId                            │
│     ↓                                                               │
│  3. 提交导入联系人                                                  │
│     POST /contactimport/import/{importId}/ → status=waiting         │
│     ↓                                                               │
│  4. 执行导入任务                                                     │
│     POST /contactimport/{importId} ?method=put → status=executing   │
│     ↓                                                               │
│  5. 查询导入结果                                                     │
│     GET /contactimport/{importId}/ → status=导入成功                │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Step 1 — 创建联系人列表

**请求**
```
POST /list/?apikey=customersupport&method=post&alt=atom
```

**请求体**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <title>vivian_test_Token1-15 - SN-56230_20260617104841</title>
  <subtitle>vivian_test_Token1-15 - SN-56230_20260617104841</subtitle>
  <um:attribute name="Token" label="Token1" visible="true" public="true" sn="1" type="text"></um:attribute>
  <um:attribute name="TokenT" label="Token2" visible="true" public="true" sn="2" type="text"></um:attribute>
  <um:attribute name="TokenH" label="Token3" visible="true" public="true" sn="3" type="text"></um:attribute>
  <um:attribute name="TokenF" label="Token4" visible="true" public="true" sn="4" type="text"></um:attribute>
  <um:attribute name="TokenI" label="Token5" visible="true" public="true" sn="5" type="text"></um:attribute>
  <um:attribute name="TokenS" label="Token6" visible="true" public="true" sn="6" type="text"></um:attribute>
  <um:attribute name="TokenE" label="Token7" visible="true" public="true" sn="7" type="text"></um:attribute>
  <um:attribute name="TokenG" label="Token8" visible="true" public="true" sn="8" type="text"></um:attribute>
  <um:attribute name="TokenN" label="Token9" visible="true" public="true" sn="9" type="text"></um:attribute>
  <um:attribute name="TokenTEN" label="Token10" visible="true" public="true" sn="10" type="text"></um:attribute>
  <um:attribute name="TokenL" label="Token11" visible="true" public="true" sn="11" type="text"></um:attribute>
  <um:attribute name="TokenW" label="Token12" visible="true" public="true" sn="12" type="text"></um:attribute>
  <um:attribute name="TokenR" label="Token13" visible="true" public="true" sn="13" type="text"></um:attribute>
  <um:attribute name="TokenO" label="Token14" visible="true" public="true" sn="14" type="text"></um:attribute>
  <um:attribute name="TokenV" label="Token15" visible="true" public="true" sn="15" type="text"></um:attribute>
</entry>
```

**响应**
```xml
<entry xmlns="http://www.w3.org/2005/Atom">
  <id>http://services.unimarketing.com.cn/list/349793</id>
  <title>vivian_test_Token1-15 - SN-56230_20260617104841</title>
  <subtitle>vivian_test_Token1-15 - SN-56230_20260617104841</subtitle>
</entry>
```

**字段说明**
- `um:attribute name`: 系统属性名（Token / TokenT / TokenH / TokenF / TokenI / TokenS / TokenE / TokenG / TokenN / TokenTEN / TokenL / TokenW / TokenR / TokenO / TokenV）
- `um:attribute label`: 显示名称，对应 xlsx 表头（Token1 ~ Token15）
- `sn`: 排序号，从 1 开始递增
- `type`: 固定 `"text"`

---

### Step 2 — 创建导入任务

**请求**
```
POST /contactimport/?apikey=customersupport&method=post&alt=atom
```

**请求体**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <title>API导入_20260617104843</title>
  <um:type>UpdateExistsAddNew</um:type>
  <um:reportOpen>false</um:reportOpen>
  <um:importMethod>api</um:importMethod>
  <link href="http://services.unimarketing.com.cn/list/349793" rel="related"></link>
  <um:status>building</um:status>
</entry>
```

**响应**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>http://services.unimarketing.com.cn/contactimport/155092</id>
  <title type="text">API导入_20260617104843</title>
  <updated>2026-06-17T02:48:43.871Z</updated>
  <um:reportOpen>false</um:reportOpen>
  <um:reportEmail></um:reportEmail>
  <um:status>building</um:status>
  <um:total>0</um:total>
</entry>
```

**字段说明**
- `um:type`: `UpdateExistsAddNew` — 存在则更新，不存在则新增
- `um:importMethod`: `api`（API 导入）或 `csv`（CSV 文件导入）
- `link href`: 必须指向关联的联系人列表 `list/{listId}`
- `um:status`: 创建时必须为 `building`

---

### Step 3 — 提交导入联系人

**请求**
```
POST /contactimport/import/155092/?apikey=customersupport&method=post&alt=atom
```

**请求体**
```xml
<feed xmlns="http://www.w3.org/2005/Atom">
  <link href="http://services.unimarketing.com.cn/contactimport/155092" rel="related"></link>

  <entry xmlns:um="http://www.unimarketing.com.cn/xmlns/">
    <email>lwy00705@163.com</email>
    <um:attribute name="Token">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, ARM_PROD_FW</um:attribute>
    <um:attribute name="TokenT">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, ARM-dev-key-vault</um:attribute>
    <um:attribute name="TokenH">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, AVEM-WEP3-CHINA-ACTIONGROUP</um:attribute>
    <um:attribute name="TokenF">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, AVEM-WEP3-CHINA-LAB</um:attribute>
    <um:attribute name="TokenI">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, AVEM-WEP3-CHINA-NETWORK</um:attribute>
    <um:attribute name="TokenS">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, AVEM-WEP3-CHINAPROD</um:attribute>
    <um:attribute name="TokenE">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, AVEM-WEP3-LOGANALYTICS</um:attribute>
    <um:attribute name="TokenG">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, CH_CHINA_EAST_NSG</um:attribute>
    <um:attribute name="TokenN">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, CH1AVEMCHEM</um:attribute>
    <um:attribute name="TokenTEN">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, CH1AVEMPFIL01</um:attribute>
    <um:attribute name="TokenL">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, FL-BACKUP-VAULT-2</um:attribute>
    <um:attribute name="TokenW">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, NetworkWatcherRG</um:attribute>
    <um:attribute name="TokenR">77095aeb-90d8-41c6-ab46-bab6f9a3a35d, Exxon_AVA, WEP3-Backup-Vault</um:attribute>
    <um:attribute name="TokenO">92563130-7daa-4a96-bb94-2a58c382b3e6, SDWAN, resourcegroup_networkimprovement</um:attribute>
    <um:attribute name="TokenV">92563130-7daa-4a96-bb94-2a58c382b3e6, SDWAN, SDWAN</um:attribute>
  </entry>

  <entry xmlns:um="http://www.unimarketing.com.cn/xmlns/">
    <email>liu.wenya@oe.21vianet.com</email>
    <um:attribute name="Token">45f53c34-138c-4c11-a64d-816201a4fb21, corp comm, RG-CN-DELTAWEBSITE</um:attribute>
    <um:attribute name="TokenT">a6ce627a-df16-4bcf-846d-398462210147, 华北_云I云N, DGCWEB</um:attribute>
    <um:attribute name="TokenH">a6d1b66b-97ae-4634-ace1-72efbfddd8dc, Corp IT, RG-IT-TEST-EnergyCloud</um:attribute>
  </entry>
</feed>
```

**响应**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>http://services.unimarketing.com.cn/contactimport/155092</id>
  <um:reportOpen>false</um:reportOpen>
  <um:reportEmail></um:reportEmail>
  <um:status>waiting</um:status>
  <um:total>2</um:total>
</entry>
```

**关键要点**
- `feed/link`: 必须指向 `contactimport/{importId}`，`rel="related"`
- `<email>` 使用 Atom 默认命名空间（不带 `um:` 前缀）
- `<um:attribute name="...">` 为自定义属性，只提交有值的属性
- 第二个联系人只有 Token1-3 有值，其余省略

---

### Step 4 — 执行导入任务

**请求**
```
POST /contactimport/155092?apikey=customersupport&method=put&alt=atom
```

> HTTP 方法为 **POST**（不是 PUT），URL 参数 `method=put` 指示服务端执行更新操作。HTTP PUT 会返回 405。

**请求体**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <um:status>executing</um:status>
</entry>
```

**响应**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>http://services.unimarketing.com.cn/contactimport/155092</id>
  <updated>2026-06-17T02:48:44.221Z</updated>
  <um:reportOpen>false</um:reportOpen>
  <um:reportEmail></um:reportEmail>
  <um:status>waiting</um:status>
  <um:total>2</um:total>
</entry>
```

---

### Step 5 — 查询导入结果

**请求**
```
GET /contactimport/155092/?apikey=customersupport&method=get&alt=atom
```

**响应**
```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>http://services.unimarketing.com.cn/contactimport/155092</id>
  <um:importMethod>csv</um:importMethod>
  <um:type>UpdateExistsAddNew</um:type>
  <link href="http://services.unimarketing.com.cn/list/349793" rel="related"></link>
  <um:total>2</um:total>
  <um:status>导入成功</um:status>
  <um:validNum>2</um:validNum>
  <um:inValidNum>0</um:inValidNum>
  <um:addToListSuccessNum>2</um:addToListSuccessNum>
  <um:validateHandlerNum>2</um:validateHandlerNum>
  <um:addSuccessNum>0</um:addSuccessNum>
  <um:updateSuccessNum>2</um:updateSuccessNum>
  <um:breakImportRule>false</um:breakImportRule>
  <um:addToTempNum>0</um:addToTempNum>
</entry>
```

**结果字段说明**
| 字段 | 含义 |
|------|------|
| `um:total` | 总记录数 |
| `um:validNum` | 有效记录数 |
| `um:inValidNum` | 无效记录数 |
| `um:addToListSuccessNum` | 成功加入列表数 |
| `um:addSuccessNum` | 新增成功数 |
| `um:updateSuccessNum` | 更新成功数 |
| `um:validateHandlerNum` | 已处理验证数 |
| `um:breakImportRule` | 是否违反导入规则 |
| `um:addToTempNum` | 加入临时表数 |

**导入任务状态流转**
```
building → waiting → queueing → executing → execute_succeed / execute_failure / execute_stop
```

> 注意：导入是异步执行的，提交后需要等待数秒再查询结果。建议轮询间隔 3-5 秒。

---

## 其他联系人 API

### 添加单个联系人

```
POST /contact/?apikey=xxx&method=post&alt=atom
```

```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <email>user@example.com</email>
  <um:type>html</um:type>
  <um:status>activity</um:status>
  <um:attribute name="Token">value1</um:attribute>
  <link href="http://services.unimarketing.com.cn/list/{listId}" rel="related"></link>
</entry>
```

### 更新联系人

```
POST /contact/{contactId}?apikey=xxx&method=post&alt=atom
```

```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <email>user@example.com</email>
  <title>联系人姓名</title>
  <um:type>html</um:type>
  <um:status>activity</um:status>
  <um:attribute name="Token">newValue</um:attribute>
</entry>
```

### 查询联系人

```
GET /contact/?apikey=xxx&method=get&alt=atom&q=email:user@example.com
```

### 查询联系人列表

```
GET /list/?apikey=xxx&method=get&alt=atom
```

### 查询联系人详情

```
GET /contact/{contactId}/?apikey=xxx&method=get&alt=atom
```

---

## 附录

### A. Token 属性映射表

| CSV 表头 | 系统属性名 | CSV 表头 | 系统属性名 |
|----------|-----------|----------|-----------|
| Token1 | Token | Token9 | TokenN |
| Token2 | TokenT | Token10 | TokenTEN |
| Token3 | TokenH | Token11 | TokenL |
| Token4 | TokenF | Token12 | TokenW |
| Token5 | TokenI | Token13 | TokenR |
| Token6 | TokenS | Token14 | TokenO |
| Token7 | TokenE | Token15 | TokenV |
| Token8 | TokenG | | |

### B. SubId 属性映射表

| CSV 表头 | 系统属性名 | CSV 表头 | 系统属性名 |
|----------|-----------|----------|-----------|
| SubId1 | SubId | SubId9 | SubIdN |
| SubId2 | SubIdT | SubId10 | SubIdTEN |
| SubId3 | SubIdH | SubId11 | SubIdL |
| SubId4 | SubIdF | SubId12 | SubIdW |
| SubId5 | SubIdI | SubId13 | SubIdR |
| SubId6 | SubIdS | SubId14 | SubIdO |
| SubId7 | SubIdE | SubId15 | SubIdV |
| SubId8 | SubIdG | | |

### C. 编码说明

- **XML 请求体**: UTF-8 编码
- **CSV 文件**: GBK 编码（xlsx 转 CSV 由 `XlsxToCsvUtil` 转换）
- **服务器响应**: GBK 编码解析

### D. 错误排查

| 错误 | 原因 | 解决 |
|------|------|------|
| HTTP 405 | 对 import task 使用了 HTTP PUT | 改用 POST + `method=put` |
| HTTP 500 | email 使用了 `<um:email>` | 改用 `<email>`（Atom 命名空间） |
| HTTP 400 | "email address is required" | 检查 email 字段格式、Feed link 指向 |
| status=等待 total=0 | 查询过早 | 导入是异步的，等待 3-5 秒后再次查询 |
