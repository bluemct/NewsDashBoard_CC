"""EWS Calendar: query room/calendar availability and book meeting rooms.

Usage:
    python .claude/skills/ews-calendar/ews_calendar.py query --email <email> [--date YYYY-MM-DD]
    python .claude/skills/ews-calendar/ews_calendar.py book --room <room_email> --subject <s> --date YYYY-MM-DD --start HH:MM --end HH:MM [--attendees e1;e2] [--body text]
    python .claude/skills/ews-calendar/ews_calendar.py check-slot --emails e1;e2;... --date YYYY-MM-DD --start HH:MM --end HH:MM
    python .claude/skills/ews-calendar/ews_calendar.py matrix --emails e1;e2;... --date YYYY-MM-DD
"""

import argparse
import datetime as dt
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
CONFIG_FILE = Path(__file__).parent / "ews_config.json"
if not CONFIG_FILE.exists():
    # Fallback to project root config
    CONFIG_FILE = Path(__file__).parent.parent.parent / ".edm_agent_config.json"

TIMEZONE_NAME = "Asia/Shanghai"
TIMEZONE_OFFSET_HOURS = 8
WORK_START = 9
WORK_END = 18

# ---------------------------------------------------------------------------

def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def ews_credentials(cfg):
    from exchangelib import Credentials
    return Credentials(
        username=cfg["ews"]["domain_user"],
        password=cfg["ews"]["password"],
    )


def ews_configuration(cfg):
    from exchangelib import Configuration
    return Configuration(
        service_endpoint=cfg["ews"]["url"],
        credentials=ews_credentials(cfg),
    )


def ews_service_account(cfg):
    from exchangelib import Account, DELEGATE
    return Account(
        primary_smtp_address=cfg["ews"]["mailbox"],
        config=ews_configuration(cfg),
        autodiscover=False,
        access_type=DELEGATE,
    )


def ews_room_account(room_email, cfg):
    from exchangelib import Account, DELEGATE
    return Account(
        primary_smtp_address=room_email,
        config=ews_configuration(cfg),
        autodiscover=False,
        access_type=DELEGATE,
    )


def ews_datetime(year, month, day, hour, minute):
    from exchangelib import EWSDateTime, EWSTimeZone
    tz = EWSTimeZone(TIMEZONE_NAME)
    return EWSDateTime(year, month, day, hour, minute, tzinfo=tz)


def ews_timezone():
    from exchangelib import EWSTimeZone
    return EWSTimeZone(TIMEZONE_NAME)


def ews_to_local_naive(value):
    local_value = value.astimezone(ews_timezone())
    return dt.datetime(
        local_value.year, local_value.month, local_value.day,
        local_value.hour, local_value.minute, local_value.second,
    )


def ews_mailbox_label(mailbox):
    if not mailbox:
        return ""
    name = getattr(mailbox, "name", "") or ""
    email = getattr(mailbox, "email_address", "") or ""
    return name or email


def ews_attendee_labels(attendees):
    if not attendees:
        return []
    labels = []
    for att in attendees:
        mb = getattr(att, "mailbox", att)
        label = ews_mailbox_label(mb)
        if label:
            labels.append(label)
    return labels


def ews_body_preview(body):
    text = str(body or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())[:200]


def now_utc8_naive():
    return dt.datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET_HOURS)


# ---------------------------------------------------------------------------
# Query: calendar first, fallback to FreeBusy
# ---------------------------------------------------------------------------

def read_room_calendar_events(email, day, cfg):
    """Try to read calendar directly (needs permission)."""
    account = ews_room_account(email, cfg)
    day_start = ews_datetime(day.year, day.month, day.day, 0, 0)
    day_end = day_start + timedelta(days=1)

    events = []
    for item in account.calendar.view(start=day_start, end=day_end):
        start = ews_to_local_naive(item.start)
        end = ews_to_local_naive(item.end)
        events.append({
            "subject": item.subject or "Busy",
            "start": start, "end": end,
            "organizer": ews_mailbox_label(getattr(item, "organizer", None)),
            "required_attendees": ews_attendee_labels(getattr(item, "required_attendees", None)),
            "body_preview": ews_body_preview(getattr(item, "body", "")),
            "location": getattr(item, "location", "") or "",
            "source": "calendar",
        })
    return sorted(events, key=lambda e: e["start"])


