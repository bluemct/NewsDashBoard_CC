---
name: msg-to-html
description: "Convert Outlook .msg files to HTML code using win32com"
---

# MSG to HTML Converter

Convert Outlook `.msg` email files to HTML format via win32com. Outputs the raw HTMLBody with zero modifications.

## Usage

```bash
python .claude/skills/msg-to-html/msg_to_html.py <input.msg> [output.html]
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| input     | Yes      | Path to source .msg file |
| output    | No       | Path to output HTML file (default: same name, .html extension) |

## Output

- HTML file with raw HTMLBody (zero modifications)

## Requirements

- Python 3.x
- `win32com` (install: `pip install pypiwin32`)
- Outlook running and connected to Exchange