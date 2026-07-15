---
name: eml-to-msg
description: Convert .eml email files to .msg format with nested RFC822 attachments preserved
---

## EML to MSG Conversion Skill

将 `.eml` 邮件文件转换为 Outlook `.msg` 格式，**保留嵌套的 RFC822 邮件附件**。

### 转换原理

1. 解析 `.eml` MIME 内容，提取 HTML body（按 MIME 声明的 charset 解码，支持 gb2312/utf-8/gb18030）
2. 每个嵌套 `message/rfc822` 单独创建 Outlook MailItem，按各自 charset 解码 HTML，SaveAs 为临时 `.msg`
3. 创建外层 MailItem，将嵌套 `.msg` 作为附件加入
4. 最终 SaveAs 为完整 `.msg` 文件

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
