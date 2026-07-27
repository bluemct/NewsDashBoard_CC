---
name: outlook-email
description: Read a single email by EntryID using win32com
---

# Outlook Read Email

Read email details (Subject, Body, Sender, Recipients) by EntryID.

## Usage

```bash
# Read email by EntryID
python .claude/skills/outlook-email/outlook_email.py "<EntryID>"

# Read and show plain text body
python .claude/skills/outlook-email/outlook_email.py "<EntryID>" --plain-text
```
