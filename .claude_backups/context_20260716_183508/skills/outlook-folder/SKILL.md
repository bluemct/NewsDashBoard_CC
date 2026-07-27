---
name: outlook-folder
description: Find Outlook folders by name via win32com
---

# Outlook Find Folder

Find an Outlook folder by name, or list all folders.

## Folder constants

| Name | Constant |
|------|----------|
| Inbox | 6 |
| Sent Items | 5 |
| Drafts | 16 |
| Deleted Items | 3 |
| Outbox | 4 |
| Junk Email | 23 |

## Usage

```bash
# Get default folder by name
python .claude/skills/outlook-folder/outlook_folder.py Inbox

# List all top-level folders
python .claude/skills/outlook-folder/outlook_folder.py --list
```
