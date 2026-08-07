"""Calendar: meeting room booking, recurring plans, AI analysis.

API endpoints under /api/calendar/*
"""
import datetime as dt
import json
import logging
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from flask import Blueprint, jsonify, g, request

from utils import task_queue
from routes.auth import require_auth, DOMAIN_NAME

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

_CONFIG_FILE = Path(PROJECT_ROOT) / ".edm_agent_config.json"
if not _CONFIG_FILE.exists():
    _CONFIG_FILE = Path(PROJECT_ROOT) / ".claude" / "skills" / "ews-calendar" / "ews_config.json"

TIMEZONE_NAME = "Asia/Shanghai"
WORK_START = 9
WORK_END = 18

# ─── Default Meeting Rooms ────────────────────────────────────────

_DEFAULT_ROOMS = [
    {"email": "13-1@oe.21vianet.com", "name": "13-1", "description": "大会议室，能容纳12人", "capacity": 12},
    {"email": "13-3@oe.21vianet.com", "name": "13-3", "description": "每周 Azure Manager Sync Meeting", "capacity": 0},
    {"email": "13-4@oe.21vianet.com", "name": "13-4", "description": "PS Team 每周 Free Talk", "capacity": 0},
]

# ─── Blueprint ────────────────────────────────────────────────────

calendar_bp = Blueprint('calendar', __name__, url_prefix='/api/calendar')


# ─── EWS Helpers ──────────────────────────────────────────────────

def _load_ews_config():
    if not _CONFIG_FILE.exists():
        raise FileNotFoundError(f"EWS config not found: {_CONFIG_FILE}")
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# EWS URL comes from config file
_EWS_URL = None

def _get_ews_url():
    """Lazy-load EWS URL from config file."""
    global _EWS_URL
    if _EWS_URL is None:
        cfg = _load_ews_config()
        _EWS_URL = cfg["ews"]["url"]
    return _EWS_URL


def _get_user_creds():
    """Get current user's domain credentials for EWS.
    Returns (domain_user, password)."""
    user = getattr(g, 'current_user', None) or {}
    username = user.get('username', '')
    password = user.get('password')
    domain = user.get('domain', DOMAIN_NAME)
    if not username or not password:
        raise ValueError("用户凭据不可用，请重新登录")
    return f"{domain}\\{username}", password


def _ews_credentials(domain_user, password):
    from exchangelib import Credentials
    return Credentials(username=domain_user, password=password)


def _ews_configuration(domain_user, password):
    from exchangelib import Configuration
    return Configuration(service_endpoint=_get_ews_url(), credentials=_ews_credentials(domain_user, password))


def _ews_ews_account(primary_smtp, domain_user, password):
    from exchangelib import Account, DELEGATE
    return Account(
        primary_smtp_address=primary_smtp,
        config=_ews_configuration(domain_user, password),
        autodiscover=False,
        access_type=DELEGATE,
    )


def _ews_service_account():
    """Create EWS Account for the logged-in domain user."""
    domain_user, password = _get_user_creds()
    username = domain_user.split('\\')[-1]
    return _ews_ews_account(
        f"{username}@oe.21vianet.com", domain_user, password)


def _ews_room_account(room_email):
    """Create EWS Account for a meeting room, authenticated as logged-in user."""
    domain_user, password = _get_user_creds()
    return _ews_ews_account(room_email, domain_user, password)


def _ews_datetime(year, month, day, hour, minute):
    from exchangelib import EWSDateTime, EWSTimeZone
    tz = EWSTimeZone(TIMEZONE_NAME)
    return EWSDateTime(year, month, day, hour, minute, tzinfo=tz)


def _ews_timezone():
    from exchangelib import EWSTimeZone
    return EWSTimeZone(TIMEZONE_NAME)


def _ews_to_local_naive(value):
    local_value = value.astimezone(_ews_timezone())
    return dt.datetime(
        local_value.year, local_value.month, local_value.day,
        local_value.hour, local_value.minute, local_value.second,
    )


def _ews_mailbox_label(mailbox):
    if not mailbox:
        return ""
    name = getattr(mailbox, "name", "") or ""
    email = getattr(mailbox, "email_address", "") or ""
    return name or email


