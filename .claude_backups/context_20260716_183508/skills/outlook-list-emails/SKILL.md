---
name: outlook-list-emails
description: List recent emails from an Outlook folder via win32com (read-only)
---

# Outlook List Emails

List recent emails from an Outlook folder.

## Usage

```bash
# List last 10 inbox emails
python .claude/skills/outlook-list-emails/outlook_list_emails.py Inbox

# List last 20 sent emails
python .claude/skills/outlook-list-emails/outlook_list_emails.py "Sent Items" --count 20

# List draft emails
python .claude/skills/outlook-list-emails/outlook_list_emails.py Drafts
```

## Output

Table with: Subject, From, SentOn, UnRead, EntryID
