---
name: msg-to-html
description: "Convert Outlook .msg files to HTML code for copy-paste into RTF-capable email systems"
---

# MSG to HTML Converter

Convert Outlook `.msg` email files to HTML format. The output HTML contains the full email body, subject, sender, recipients, and date — ready to copy-paste into a system that converts HTML to RTF.

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

- HTML file with full email content (header + body)
- Console prints the HTML code for easy copy-paste

## Requirements

- Python 3.x
- `win32com` (install: `pip install pypiwin32`)

## Example

```bash
python .claude/skills/msg-to-html/msg_to_html.py email.msg
python .claude/skills/msg-to-html/msg_to_html.py email.msg output.html
```
