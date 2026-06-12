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
  --html-file "path/to/file.html"

# From inline HTML content
python .claude/skills/unimarketing-create-message/unimarketing_create_message.py \
  --title "Quick Test" \
  --html-content "<p>Hello World</p>"

# List available folders
python .claude/skills/unimarketing-create-message/unimarketing_create_message.py --list-folders
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
| `--no-header-footer` | Disable platform header/footer | Off |
| `-v` | Print request XML | Off |

## Important Constraints

- **HTML must be escaped** — The API wraps content in `<![CDATA[ ... ]]>` so `<`, `>`, `&` in the HTML must be escaped as `&lt;`, `&gt;`, `&amp;` before being placed inside the CDATA block. The script handles this automatically.
- **Omit `footerName`** — Using `um:footerName` causes validation errors unless the exact footer exists for the chosen language.
- **Large Word HTML** — Raw Word HTML from Outlook (~37KB) may cause server 500 errors. The script strips Word-specific XML (`mso-bookmark`, `o:p`, conditional comments) to reduce size.
- **Does NOT send** — This only creates a draft in the Unimarketing folder. The user must send it from the web UI.
