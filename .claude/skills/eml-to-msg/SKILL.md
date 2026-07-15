---
name: eml-to-msg
description: Convert .eml email files to .msg format — only top-level RFC822 parts preserved as .msg attachments, does not descend into forwarded-message chains
---

## EML to MSG Conversion Skill

将 `.eml` 邮件文件转换为 Outlook `.msg` 格式，**保留顶层的 RFC822 邮件附件**。

### 转换原理

1. 解析 `.eml` MIME 内容，**只遍历顶层结构**（不递归进入 `message/rfc822` 内部，避免把回复链当附件）
2. 顶层提取：HTML body（按 MIME charset 解码）、`message/rfc822`（转发/嵌套邮件）、文件附件
3. 每个 `message/rfc822` 单独创建 Outlook MailItem，SaveAs 为临时 `.msg`
4. 创建外层 MailItem，将嵌套 `.msg` 作为附件加入
5. 最终 SaveAs 为完整 `.msg` 文件

### 编码处理

HTML 正文按 MIME 声明的 `Content-Type: charset` 解码，回退顺序：
`charset → utf-8 → gb18030 → latin-1`

### 输出

- `EDM/Temp/SN-xxxxx_email.msg` — 转换后的 .msg（含嵌套附件）

### 用法

```python
from eml_to_msg import eml_to_msg
result = eml_to_msg('EDM/Temp/SN-56619_email.eml')
```

或直接运行：

```bash
python .claude/skills/eml-to-msg/eml_to_msg.py EDM/Temp/SN-56619_email.eml
```

### 依赖

- `win32com` — 需要 Outlook 运行且已连接 Exchange
- `extract-msg` — 验证输出
