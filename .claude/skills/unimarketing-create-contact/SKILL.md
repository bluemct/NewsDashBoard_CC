---
name: unimarketing-create-contact
description: Create or update a contact via Unimarketing API — POST /contact/ with Atom Feed XML
---

# Unimarketing Contact Create / Update

Create or update a single contact in the 21Vianet Unimarketing system via API. Uses `POST /contact/` — not the bulk import endpoint (`/contactimport/`).

## Key Behavior

- **POST /contact/ 只需 email** — 如果 email 存在则更新，不存在则新建，**不需要 contact_id**
- **GET /contact/?field=email&q=xxx 无效** — API 不支持 email 过滤，总是返回前50条
- **GET /contact/{id}/** — 按 ID 精确查询，返回单个 `<entry>` 根元素（不是 `<feed>`）

## Usage

```bash
# Single contact with token attributes
python .claude/skills/unimarketing-create-contact/unimarketing_create_contact.py test@example.com --token Token "value1" --token TokenT "value2"

# Batch from JSON file
python .claude/skills/unimarketing-create-contact/unimarketing_create_contact.py --json-input contacts.json

# Verbose mode (prints XML body)
python .claude/skills/unimarketing-create-contact/unimarketing_create_contact.py test@example.com --token Token "value" -v
```

## JSON Input Format

```json
[
  {"email": "user1@example.com", "attributes": {"Token": "value1", "TokenT": "text"}},
  {"email": "user2@example.com", "attributes": {"Token": "value2"}}
]
```

## Attribute Field Names

Must match the list template defined fields. **Pure English letters only** — no digits or special characters. `Token1` (with digit) will be rejected.

Common fields: `Token`, `TokenT`, `TokenH`, `TokenF`, `TokenI`, `TokenS`, `TokenE`, `TokenG`, `TokenN`, `TokenTEN`, `TokenL`, `TokenW`, `TokenR`, `TokenO`, `TokenV`

### xlsx Token1~Token15 字段名映射

EDM 导出的 xlsx 文件列名为 `Token1`~`Token15`（含数字），API 不接受含数字的字段名，需要映射：

| xlsx 列名 | API 字段名 |
|-----------|-----------|
| Token1 | Token |
| Token2 | TokenT |
| Token3 | TokenH |
| Token4 | TokenF |
| Token5 | TokenI |
| Token6 | TokenS |
| Token7 | TokenE |
| Token8 | TokenG |
| Token9 | TokenN |
| Token10 | TokenTEN |
| Token11 | TokenL |
| Token12 | TokenW |
| Token13 | TokenR |
| Token14 | TokenO |
| Token15 | TokenV |

## Field Value Rules

- Allowed: Chinese characters, numbers, letters, spaces, commas, hyphens (`-`)
- UUID 格式值（含连字符）可以正常写入

## Atom XML Format

Must use `<feed>` wrapper (bare `<entry>` returns 400):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>test@example.com</email>
    <um:attribute name="Token">value1</um:attribute>
    <um:attribute name="TokenT">value2</um:attribute>
  </entry>
</feed>
```

## Requirements

- Python 3.x
- `requests` (install: `pip install requests`)
