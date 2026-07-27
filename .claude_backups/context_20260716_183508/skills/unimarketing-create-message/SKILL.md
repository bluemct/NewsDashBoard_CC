---
name: unimarketing-create-message
description: Create an email draft via Unimarketing API — POST /message/ with HTML content (does NOT send)
---

# Unimarketing Create Message

Create an email draft in the Unimarketing platform via `POST /message/`. This saves the email template to a folder — it **never sends** the email.

## Usage

```bash
# From an HTML file
python .claude/skills/unimarketing-create-message/unimarketing_create_message.py \
  --title "My EDM Email" \
  --html-file "path/to/EDM_template.html" \
  --folder 14409 \
  --header-footer
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--title` | Email name (required) | - |
| `--html-file` | Path to HTML file for email body | - |
| `--html-content` | Inline HTML string | - |
| `--folder` | Folder ID to save to | 14409 (Azure) |
| `--language` | Language for header/footer | zh_CN |
| `--trigger-type` | `normal`=marketing, `transaction`=transactional | normal |
| `--header-footer` | Enable platform header/footer wrapper | Off |
| `--no-header-footer` | Disable platform header/footer | Off |

## Platform Header/Footer

- `--header-footer` sets `isContainPageHeadFooter=1` and `footerName=htmlHeader`
- The `htmlHeader` template injects **Chinese** header + footer (TABLE wrapper: TR1 header + TR2 content + TR3 footer)
- Header: "如果不显示图片，请查看 网页版本" + 21Vianet
- Footer: "为了确保您能收到我们的信息" + 退订 + 投诉

## Important: HTML Content Format

- **Must extract `<head>` + `<body>` content, removing `<html>`, `<head>`, `<body>` wrapper tags**
- `_extract_body()` extracts `<head>` styles + `<body>` content concatenated
- Sending full HTML document (`<html><body>...`) causes platform to skip footer injection
- Sending body-only loses `<head>` styles (formatting breaks)
- The `edm_process.py` outputs `EDM_template_combined.html` for this purpose

## Important Constraints

- **HTML must be escaped** — The API wraps content in `<![CDATA[ ... ]]>` so `<`, `>`, `&` in the HTML must be escaped as `&lt;`, `&gt;`, `&amp;`
- **Omit `footerName`** — Using `um:footerName` causes validation errors for most template names. Only `htmlHeader` is verified working.
- **Does NOT send** — This only creates a draft in the Unimarketing folder. The user must send it from the web UI.
