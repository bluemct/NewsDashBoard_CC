---
name: email-html2text
description: Convert HTML email body to plain text using Python
---

# HTML to Text

Convert HTML email body to readable plain text using Windows COM HTMLFile object.

## Usage

```bash
python .claude/skills/email-html2text/html_to_text.py --html "<h1>Hello</h1><p>World</p>"

# Or from stdin
echo "<b>Bold text</b>" | python .claude/skills/email-html2text/html_to_text.py
```