def read_room_freebusy_events(email, day, cfg):
    """Fallback: GetUserAvailability (no permission needed for rooms)."""
    from exchangelib.properties import (
        DaylightTime, Email, FreeBusyViewOptions, MailboxData,
        StandardTime, TimeWindow, TimeZone,
    )
    from exchangelib.services import GetUserAvailability

    account = ews_service_account(cfg)
    day_start = ews_datetime(day.year, day.month, day.day, 0, 0)
    day_end = day_start + timedelta(days=1)

    mailbox_data = [MailboxData(
        email=Email(email_address=email),
        attendee_type="Required",
        exclude_conflicts=False,
    )]
    timezone = TimeZone(
        bias=-480,
        standard_time=StandardTime(bias=0, time=dt.time(0, 0),
                                    occurrence=1, iso_month=1, weekday="Sunday"),
        daylight_time=DaylightTime(bias=0, time=dt.time(0, 0),
                                    occurrence=1, iso_month=1, weekday="Sunday"),
    )
    options = FreeBusyViewOptions(
        time_window=TimeWindow(start=day_start, end=day_end),
        merged_free_busy_interval=10,
        requested_view="DetailedMerged",
    )

    views = list(GetUserAvailability(protocol=account.protocol).call(
        tzinfo=ews_timezone(), mailbox_data=mailbox_data,
        timezone=timezone, free_busy_view_options=options))
    if not views:
        return []

    events = []
    for item in views[0].calendar_events or []:
        busy_type = str(getattr(item, "busy_type", "") or "")
        if busy_type.lower() in {"free", "unknown"}:
            continue
        start = ews_to_local_naive(item.start)
        end   = ews_to_local_naive(item.end)
        details = getattr(item, "details", None)
        subject = getattr(details, "subject", "") if details else busy_type or "Busy"
        location = getattr(details, "location", "") if details else ""
        events.append({
            "subject": subject, "start": start, "end": end,
            "organizer": "", "required_attendees": [], "body_preview": "",
            "location": location, "source": "freebusy",
        })
    return sorted(events, key=lambda e: e["start"])


def read_room_events(email, day, cfg):
    """Calendar first, fallback to FreeBusy."""
    try:
        events = read_room_calendar_events(email, day, cfg)
        return events, "calendar"
    except Exception as exc:
        cal_err = str(exc)
        try:
            events = read_room_freebusy_events(email, day, cfg)
            return events, "freebusy"
        except Exception as fb_exc:
            raise RuntimeError(
                f"Both calendar and FreeBusy failed for {email}. "
                f"Calendar: {cal_err} | FreeBusy: {fb_exc}"
            ) from fb_exc


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_query(args):
    cfg = load_config()
    day = dt.datetime.strptime(args.date, "%Y-%m-%d").replace(hour=0, minute=0) if args.date else dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    email = args.email

    print(f"Querying {email} for {day.strftime('%Y-%m-%d')} ...")
    events, source = read_room_events(email, day, cfg)
    print(f"[OK] Source: {source}\n")

    empty = compute_empty_slots(events, day)
    print_schedule(email, day, events, empty)


def cmd_book(args):
    cfg = load_config()
    account = ews_service_account(cfg)

    date = dt.datetime.strptime(args.date, "%Y-%m-%d")
    sh, sm = map(int, args.start.split(":"))
    eh, em = map(int, args.end.split(":"))

    start_dt = date.replace(hour=sh, minute=sm)
    end_dt   = date.replace(hour=eh, minute=em)

    if end_dt <= start_dt:
        print("Error: end time must be after start time")
        sys.exit(1)
    if start_dt.hour < WORK_START or end_dt.hour > WORK_END:
        print(f"Error: booking time must be within {WORK_START}:00-{WORK_END}:00")
        sys.exit(1)

    attendees = parse_attendee_input(args.attendees) if args.attendees else []

    # Check conflicts before booking
    room_info = {"email": args.room, "name": args.room.split("@")[0]}
    try:
        events, _ = read_room_events(args.room, date, cfg)
        conflicts = conflicting_events(events, start_dt, end_dt)
        if conflicts:
            c = conflicts[0]
            print(f"Conflict: {c['start'].strftime('%H:%M')}-{c['end'].strftime('%H:%M')} "
                  f"{c['subject']}")
            sys.exit(1)
    except Exception as exc:
        print(f"Warning: could not check conflicts: {exc}")

    from exchangelib import CalendarItem, Mailbox
    from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY
    from exchangelib.properties import Attendee

    item = CalendarItem(
        account=account,
        folder=account.calendar,
        subject=args.subject,
        start=ews_datetime(date.year, date.month, date.day, sh, sm),
        end=ews_datetime(date.year, date.month, date.day, eh, em),
        body=args.body or "",
        location=args.room,
        required_attendees=[
            Attendee(mailbox=Mailbox(email_address=e)) for e in attendees
        ],
        resources=[Attendee(mailbox=Mailbox(email_address=args.room))],
    )
    item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)

    print("=" * 50)
    print("  Meeting booked successfully!")
    print("=" * 50)
    print(f"  Subject:   {args.subject}")
    print(f"  Room:      {args.room}")
    print(f"  Date:      {args.date} {args.start} - {args.end}")
    if attendees:
        print(f"  Attendees: {len(attendees)}")
        for a in attendees:
            print(f"    - {a}")
    else:
        print("  Attendees: (room only)")
    print()


