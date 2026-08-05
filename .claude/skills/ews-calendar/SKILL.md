---
name: ews-calendar
description: EWS Calendar — query meeting room/calendar availability and book rooms via Exchange Web Services
---

# EWS Calendar

Query calendar availability and book meeting rooms via Exchange Web Services (exchangelib).

## Config

Create `.claude/skills/ews-calendar/ews_config.json`:

```json
{
  "ews": {
    "url": "https://mail.21vianet.com/EWS/Exchange.asmx",
    "domain_user": "21vianet\\ps-tier2.support",
    "password": "your-password",
    "mailbox": "ps-tier2.support@oe.21vianet.com"
  }
}
```

If not present, falls back to `.edm_agent_config.json` in project root.

## Dependency

```bash
pip install exchangelib
```

## Usage

### Query calendar (one person/room)

```bash
python .claude/skills/ews-calendar/ews_calendar.py query --email 13-3@oe.21vianet.com --date 2026-08-06
```

Shows busy events + free slots during work hours (09:00-18:00).

### Book a room

```bash
python .claude/skills/ews-calendar/ews_calendar.py book --room 13-3@oe.21vianet.com --subject "Weekly Sync" --date 2026-08-06 --start 15:00 --end 17:00 --attendees "a@x.com;b@x.com"
```

Checks conflicts before booking. Sends meeting invitation to room + attendees.

### Check slot (multiple people, one time slot)

```bash
python .claude/skills/ews-calendar/ews_calendar.py check-slot --emails "a@x.com;b@x.com;c@x.com" --date 2026-08-06 --start 10:00 --end 10:30
```

Reports FREE/BUSY for each person in the given slot.

### Availability matrix (full day, 30-min slots)

```bash
python .claude/skills/ews-calendar/ews_calendar.py matrix --emails "a@x.com;b@x.com;c@x.com" --date 2026-08-06
```

Prints a time grid showing who is busy/free at each 30-minute slot, plus highlights all-free slots.

## Architecture

```
Calendar query strategy (two-tier):
  1. account.calendar.view()     → detailed events (organizer, attendees, body)
     Requires: FullAccess or Reviewer permission on target calendar
  2. GetUserAvailability fallback → free/busy + subject only
     No permission needed for room mailboxes; works for any mailbox with free/busy visibility
```

## Key Points

- **No Flask dependency** — pure CLI, no web server
- **Config fallback**: `ews_config.json` (skill dir) → `.edm_agent_config.json` (project root)
- **Timezone**: Asia/Shanghai (UTC+8)
- **Work hours**: 09:00-18:00 (configurable via WORK_START/WORK_END)
- **Book guard**: Checks conflicts before creating CalendarItem
