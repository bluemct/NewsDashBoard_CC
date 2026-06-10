---
name: email-track-conversation
description: Track email conversations by EntryID to distinguish sent mail from replies
---

# Track Email Conversation

Track email conversations to classify incoming mail as: Sent, Reply, or Other.

## Usage

```bash
python .claude/skills/email-track-conversation/track_conversation.py \
    --entry-id "<EntryID>" \
    --my-address "user@example.com"
```

Reads the email from Outlook and classifies it based on the sender and subject.