def cmd_check_slot(args):
    """Check if a list of emails are free in a given time slot."""
    cfg = load_config()
    day = dt.datetime.strptime(args.date, "%Y-%m-%d")
    emails = parse_attendee_input(args.emails)
    slot_start = day.replace(hour=int(args.start.split(":")[0]), minute=int(args.start.split(":")[1]))
    slot_end   = day.replace(hour=int(args.end.split(":")[0]), minute=int(args.end.split(":")[1]))

    today_str = day.strftime("%Y-%m-%d (%A)")
    slot_label = f"{args.start} - {args.end}"
    print(f"\nChecking: {today_str}  {slot_label}\n")

    results = []
    for email in emails:
        short = email.split("@")[0].replace(".", " ")
        try:
            _, _ = read_room_events(email, day, cfg)
            events, _ = read_room_events(email, day, cfg)
            busy = [e for e in events if e["start"] < slot_end and e["end"] > slot_start]
            if busy:
                print(f"  [BUSY] {short:<25s} <- {busy[0]['subject']}")
                results.append((email, "BUSY"))
            else:
                print(f"  [FREE] {short:<25s}")
                results.append((email, "FREE"))
        except Exception as exc:
            print(f"  [ERR ] {short:<25s} <- {exc}")
            results.append((email, "ERROR"))

    free_c = sum(1 for _, s in results if s == "FREE")
    busy_c = sum(1 for _, s in results if s == "BUSY")
    print(f"\n{free_c}/{len(results)} FREE, {busy_c}/{len(results)} BUSY")


