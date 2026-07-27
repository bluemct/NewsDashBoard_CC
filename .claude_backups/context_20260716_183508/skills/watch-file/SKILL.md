---
name: watch-file
description: Monitor a file for changes by comparing checksums
metadata:
  type: skill
  version: "1.0"
---

# File Watcher Skill

Monitors `runoob-claude-demo/main.py` for changes.

## Instructions

1. Read the current file: `runoob-claude-demo/main.py`
2. Compute its MD5 checksum with: `md5sum runoob-claude-demo/main.py` (or `certutil -hashfile` on Windows)
3. Read the previously stored checksum from `.claude/skills/watch-file/.checksum`
4. Compare:
   - If checksum differs → report the change, read the new content, show a diff summary, and update `.checksum`
   - If same → report "no changes detected"
5. On first run (no `.checksum` exists) → store the initial checksum and report "monitoring started"

## Trigger
User invokes `/watch-file` or asks to check if main.py has changed.
