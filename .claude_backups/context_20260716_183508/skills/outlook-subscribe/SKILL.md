---
name: outlook-subscribe
description: Monitor Outlook Inbox for new mail via win32com
---

# Outlook Subscribe

Monitor Outlook Inbox for new email arrivals using win32com.

## Usage

```bash
python .claude/skills/outlook-subscribe/outlook_subscribe.py

# With a specific callback script
python .claude/skills/outlook-subscribe/outlook_subscribe.py --callback my_handler.py
```

## How it works

- Uses `outlook.Application` to poll Inbox folder
- Checks every 5 seconds for unread messages
- Prints Subject, From, ReceivedTime of new emails
