---
name: edm-process
description: Process EDM email — extract SN, create folder, convert xlsx to CSV, extract nested .msg, convert to HTML with token replacement
---

# EDM Email Processor

完整 EDM 邮件处理流程：从原始邮件提取 SN 创建文件夹，转换 xlsx 为 CSV，提取嵌套 .msg 并转换为 HTML，自动替换占位符。

## Workflow

1. 将原始邮件 `.msg` 和 `.xlsx` 联系人列表放在 `EDM/Temp/` 目录下
2. 从原始邮件主题提取 SN 编号（如 `SN-12345`）
3. 在 `EDM/` 下创建 `SN-12345/` 文件夹
4. 将 `.xlsx` 复制到 SN 文件夹并转换为 CSV（GB18030 编码）
5. 生成 `formal_*.csv`（全部行）和 `test_*.csv`（N 行，每行配对测试邮箱）
6. 从原始邮件提取嵌套 EDM 模板 `.msg`（无收件人的那个），保存到 SN 文件夹
7. 通过 win32com 读取嵌套 .msg 的 HTMLBody，在 `<body>` 后插入主题行
8. 自动替换 `%%TokenN%%` / `%%SubIdN%%` 占位符（支持跨 `<span>` 拆分，从 `Tokenmapping.json` 读取映射）
9. 保存为 `EDM_template.html`

## Token 占位符替换

Outlook 经常把 `%%Token1%%` 拆分成多个 `<span>` 标签：
```html
<span>%%</span><span>Token</span><span>1%%</span>
```

脚本会先剥离 HTML 标签得到纯文本，在纯文本中匹配占位符模式，再将位置映射回原始 HTML 进行替换，**不影响表格结构**。

映射文件：项目根目录 `Tokenmapping.json`
```json
[{"Name": "Token1", "Value": "${contactToken}"}]
```

## Usage

```bash
python .claude/skills/edm-process/edm_process.py
```

无需参数，自动读取 `EDM/Temp/` 中的 .msg 和 .xlsx 文件。

## Output

`EDM/SN-xxxxx/` 目录下生成：
- `Token1-3 SN-xxxxx.xlsx` — 原始联系人列表
- `Token1-3 SN-xxxxx.csv` — GB18030 编码 CSV（单元格验证通过，CLI 保留，GUI 删除）
- `formal_Token1-3 SN-xxxxx.csv` — 正式 CSV（保留原信息全部行）
- `test_Token1-3 SN-xxxxx.csv` — 测试 CSV（保留 N 行最长且不同的行，替换 Email 为测试邮箱）
- `请在...2026.msg` — 嵌套 EDM 模板 .msg
- `EDM_template.html` — Outlook 原生 HTMLBody + 主题行 + token 替换
- `process.log` — GUI 处理日志（仅 GUI 生成）

## EDM GUI Tool (edm_gui.py)

GUI 桌面应用（tkinter），支持通过界面选择文件并处理。额外功能：

- **Discover 按钮** — 根据 MSG 邮件中的 SN 号，自动在配置目录下检索 XLSX 文件
- **检索目录配置** — `xlsx_search_dir.json` 文件，可编辑 `search_directory` 字段修改检索路径
- **Import Test/Formal List** — 直接通过 Unimarketing API 导入联系人列表
- **PyInstaller 打包** — `edm_gui.spec` 生成 `EDM Email Processor.exe`

```bash
python edm_gui.py
```

## Public API

| Function | Description |
|----------|-------------|
| `extract_sn(text)` | Extract SN-12345 from text |
| `find_target_attachment_idx(msg_path)` | Find nested .msg (0 recipients) index via olefile |
| `save_target_attachment(att, save_dir)` | Save attachment to disk |
| `convert_xlsx_to_csv(xlsx_path)` | Convert xlsx to CSV (subprocess to xlsx_to_csv skill) |
| `generate_formal_test_csv(xlsx_path)` | Generate formal_*.csv and test_*.csv from source CSV |
| `replace_span_tokens(html, mapping)` | Replace %%TokenN%%/%%SubIdN%% split across <span> tags |
| `convert_msg_to_html(msg_path, output_html)` | Convert .msg to HTML via win32com with token replacement |
| `process_edm()` | Full EDM workflow entry point |

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
- `EDM_template.html` 在 `<body>` 后插入主题行，并按 `Tokenmapping.json` 替换跨 `<span>` 占位符
- xlsx 文件复制（不移动）到 SN 文件夹，Temp/ 保留原始文件