def _ews_attendee_labels(attendees):
    if not attendees:
        return []
    labels = []
    for att in attendees:
        mb = getattr(att, "mailbox", att)
        label = _ews_mailbox_label(mb)
        if label:
            labels.append(label)
    return labels


def _read_calendar_events(email, start, end=None):
    """Try calendar.view() first, fallback to GetUserAvailability.

    If *end* is None, queries a single day (start + 1 day).
    If *end* is provided, queries the full range [start, end).
    """
    if end is None:
        end = start + timedelta(days=1)

    try:
        account = _ews_room_account(email)
        view_start = _ews_datetime(start.year, start.month, start.day, 0, 0)
        view_end = _ews_datetime(end.year, end.month, end.day, 0, 0)
        events = []
        for item in account.calendar.view(start=view_start, end=view_end):
            start_dt = _ews_to_local_naive(item.start)
            end_dt = _ews_to_local_naive(item.end)
            organizer = ""
            organizer_email = ""
            org = getattr(item, "organizer", None)
            if org:
                organizer = _ews_mailbox_label(org)
                org_email = getattr(org, "email_address", "")
                if org_email:
                    organizer_email = org_email
            events.append({
                "subject": item.subject or "Busy",
                "start": start_dt, "end": end_dt,
                "organizer": organizer,
                "organizer_email": organizer_email,
            })
        return sorted(events, key=lambda e: e["start"]), "calendar"
    except Exception as exc:
        cal_err = str(exc)
        try:
            return _read_freebusy_events(email, start, end=end), "freebusy"
        except Exception as fb_exc:
            raise RuntimeError(
                f"Both calendar and FreeBusy failed for {email}. "
                f"Calendar: {cal_err} | FreeBusy: {fb_exc}"
            ) from fb_exc


def _read_freebusy_events(email, start, end=None):
    """GetUserAvailability FreeBusy query."""
    if end is None:
        end = start + timedelta(days=1)
    from exchangelib.properties import (
        DaylightTime, Email, FreeBusyViewOptions, MailboxData,
        StandardTime, TimeWindow, TimeZone,
    )
    from exchangelib.services import GetUserAvailability

    account = _ews_service_account()
    tw_start = _ews_datetime(start.year, start.month, start.day, 0, 0)
    tw_end = _ews_datetime(end.year, end.month, end.day, 0, 0)

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
        time_window=TimeWindow(start=tw_start, end=tw_end),
        merged_free_busy_interval=10,
        requested_view="DetailedMerged",
    )

    views = list(GetUserAvailability(protocol=account.protocol).call(
        tzinfo=_ews_timezone(), mailbox_data=mailbox_data,
        timezone=timezone, free_busy_view_options=options))
    if not views:
        return []

    events = []
    for item in views[0].calendar_events or []:
        busy_type = str(getattr(item, "busy_type", "") or "")
        if busy_type.lower() in {"free", "unknown"}:
            continue
        start = _ews_to_local_naive(item.start)
        end = _ews_to_local_naive(item.end)
        details = getattr(item, "details", None)
        subject = getattr(details, "subject", "") if details else busy_type or "Busy"
        events.append({
            "subject": subject, "start": start, "end": end,
            "organizer": "",
            "organizer_email": "",
        })
    return sorted(events, key=lambda e: e["start"])


def _conflicting_events(events, start, end):
    return [e for e in events if e["start"] < end and e["end"] > start]


def _compute_time_grid(events, day):
    """Compute a 30-minute time grid from 09:00 to 18:00.
    Each slot shows whether it's free or busy (with busy subject).
    """
    slots = []
    cursor = day.replace(hour=WORK_START, minute=0, second=0)
    end_of_day = day.replace(hour=WORK_END, minute=0, second=0)

    while cursor < end_of_day:
        slot_end = cursor + timedelta(minutes=30)
        # Check if any busy event overlaps this slot
        busy_event = None
        for e in events:
            if e["start"] < slot_end and e["end"] > cursor:
                busy_event = e
                break

        status = "busy" if busy_event else "free"
        subject = busy_event["subject"] if busy_event else ""
        slots.append({
            "time": cursor.strftime("%H:%M"),
            "end": slot_end.strftime("%H:%M"),
            "status": status,
            "subject": subject,
        })
        cursor = slot_end
    return slots


