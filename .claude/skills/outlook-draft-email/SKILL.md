---
name: outlook-draft-email
description: Create an email draft via win32com — saves to Drafts folder, never sends
---

# Outlook Draft Email

Create an Outlook email draft. Saves to Drafts folder — **never sends automatically**.

## Usage

```bash
# Create a plain text draft
python .claude/skills/outlook-draft-email/outlook_draft_email.py \
    --to "user@example.com" \
    --subject "Test Email" \
    --body "This is the body."

# Create with CC and HTML body
python .claude/skills/outlook-draft-email/outlook_draft_email.py \
    --to "user@example.com" \
    --cc "manager@example.com" \
    --subject "Report" \
    --body "<h1>Title</h1><p>Content</p>" \
    --html
```

## Output

Displays draft info and a reminder to open Outlook and send manually.