def cmd_matrix(args):
    """Full-day availability matrix (30-min slots)."""
    cfg = load_config()
    day = dt.datetime.strptime(args.date, "%Y-%m-%d")
    emails = parse_attendee_input(args.emails)
    today_str = day.strftime("%Y-%m-%d (%A)")

    print(f"\nAvailability Matrix: {today_str} ({WORK_START}:00 - {WORK_END}:00)\n")

    slots = []
    cursor = day.replace(hour=WORK_START, minute=0)
    end_cursor = day.replace(hour=WORK_END, minute=0)
    while cursor < end_cursor:
        slots.append((cursor, cursor + timedelta(minutes=30)))
        cursor += timedelta(minutes=30)

    # Query all
    busy_map = {}
    for email in emails:
        try:
            events, _ = read_room_events(email, day, cfg)
            busy_map[email] = [(e["start"], e["end"], e["subject"]) for e in events]
        except Exception as exc:
            print(f"  [ERR] {email}: {exc}")
            busy_map[email] = []

    def slot_status(email, s, e):
        for bs, be, subj in busy_map.get(email, []):
            if bs < e and be > s:
                return "Busy", subj
        return "Free", ""

    # Print matrix
    name_width = max(len(e.split("@")[0].replace(".", " ")) for e in emails)
    name_width = max(name_width, 10)

    header = f"{'Time':<10s}"
    for email in emails:
        short = email.split("@")[0].replace(".", " ")
        header += f" | {short:^{name_width}s}"
    print(header)
    print("-" * len(header))

    for s, e in slots:
        time_label = f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
        row = f"{time_label:<10s}"
        for email in emails:
            bt, subj = slot_status(email, s, e)
            if bt == "Free":
                row += f" | {'Free':^{name_width}s}"
            else:
                short_subj = subj[:name_width] if len(subj) > name_width else subj
                row += f" | {'*' + short_subj:^{name_width}s}"
        print(row)

    # All-free slots
    print("\nAll-free slots:")
    all_free = []
    for s, e in slots:
        if all(slot_status(email, s, e)[0] == "Free" for email in emails):
            all_free.append(f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}")

    if all_free:
        for slot in all_free:
            print(f"  {slot}")
    else:
        print("  (none)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_empty_slots(events, day):
    ws = day.replace(hour=WORK_START, minute=0, second=0)
    we = day.replace(hour=WORK_END, minute=0, second=0)
    busy = sorted([
        {"start": max(e["start"], ws), "end": min(e["end"], we)}
        for e in events if e["end"] > ws and e["start"] < we
    ], key=lambda b: b["start"])

    slots = []
    cursor = ws
    for block in busy:
        if block["start"] > cursor:
            slots.append((cursor, block["start"]))
        cursor = max(cursor, block["end"])
    if cursor < we:
        slots.append((cursor, we))
    return slots


def print_schedule(email, day, events, empty_slots):
    today_str = day.strftime("%Y-%m-%d (%A)")
    print("=" * 60)
    print(f"  {email}")
    print(f"  Date: {today_str}")
    print(f"  Work: {WORK_START}:00 - {WORK_END}:00")
    print("=" * 60)

    print("\n[Busy]:")
    busy_in_work = [e for e in events
                    if e["end"] > day.replace(hour=WORK_START) and e["start"] < day.replace(hour=WORK_END)]
    if not busy_in_work:
        print("  (none)")
    else:
        for e in busy_in_work:
            print(f"  {e['start'].strftime('%H:%M')}-{e['end'].strftime('%H:%M')}  "
                  f"{e['subject']}  [{e.get('source', '')}]")

    print("\n[Free]:")
    if not empty_slots:
        print("  (fully booked)")
    else:
        for s, e in empty_slots:
            mins = int((e - s).total_seconds() // 60)
            print(f"  {s.strftime('%H:%M')}-{e.strftime('%H:%M')}  ({mins} min)")

    total_free = sum(int((e - s).total_seconds() // 60) for s, e in empty_slots)
    total_work = (WORK_END - WORK_START) * 60
    print(f"\n  Free: {total_free}/{total_work} min ({total_free/total_work*100:.0f}%)\n")


def conflicting_events(events, start, end):
    conflicts = []
    for e in events:
        if e["start"] < end and e["end"] > start:
            conflicts.append(e)
    return conflicts


def parse_attendee_input(value):
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[;,\n]", str(value))
    return [str(item).strip() for item in candidates if str(item).strip()]


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="EWS Calendar: query & book")
    sub = parser.add_subparsers(dest="command")

    # query
    pq = sub.add_parser("query", help="Query calendar for one email")
    pq.add_argument("--email", required=True)
    pq.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")

    # book
    pb = sub.add_parser("book", help="Book a meeting room")
    pb.add_argument("--room", required=True, help="Room email")
    pb.add_argument("--subject", required=True)
    pb.add_argument("--date", required=True, help="YYYY-MM-DD")
    pb.add_argument("--start", required=True, help="HH:MM")
    pb.add_argument("--end", required=True, help="HH:MM")
    pb.add_argument("--attendees", default=None, help="Email list separated by ;")
    pb.add_argument("--body", default="")

    # check-slot
    ps = sub.add_parser("check-slot", help="Check time slot for multiple people")
    ps.add_argument("--emails", required=True, help="Emails separated by ;")
    ps.add_argument("--date", required=True, help="YYYY-MM-DD")
    ps.add_argument("--start", required=True, help="HH:MM")
    ps.add_argument("--end", required=True, help="HH:MM")

    # matrix
    pm = sub.add_parser("matrix", help="Full-day availability matrix")
    pm.add_argument("--emails", required=True, help="Emails separated by ;")
    pm.add_argument("--date", required=True, help="YYYY-MM-DD")

    args = parser.parse_args()
    if args.command == "query":
        cmd_query(args)
    elif args.command == "book":
        cmd_book(args)
    elif args.command == "check-slot":
        cmd_check_slot(args)
    elif args.command == "matrix":
        cmd_matrix(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