def _compute_free_slots(events, day):
    """Compute free slots during work hours (for booking suggestions)."""
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


def _parse_attendees(value):
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[;,\n]", str(value))
    return [str(item).strip() for item in candidates if str(item).strip()]


def _init_default_rooms():
    """Seed default rooms if table is empty."""
    rooms = task_queue.get_meeting_rooms()
    if not rooms:
        for room in _DEFAULT_ROOMS:
            task_queue.upsert_meeting_room(
                email=room["email"], name=room["name"],
                description=room["description"], capacity=room.get("capacity", 0))
        logger.info("[calendar] Initialized default meeting rooms")


# ─── API Endpoints ────────────────────────────────────────────────

@calendar_bp.route('/rooms', methods=['GET'])
@require_auth
def api_rooms():
    """GET /api/calendar/rooms — List meeting rooms."""
    _init_default_rooms()
    rooms = task_queue.get_meeting_rooms()
    return jsonify({"ok": True, "rooms": rooms})


@calendar_bp.route('/freebusy', methods=['POST'])
@require_auth
def api_freebusy():
    """POST /api/calendar/freebusy — Query free/busy for a room on a given day.

    Body: { "room_email": "13-3@...", "date": "2026-08-06" }
    """
    data = request.get_json(force=True)
    room_email = data.get("room_email", "")
    date_str = data.get("date", dt.date.today().isoformat())
    if not room_email or not date_str:
        return jsonify({"ok": False, "error": "room_email and date are required"}), 400

    try:
        day = dt.datetime.strptime(date_str, "%Y-%m-%d")
        events, source = _read_calendar_events(room_email, day)

        # Build a 30-min time grid
        time_grid = _compute_time_grid(events, day)

        # Also compute continuous free blocks for suggestions
        free_slots = _compute_free_slots(events, day)
        free_blocks = []
        for s, e in free_slots:
            mins = int((e - s).total_seconds() // 60)
            free_blocks.append({
                "start": s.strftime("%H:%M"),
                "end": e.strftime("%H:%M"),
                "minutes": mins,
            })

        return jsonify({
            "ok": True, "source": source,
            "room_email": room_email, "date": date_str,
            "time_grid": time_grid, "free_blocks": free_blocks,
        })
    except Exception as exc:
        logger.exception("freebusy error")
        return jsonify({"ok": False, "error": str(exc)}), 500


@calendar_bp.route('/book', methods=['POST'])
@require_auth
def api_book():
    """POST /api/calendar/book — Book a meeting room.

    Body: {
        "room_email": "13-3@...",
        "subject": "Weekly Sync",
        "date": "2026-08-06",
        "start_time": "15:00",
        "end_time": "17:00",
        "attendees": "a@x.com;b@x.com"
    }
    """
    data = request.get_json(force=True)
    room_email = data.get("room_email", "")
    subject = data.get("subject", "")
    date_str = data.get("date", "")
    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")
    attendees_str = data.get("attendees", "")

    if not all([room_email, subject, date_str, start_time, end_time]):
        return jsonify({"ok": False, "error": "room_email, subject, date, start_time, end_time are required"}), 400

    try:
        date = dt.datetime.strptime(date_str, "%Y-%m-%d")
        sh, sm = map(int, start_time.split(":"))
        eh, em = map(int, end_time.split(":"))

        start_dt = date.replace(hour=sh, minute=sm)
        end_dt = date.replace(hour=eh, minute=em)

        if end_dt <= start_dt:
            return jsonify({"ok": False, "error": "end_time must be after start_time"}), 400

        attendees = _parse_attendees(attendees_str) if attendees_str else []

        # Check conflicts
        events, _ = _read_calendar_events(room_email, date)
        conflicts = _conflicting_events(events, start_dt, end_dt)

        if conflicts:
            # Compute suggested free slots
            free_slots = _compute_free_slots(events, date)
            suggestions = []
            for s, e in free_slots:
                mins = int((e - end_dt).total_seconds() // 60)
                if mins >= (end_dt - start_dt).total_seconds() // 60:
                    suggestions.append({
                        "start": s.strftime("%H:%M"),
                        "end": (s + (end_dt - start_dt)).strftime("%H:%M"),
                        "minutes": int((e - s).total_seconds() // 60),
                    })

            task_queue.save_booking(
                room_email=room_email, subject=subject, date=date_str,
                start_time=start_time, end_time=end_time,
                attendees=";".join(attendees), source="manual", status="conflict")

            return jsonify({
                "ok": False,
                "error": f"时间冲突: {conflicts[0]['subject']} ({conflicts[0]['start'].strftime('%H:%M')}-{conflicts[0]['end'].strftime('%H:%M')})",
                "conflicts": [{"subject": c["subject"],
                               "start": c["start"].strftime("%H:%M"),
                               "end": c["end"].strftime("%H:%M")} for c in conflicts],
                "suggestions": suggestions,
            })

        # No conflict — book it!
        account = _ews_service_account()
        from exchangelib import CalendarItem, Mailbox
        from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY
        from exchangelib.properties import Attendee

        item = CalendarItem(
            account=account,
            folder=account.calendar,
            subject=subject,
            start=_ews_datetime(date.year, date.month, date.day, sh, sm),
            end=_ews_datetime(date.year, date.month, date.day, eh, em),
            body="",
            location=room_email,
            required_attendees=[
                Attendee(mailbox=Mailbox(email_address=e)) for e in attendees
            ],
            resources=[Attendee(mailbox=Mailbox(email_address=room_email))],
        )
        item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)

        task_queue.save_booking(
            room_email=room_email, subject=subject, date=date_str,
            start_time=start_time, end_time=end_time,
            attendees=";".join(attendees), source="manual", status="booked")
        task_queue.save_activity(
            category="calendar",
            title=f"预定会议室 {room_email.split('@')[0]}",
            detail=f"{subject} @ {date_str} {start_time}-{end_time}",
            status="ok")

        return jsonify({
            "ok": True,
            "message": f"会议预定成功: {subject} @ {room_email.split('@')[0]} {date_str} {start_time}-{end_time}",
        })
    except Exception as exc:
        logger.exception("book error")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Recurring Plans ──────────────────────────────────────────────

@calendar_bp.route('/plan/create', methods=['POST'])
@require_auth
def api_plan_create():
    """POST /api/calendar/plan/create — Create a recurring plan.

    Body: { "name": "Azure Manager Sync", "room_email": "13-3@...",
            "subject": "Azure Manager Sync Meeting",
            "day_of_week": 4, "start_time": "15:00", "end_time": "17:00" }
    """
    data = request.get_json(force=True)
    name = data.get("name", "")
    room_email = data.get("room_email", "")
    subject = data.get("subject", "")
    day_of_week = int(data.get("day_of_week", 1))
    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")

    if not all([name, room_email, subject, start_time, end_time]):
        return jsonify({"ok": False, "error": "All fields required"}), 400

    plan_id = task_queue.create_recurring_plan(
        name=name, room_email=room_email, subject=subject,
        day_of_week=day_of_week, start_time=start_time, end_time=end_time)

    task_queue.save_activity(
        category="calendar", title=f"创建重复计划: {name}",
        detail=f"{room_email.split('@')[0]} 每周{'一二三四五六日'[day_of_week-1]} {start_time}-{end_time}",
        status="ok")

    return jsonify({"ok": True, "plan_id": plan_id, "message": "计划创建成功"})


@calendar_bp.route('/plan/list', methods=['GET'])
@require_auth
def api_plan_list():
    """GET /api/calendar/plan/list — List all recurring plans."""
    plans = task_queue.list_recurring_plans()
    return jsonify({"ok": True, "plans": plans})


@calendar_bp.route('/plan/toggle', methods=['POST'])
@require_auth
def api_plan_toggle():
    """POST /api/calendar/plan/toggle — Enable/disable a plan.

    Body: { "plan_id": 1, "enabled": 0 }
    """
    data = request.get_json(force=True)
    plan_id = int(data.get("plan_id"))
    enabled = int(data.get("enabled", 1))
    task_queue.toggle_recurring_plan(plan_id, enabled)
    return jsonify({"ok": True})


@calendar_bp.route('/plan/update', methods=['POST'])
@require_auth
def api_plan_update():
    """POST /api/calendar/plan/update — Update a recurring plan.

    Body: { "plan_id": 1, "name": "...", "room_email": "...", "subject": "...",
            "day_of_week": 4, "start_time": "15:00", "end_time": "17:00" }
    """
    data = request.get_json(force=True)
    plan_id = int(data.get("plan_id"))
    task_queue.update_recurring_plan(
        plan_id=plan_id,
        name=data.get("name"),
        room_email=data.get("room_email"),
        subject=data.get("subject"),
        day_of_week=int(data["day_of_week"]) if data.get("day_of_week") is not None else None,
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        max_days_ahead=int(data["max_days_ahead"]) if data.get("max_days_ahead") is not None else None)
    return jsonify({"ok": True})


@calendar_bp.route('/plan/delete', methods=['POST'])
@require_auth
def api_plan_delete():
    """POST /api/calendar/plan/delete — Delete a plan."""
    data = request.get_json(force=True)
    plan_id = int(data.get("plan_id"))
    task_queue.delete_recurring_plan(plan_id)
    return jsonify({"ok": True})


@calendar_bp.route('/plan/check', methods=['POST'])
@require_auth
def api_plan_check():
    """POST /api/calendar/plan/check — Check all enabled plans, return ALL slots with status.

    Each slot includes: date, time, status (booked/unbooked/busy),
    subject (if booked), organizer, and whether the organizer matches current user.
    Optimisation: query the entire date range once per plan instead of per-day.
    """
    plans = task_queue.list_recurring_plans()
    enabled = [p for p in plans if p.get("enabled")]

    all_slots = []
    # Validate user credentials are available
    try:
        _get_user_creds()
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 401

    current_user_email = (getattr(g, 'current_user', None) or {}).get("username", "")
    if current_user_email and "@" not in current_user_email:
        current_user_email += "@oe.21vianet.com"
    current_user_email = current_user_email.lower()
    today = dt.date.today()
    days_map = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for plan in enabled:
        dow = plan["day_of_week"]
        max_ahead = plan.get("max_days_ahead", 30)
        room_email = plan["room_email"]
        subject = plan["subject"]
        start_t = plan["start_time"]
        end_t = plan["end_time"]
        end_date = today + dt.timedelta(days=max_ahead)

        sh, sm = map(int, start_t.split(":"))
        eh, em = map(int, end_t.split(":"))

        # Collect all target dates for this plan
        target_dates = []
        current = today
        while current <= end_date:
            if current.weekday() == dow - 1:  # weekday(): Mon=0
                target_dates.append(current)
            current += dt.timedelta(days=1)

        if not target_dates:
            continue

        # Single EWS call covering the full range for this plan
        try:
            range_start = dt.datetime.combine(target_dates[0], dt.time())
            range_end = dt.datetime.combine(target_dates[-1], dt.time()) + dt.timedelta(days=1)
            events, _ = _read_calendar_events(room_email, range_start, end=range_end)
        except Exception as exc:
            logger.warning(f"plan_check EWS error for {room_email}: {exc}")
            # Fallback: mark all as unknown
            for day_date in target_dates:
                all_slots.append({
                    "plan_id": plan["id"],
                    "plan_name": plan["name"],
                    "room_email": room_email,
                    "subject": subject,
                    "date": day_date.isoformat(),
                    "start_time": start_t,
                    "end_time": end_t,
                    "day_name": days_map[dow - 1],
                    "status": "unknown",
                    "busy_subject": "",
                    "organizer": "",
                    "is_user": False,
                })
            continue

        # Check each target date against the events loaded in memory
        for day_date in target_dates:
            day_dt = dt.datetime.combine(day_date, dt.time())
            slot_start = day_dt.replace(hour=sh, minute=sm)
            slot_end = day_dt.replace(hour=eh, minute=em)
            conflicts = _conflicting_events(events, slot_start, slot_end)

            if conflicts:
                conflict = conflicts[0]
                organizer = conflict.get("organizer", "")
                organizer_email = (conflict.get("organizer_email", "") or "").lower()
                is_user = organizer_email == current_user_email if current_user_email else False
                all_slots.append({
                    "plan_id": plan["id"],
                    "plan_name": plan["name"],
                    "room_email": room_email,
                    "subject": subject,
                    "date": day_date.isoformat(),
                    "start_time": start_t,
                    "end_time": end_t,
                    "day_name": days_map[dow - 1],
                    "status": "booked" if is_user else "busy",
                    "busy_subject": conflict["subject"],
                    "busy_start": conflict["start"].strftime("%H:%M"),
                    "busy_end": conflict["end"].strftime("%H:%M"),
                    "organizer": organizer,
                    "is_user": is_user,
                })
            else:
                all_slots.append({
                    "plan_id": plan["id"],
                    "plan_name": plan["name"],
                    "room_email": room_email,
                    "subject": subject,
                    "date": day_date.isoformat(),
                    "start_time": start_t,
                    "end_time": end_t,
                    "day_name": days_map[dow - 1],
                    "status": "unbooked",
                    "busy_subject": "",
                    "organizer": "",
                    "is_user": False,
                })

    return jsonify({"ok": True, "slots": all_slots})


@calendar_bp.route('/plan/book-all', methods=['POST'])
@require_auth
def api_plan_book_all():
    """POST /api/calendar/plan/book-all — Book all unbooked slots from plan check.

    Body: { "unbooked": [ ... list of unbooked slots from plan/check ... ] }
    """
    data = request.get_json(force=True)
    unbooked = data.get("unbooked", [])
    if not unbooked:
        return jsonify({"ok": True, "message": "没有需要预定的时段", "booked": 0})

    results = []
    for slot in unbooked:
        try:
            date = dt.datetime.strptime(slot["date"], "%Y-%m-%d")
            sh, sm = map(int, slot["start_time"].split(":"))
            eh, em = map(int, slot["end_time"].split(":"))
            start_dt = date.replace(hour=sh, minute=sm)
            end_dt = date.replace(hour=eh, minute=em)

            events, _ = _read_calendar_events(slot["room_email"], date)
            conflicts = _conflicting_events(events, start_dt, end_dt)

            if conflicts:
                results.append({"date": slot["date"], "ok": False, "error": "冲突"})
                continue

            account = _ews_service_account()
            from exchangelib import CalendarItem, Mailbox
            from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY
            from exchangelib.properties import Attendee

            item = CalendarItem(
                account=account, folder=account.calendar,
                subject=slot["subject"],
                start=_ews_datetime(date.year, date.month, date.day, sh, sm),
                end=_ews_datetime(date.year, date.month, date.day, eh, em),
                body="", location=slot["room_email"],
                resources=[Attendee(mailbox=Mailbox(email_address=slot["room_email"]))],
            )
            item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)

            task_queue.save_booking(
                room_email=slot["room_email"], subject=slot["subject"],
                date=slot["date"], start_time=slot["start_time"], end_time=slot["end_time"],
                source="recurring", plan_id=slot.get("plan_id"), status="booked")

            results.append({"date": slot["date"], "ok": True})
        except Exception as exc:
            logger.exception(f"plan_book_all error for {slot.get('date')}")
            results.append({"date": slot["date"], "ok": False, "error": str(exc)})

    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count

    task_queue.save_activity(
        category="calendar",
        title=f"重复计划批量预定",
        detail=f"成功 {ok_count} 个, 失败 {fail_count} 个",
        status="ok" if fail_count == 0 else "warn")

    return jsonify({"ok": True, "results": results, "booked": ok_count, "failed": fail_count})


# ─── Booking History ──────────────────────────────────────────────

@calendar_bp.route('/history', methods=['GET'])
@require_auth
def api_history():
    """GET /api/calendar/history?page=1&size=30&source=manual — List bookings."""
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 30, type=int)
    source = request.args.get('source', None)

    result = task_queue.list_bookings(page=page, page_size=size, source=source)
    return jsonify({"ok": True, **result})


