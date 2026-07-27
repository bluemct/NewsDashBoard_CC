---
name: email-parse-ticket
description: Extract ticket/request numbers from email body text using Python regex
---

# Parse Ticket Number

Extract ticket/request numbers from email text using regex patterns.

## Usage

```bash
python .claude/skills/email-parse-ticket/parse_ticket.py --text "Your Request #12345 is ready"

# Custom pattern
python .claude/skills/email-parse-ticket/parse_ticket.py --text "CASE-00123" --pattern "CASE[-:]?\s*(\d+)"

# From stdin
echo "工单 98765" | python .claude/skills/email-parse-ticket/parse_ticket.py
```
