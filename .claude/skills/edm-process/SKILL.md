---
name: edm-process
description: Process EDM email — extract SN, create folder, convert xlsx to CSV, extract nested .msg, convert to HTML
---

# EDM Email Processor

完整 EDM 邮件处理流程：从原始邮件提取 SN 创建文件夹，转换 xlsx 为 CSV，提取嵌套 .msg 并转换为 HTML。

## Workflow

1. 将原始邮件 `.msg` 和 `.xlsx` 联系人列表放在 `EDM/Temp/` 目录下
2. 从原始邮件主题提取 SN 编号（如 `SN-12345`）
3. 在 `EDM/` 下创建 `SN-12345/` 文件夹
4. 将 `.xlsx` 复制到 SN 文件夹并转换为 CSV（GB18030 编码）
5. 从原始邮件提取嵌套 EDM 模板 `.msg`（无收件人的那个），保存到 SN 文件夹
6. 通过 win32com 读取嵌套 .msg 的 HTMLBody，在 `<body>` 后插入主题行，保存为 `EDM_template.html`

## Usage

```bash
python .claude/skills/edm-process/edm_process.py
```

无需参数，自动读取 `EDM/Temp/` 中的 .msg 和 .xlsx 文件。

## Output

`EDM/SN-xxxxx/` 目录下生成：
- `Token1-3 SN-xxxxx.xlsx` — 原始联系人列表
- `Token1-3 SN-xxxxx.csv` — GB18030 编码 CSV（单元格验证通过）
- `请在...2026.msg` — 嵌套 EDM 模板 .msg
- `EDM_template.html` — Outlook 原生 HTMLBody + 主题行

## Requirements

- Python 3.x
- `extract-msg` (install: `pip install extract-msg`)
- `olefile` (install: `pip install olefile`)
- `openpyxl` (install: `pip install openpyxl`)
- `win32com` (install: `pip install pypiwin32`)
- Outlook 运行且已连接 Exchange

## Notes

- 原始邮件包含两个嵌套 `.msg` 附件：审批邮件（有收件人）和 EDM 模板邮件（无收件人）
- 脚本只保存无收件人的 EDM 模板邮件
- `EDM_template.html` 除了 `<body>` 后插入主题行外，HTMLBody 其余内容零修改
- xlsx 文件复制（不移动）到 SN 文件夹，Temp/ 保留原始文件