@calendar_bp.route('/upcoming', methods=['GET'])
@require_auth
def api_upcoming():
    """GET /api/calendar/upcoming?days=7 — Upcoming bookings."""
    days = request.args.get('days', 7, type=int)
    bookings = task_queue.get_upcoming_bookings(days=days)
    return jsonify({"ok": True, "bookings": bookings})


# ─── AI Analysis ──────────────────────────────────────────────────

@calendar_bp.route('/ai/analyze', methods=['POST'])
@require_auth
def api_ai_analyze():
    """POST /api/calendar/ai/analyze — AI analyzes booking habits, returns suggestions."""
    stats = task_queue.get_booking_stats()
    history = task_queue.list_bookings(page=1, page_size=50)

    if stats["total"] < 2:
        return jsonify({
            "ok": True,
            "suggestions": [],
            "message": "预定记录不足，AI 无法分析（至少需要2条记录）"
        })

    try:
        llm_cfg_path = Path(BASE_DIR) / ".edm_agent_llm_config.json"
        if not llm_cfg_path.exists():
            return jsonify({"ok": False, "error": "AI Model 未配置，请先在设置中配置"}), 400

        with open(llm_cfg_path, "r", encoding="utf-8") as f:
            llm_cfg = json.load(f)

        import litellm
        litellm.drop_params = True

        room_names = {}
        for r in task_queue.get_meeting_rooms():
            room_names[r["email"]] = r["name"]

        history_summary = []
        for b in history["data"][:20]:
            rn = room_names.get(b["room_email"], b["room_email"].split("@")[0])
            history_summary.append(
                f"{b['date']} {b['start_time']}-{b['end_time']} | {rn} | {b['subject']} | {b['source']}")

        prompt = f"""你是一个会议室预定助手。根据以下预定历史，分析用户习惯并给出1-3条预定建议。

预定历史：
{chr(10).join(history_summary)}

统计：
- 总预定数: {stats['total']}
- 常用会议室: {', '.join(f"{room_names.get(r['room_email'], r['room_email'])}({r['cnt']}次)" for r in stats['rooms'][:3])}
- 常用时间段: {', '.join(f"{t['start_time']}({t['cnt']}次)" for t in stats['times'][:3])}

请以 JSON 数组格式回复，每条建议包含:
- suggestion: 建议内容（中文，简短）
- reason: 为什么给这个建议（中文）
- room_email: 建议的会议室邮箱（如果有）
- date: 建议的日期 YYYY-MM-DD（如果有）
- start_time: 建议开始时间 HH:MM（如果有）
- end_time: 建议结束时间 HH:MM（如果有）
- subject: 建议的会议标题（如果有）

只返回 JSON 数组，不要其他文字。"""

        response = litellm.completion(
            model=llm_cfg.get("model", "openai/gpt-3.5-turbo"),
            messages=[{"role": "user", "content": prompt}],
            api_base=llm_cfg.get("api_base"),
            api_key=llm_cfg.get("api_key"),
            temperature=0.3,
            timeout=llm_cfg.get("timeout", 30),
        )

        ai_text = response.choices[0].message.content.strip()

        # Extract JSON from possible markdown code block
        json_match = re.search(r'\[(.*?)\]', ai_text, re.DOTALL)
        if json_match:
            ai_text = '[' + json_match.group(1) + ']'

        suggestions = json.loads(ai_text)
        if not isinstance(suggestions, list):
            suggestions = [suggestions]

        # Save suggestions to DB
        for s in suggestions:
            suggestion_text = s.get("suggestion", "")
            reason = s.get("reason", "")
            if suggestion_text:
                task_queue.save_ai_suggestion(suggestion_text, reason)

        return jsonify({"ok": True, "suggestions": suggestions})

    except Exception as exc:
        logger.exception("ai_analyze error")
        return jsonify({"ok": False, "error": str(exc)}), 500


@calendar_bp.route('/ai/suggestions', methods=['GET'])
@require_auth
def api_ai_suggestions():
    """GET /api/calendar/ai/suggestions — List AI suggestions."""
    suggestions = task_queue.list_ai_suggestions()
    return jsonify({"ok": True, "suggestions": suggestions})


@calendar_bp.route('/ai/respond', methods=['POST'])
@require_auth
def api_ai_respond():
    """POST /api/calendar/ai/respond — Accept or ignore an AI suggestion.

    Body: { "suggestion_id": 1, "action": "accepted" }
    """
    data = request.get_json(force=True)
    suggestion_id = int(data.get("suggestion_id"))
    action = data.get("action", "ignored")

    task_queue.respond_ai_suggestion(suggestion_id, action)

    if action == "accepted":
        # Get the suggestion details
        suggestions = task_queue.list_ai_suggestions()
        s = next((x for x in suggestions if x["id"] == suggestion_id), None)
        if s:
            task_queue.save_activity(
                category="calendar",
                title="接受 AI 建议",
                detail=s.get("suggestion", ""),
                status="ok")

    return jsonify({"ok": True})
