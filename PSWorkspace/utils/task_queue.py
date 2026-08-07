"""Async task queue for long-running operations — SQLite-backed."""
import sqlite3
import uuid
import threading
import time
import logging
import os
from typing import Dict, Any, Callable, Iterator
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_db_path: str | None = None


def init(db_path: str):
    """Initialize the task queue database. Call once at app startup.

    Args:
        db_path: Absolute path to the SQLite file.
    """
    global _db_path
    _db_path = db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with _lock:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id   TEXT PRIMARY KEY,
                status    TEXT NOT NULL DEFAULT 'running',
                name      TEXT NOT NULL DEFAULT '',
                stdout    TEXT NOT NULL DEFAULT '',
                stderr    TEXT NOT NULL DEFAULT '',
                returncode INTEGER,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edm_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'info',
                message    TEXT NOT NULL DEFAULT '',
                subject    TEXT NOT NULL DEFAULT '',
                from_addr  TEXT NOT NULL DEFAULT '',
                sn         TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS icm_token_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                action          TEXT NOT NULL,
                success         INTEGER NOT NULL,
                got_new_token   TEXT,
                token_obtained_at TEXT,
                token_expires_at  TEXT,
                remaining_min   REAL,
                error_message   TEXT NOT NULL DEFAULT '',
                detail          TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL
            )
        """)
        # Migration: add cookie columns if not present
        try:
            conn.execute("ALTER TABLE icm_token_history ADD COLUMN cookie_updated TEXT")
            conn.execute("ALTER TABLE icm_token_history ADD COLUMN cookie_expires_at TEXT")
            conn.commit()
        except Exception:
            pass  # columns already exist

        # Activity log table — unified activity feed across all modules
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                category   TEXT NOT NULL DEFAULT '',
                title      TEXT NOT NULL DEFAULT '',
                detail     TEXT NOT NULL DEFAULT '',
                status     TEXT NOT NULL DEFAULT 'ok',
                created_at REAL NOT NULL
            )
        """)
        # TFS classification feedback table — stores human corrections for AI learning
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tfs_classify_feedback (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id          INTEGER NOT NULL,
                title              TEXT NOT NULL DEFAULT '',
                content            TEXT NOT NULL DEFAULT '',
                ai_property        TEXT NOT NULL DEFAULT '',
                ai_solution        TEXT NOT NULL DEFAULT '',
                ai_working_hour    REAL DEFAULT 1,
                human_property     TEXT NOT NULL DEFAULT '',
                human_solution     TEXT NOT NULL DEFAULT '',
                human_working_hour REAL DEFAULT 1,
                diff_flag          INTEGER NOT NULL DEFAULT 1,
                created_at         REAL NOT NULL
            )
        """)
        # Calendar: meeting rooms info
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meeting_rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                capacity    INTEGER DEFAULT 0,
                created_at  REAL NOT NULL
            )
        """)
        # Calendar: recurring booking plans
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recurring_plans (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                room_email     TEXT NOT NULL,
                subject        TEXT NOT NULL,
                day_of_week    INTEGER NOT NULL,
                start_time     TEXT NOT NULL,
                end_time       TEXT NOT NULL,
                max_days_ahead INTEGER NOT NULL DEFAULT 30,
                enabled        INTEGER NOT NULL DEFAULT 1,
                created_at     REAL NOT NULL
            )
        """)
        # Migration: add updated_at to recurring_plans if not present
        try:
            conn.execute("ALTER TABLE recurring_plans ADD COLUMN updated_at REAL")
            conn.commit()
        except Exception:
            pass  # column already exists

        # Calendar: booking history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                room_email  TEXT NOT NULL,
                subject     TEXT NOT NULL,
                date        TEXT NOT NULL,
                start_time  TEXT NOT NULL,
                end_time    TEXT NOT NULL,
                attendees   TEXT NOT NULL DEFAULT '',
                source      TEXT NOT NULL DEFAULT 'manual',
                plan_id     INTEGER,
                status      TEXT NOT NULL DEFAULT 'booked',
                created_at  REAL NOT NULL
            )
        """)
        # Calendar: AI suggestions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion  TEXT NOT NULL,
                reason      TEXT NOT NULL DEFAULT '',
                action      TEXT NOT NULL DEFAULT 'pending',
                created_at  REAL NOT NULL
            )
        """)
        # EDM List Import/Verify history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edm_list_history (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                sn                TEXT NOT NULL DEFAULT '',
                list_id           TEXT NOT NULL DEFAULT '',
                list_title        TEXT NOT NULL DEFAULT '',
                import_type       TEXT NOT NULL DEFAULT '',
                xlsx_path         TEXT NOT NULL DEFAULT '',
                csv_path          TEXT NOT NULL DEFAULT '',
                import_status     TEXT NOT NULL DEFAULT '',
                import_result     TEXT NOT NULL DEFAULT '',
                verify_email_status TEXT NOT NULL DEFAULT '',
                verify_email_result TEXT NOT NULL DEFAULT '',
                verify_deep_status  TEXT NOT NULL DEFAULT '',
                verify_deep_result  TEXT NOT NULL DEFAULT '',
                created_at        REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    logger.info(f"[task_queue] SQLite initialized at {db_path}")


def _conn():
    conn = sqlite3.connect(_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def run_task(name: str, generator: Iterator[str]) -> str:
    """Submit a generator-based task that yields progress strings.
    Returns task_id.

    Usage: run_task("my-task", my_generator())
    """
    task_id = str(uuid.uuid4())[:8]

    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO tasks (task_id, status, name, stdout, stderr, created_at) VALUES (?,?,?,?,?,?)",
            (task_id, "running", name, "", "", time.time()),
        )
        conn.commit()
        conn.close()

    thread = threading.Thread(
        target=_run_generator_task,
        args=(task_id, generator),
        daemon=True,
    )
    thread.start()
    return task_id


def _run_generator_task(task_id: str, generator: Iterator[str]):
    """Consume a generator, accumulate yielded strings as stdout."""
    try:
        output_parts = []
        for chunk in generator:
            output_parts.append(str(chunk))
            with _lock:
                conn = _conn()
                conn.execute("UPDATE tasks SET stdout=? WHERE task_id=?", ("\n".join(output_parts), task_id))
                conn.commit()
                conn.close()

        with _lock:
            conn = _conn()
            conn.execute("UPDATE tasks SET status=?, returncode=0 WHERE task_id=?", ("completed", task_id))
            conn.commit()
            conn.close()
    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        logger.exception(f"Task {task_id} failed: {e}")
        with _lock:
            conn = _conn()
            conn.execute("UPDATE tasks SET status=?, stderr=?, returncode=-1 WHERE task_id=?", ("failed", error_msg, task_id))
            conn.commit()
            conn.close()


def submit(func: Callable, *args, name: str = "", **kwargs) -> str:
    """Submit a function to run in a background thread. Returns task_id.

    Usage: submit(my_func, arg1, arg2, name="Task Name", kwarg1=val1)
    """
    task_id = str(uuid.uuid4())[:8]
    task_name = name or func.__name__

    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO tasks (task_id, status, name, stdout, stderr, created_at) VALUES (?,?,?,?,?,?)",
            (task_id, "running", task_name, "", "", time.time()),
        )
        conn.commit()
        conn.close()

    thread = threading.Thread(
        target=_run_task,
        args=(task_id, func, args, kwargs),
        daemon=True,
    )
    thread.start()
    return task_id


def _run_task(task_id: str, func: Callable, args: tuple, kwargs: dict):
    """Execute a task function and update its status."""
    try:
        result = func(*args, **kwargs)
        returncode = 0
        stderr = ""
        if isinstance(result, tuple) and len(result) == 3:
            stdout, stderr, returncode = result
        else:
            stdout = str(result) if result is not None else ""

        with _lock:
            conn = _conn()
            conn.execute(
                "UPDATE tasks SET status=?, stdout=?, stderr=?, returncode=? WHERE task_id=?",
                ("completed" if returncode == 0 else "failed", stdout, stderr, returncode, task_id),
            )
            conn.commit()
            conn.close()
    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        logger.exception(f"Task {task_id} failed: {e}")
        with _lock:
            conn = _conn()
            conn.execute("UPDATE tasks SET status=?, stderr=?, returncode=-1 WHERE task_id=?", ("failed", error_msg, task_id))
            conn.commit()
            conn.close()


def status(task_id: str) -> Dict[str, Any]:
    """Get task status. Returns empty dict if task_id not found."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        conn.close()
        if row is None:
            return {}
        d = dict(row)
        d["elapsed"] = round(time.time() - d.get("created_at", time.time()), 1)
        return d


def list_tasks(max_items: int = 50) -> list:
    """List recent tasks, newest first."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (max_items,),
        ).fetchall()
        conn.close()
    tasks = []
    for row in rows:
        d = dict(row)
        d["elapsed"] = round(time.time() - d.get("created_at", time.time()), 1)
        tasks.append(d)
    return tasks


# ─── EDM Events ─────────────────────────────────────────────


def save_event(event_time: str, event_type: str, message: str,
               subject: str = "", from_addr: str = "", sn: str = ""):
    """Save an EDM detection event to the database."""
    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO edm_events (event_time, event_type, message, subject, from_addr, sn) VALUES (?,?,?,?,?,?)",
            (event_time, event_type, message, subject, from_addr, sn),
        )
        conn.commit()
        conn.close()


def list_events(max_items: int = 50) -> list:
    """List recent EDM events, newest first."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM edm_events ORDER BY id DESC LIMIT ?",
            (max_items,),
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ─── Processed EDM files ────────────────────────────────────


def processed_eml_files() -> Dict[str, str]:
    """Return a dict of {eml_filename: latest_completed_at_iso} for .eml files
    whose **most recent** processing task completed successfully."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        # Get all EDM process tasks, newest first per filename
        rows = conn.execute(
            "SELECT name, status, created_at FROM tasks "
            "WHERE name LIKE 'edm-process-%' "
            "ORDER BY name, created_at DESC"
        ).fetchall()
        conn.close()

    seen = set()
    latest_status = {}
    latest_created = {}
    for r in rows:
        filename = r["name"].replace("edm-process-", "", 1)
        if filename in seen:
            continue
        seen.add(filename)
        latest_status[filename] = r["status"]
        latest_created[filename] = r["created_at"]

    from datetime import datetime
    result = {}
    for filename, status in latest_status.items():
        if status == "completed":
            result[filename] = datetime.fromtimestamp(latest_created[filename]).isoformat()
    return result


# ─── ICM Token History ────────────────────────────────────────


def save_icm_token_history(action: str, success: bool, got_new_token: str = None,
                           token_obtained_at: str = None, token_expires_at: str = None,
                           remaining_min: float = None, error_message: str = "",
                           detail: str = "", cookie_updated: str = None,
                           cookie_expires_at: str = None):
    """Save an ICM token operation (refresh/verify) to the history table."""
    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO icm_token_history "
            "(action, success, got_new_token, token_obtained_at, token_expires_at, "
            "remaining_min, error_message, detail, created_at, cookie_updated, cookie_expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (action, 1 if success else 0, got_new_token, token_obtained_at,
             token_expires_at, remaining_min, error_message, detail,
             datetime.now(tz=timezone.utc).isoformat(), cookie_updated, cookie_expires_at),
        )
        conn.commit()
        conn.close()


def list_icm_token_history(page: int = 1, page_size: int = 20) -> dict:
    """List recent ICM token history with pagination, newest first.

    Returns: {"total": int, "page": int, "page_size": int, "pages": int, "data": [...]}
    """
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM icm_token_history").fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, pages))
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM icm_token_history ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        conn.close()
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "data": [dict(r) for r in rows]}


# ─── Activity Log ─────────────────────────────────────────────


def save_activity(category: str, title: str, detail: str = "", status: str = "ok"):
    """Save an activity record.

    Args:
        category: Module tag, e.g. 'edm', 'icm', 'tfs', 'settings', 'dashboard'
        title: Short activity title, e.g. 'EDM Process SN-55247'
        detail: Optional detail text
        status: 'ok' | 'warn' | 'error'
    """
    import time
    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO activity_log (category, title, detail, status, created_at) VALUES (?,?,?,?,?)",
            (category, title, detail, status, time.time()),
        )
        conn.commit()
        conn.close()


def list_activities(max_items: int = 50) -> list:
    """List recent activities across all modules, newest first."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?",
            (max_items,),
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        from datetime import datetime
        ts = d.get("created_at", 0)
        d["created_at_str"] = datetime.fromtimestamp(ts).isoformat()
        d["elapsed_sec"] = round(time.time() - ts, 0)
        results.append(d)
    return results


# ─── TFS Classification Feedback ─────────────────────────────


def save_tfs_feedback(ticket_id: int, title: str, content: str,
                      ai_property: str, ai_solution: str, ai_working_hour: float,
                      human_property: str, human_solution: str, human_working_hour: float,
                      diff_flag: int):
    """Save a TFS classification feedback record."""
    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO tfs_classify_feedback "
            "(ticket_id, title, content, ai_property, ai_solution, ai_working_hour, "
            " human_property, human_solution, human_working_hour, diff_flag, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, title, content, ai_property, ai_solution, ai_working_hour,
             human_property, human_solution, human_working_hour, diff_flag, time.time()),
        )
        conn.commit()
        conn.close()


def list_tfs_feedback(page: int = 1, page_size: int = 20) -> dict:
    """List TFS classification feedback with pagination, newest first.

    Returns: {"total": int, "page": int, "page_size": int, "pages": int, "data": [...]}
    """
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM tfs_classify_feedback").fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, pages))
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM tfs_classify_feedback ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        data.append(d)
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "data": data}


def delete_tfs_feedback(feedback_id: int):
    """Delete a single feedback record by id."""
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM tfs_classify_feedback WHERE id=?", (feedback_id,))
        conn.commit()
        conn.close()


def get_similar_feedback(content: str, limit: int = 5) -> list:
    """Find similar feedback records by keyword overlap.

    Only returns diff_flag=1 records (human corrections — the most valuable samples).
    Returns a list of dicts sorted by score descending, capped at `limit`.
    """
    if not content:
        return []

    # Tokenize input: lowercase, split on whitespace/punctuation
    import re
    content_lower = content.lower()
    # Extract meaningful tokens (words with 2+ chars and chinese chars)
    input_tokens = set(re.findall(r'[a-z]{2,}|[一-鿿]', content_lower))

    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        # Only diff_flag=1 (corrections) — these are the valuable learning samples
        rows = conn.execute(
            "SELECT * FROM tfs_classify_feedback WHERE diff_flag=1 ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()

    scored = []
    for r in rows:
        rd = dict(r)
        # Combine title + content for matching
        combined = (rd.get("title", "") + " " + rd.get("content", "")).lower()
        fb_tokens = set(re.findall(r'[a-z]{2,}|[一-鿿]', combined))
        # Jaccard-like score: intersection size
        overlap = len(input_tokens & fb_tokens)
        if overlap > 0:
            scored.append((overlap, rd))

    # Sort by overlap descending, then by id descending (newest first for ties)
    scored.sort(key=lambda x: (x[0], -x[1]["id"]), reverse=True)
    return [item[1] for item in scored[:limit]]


def tfs_feedback_stats() -> dict:
    """Return feedback statistics."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM tfs_classify_feedback").fetchone()[0]
        diff_count = conn.execute(
            "SELECT COUNT(*) FROM tfs_classify_feedback WHERE diff_flag=1"
        ).fetchone()[0]
        agree_count = total - diff_count

        # Per-category distribution (human_property)
        cat_rows = conn.execute(
            "SELECT human_property, COUNT(*) as cnt FROM tfs_classify_feedback "
            "GROUP BY human_property ORDER BY cnt DESC"
        ).fetchall()
        conn.close()

        categories = [dict(r) for r in cat_rows]
        return {
            "total": total,
            "diff_count": diff_count,   # human corrected
            "agree_count": agree_count,  # human agreed
        }


# ─── Calendar: Meeting Rooms ─────────────────────────────────


def get_meeting_rooms() -> list:
    """List all meeting rooms."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM meeting_rooms ORDER BY name").fetchall()
        conn.close()
    return [dict(r) for r in rows]


def upsert_meeting_room(email: str, name: str, description: str = "", capacity: int = 0):
    """Insert or update a meeting room."""
    with _lock:
        conn = _conn()
        conn.execute("""
            INSERT INTO meeting_rooms (email, name, description, capacity, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
                name=excluded.name, description=excluded.description, capacity=excluded.capacity
        """, (email, name, description, capacity, time.time()))
        conn.commit()
        conn.close()


# ─── Calendar: Recurring Plans ───────────────────────────────


def create_recurring_plan(name: str, room_email: str, subject: str,
                          day_of_week: int, start_time: str, end_time: str,
                          max_days_ahead: int = 30) -> int:
    """Create a recurring booking plan. Returns plan id."""
    with _lock:
        conn = _conn()
        cursor = conn.execute("""
            INSERT INTO recurring_plans (name, room_email, subject, day_of_week,
                                         start_time, end_time, max_days_ahead, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, room_email, subject, day_of_week, start_time, end_time, max_days_ahead, time.time()))
        plan_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return plan_id


def list_recurring_plans() -> list:
    """List all recurring plans."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM recurring_plans ORDER BY id").fetchall()
        conn.close()
    return [dict(r) for r in rows]


def toggle_recurring_plan(plan_id: int, enabled: int):
    """Enable/disable a recurring plan."""
    with _lock:
        conn = _conn()
        conn.execute("UPDATE recurring_plans SET enabled=? WHERE id=?", (enabled, plan_id))
        conn.commit()
        conn.close()


def delete_recurring_plan(plan_id: int):
    """Delete a recurring plan."""
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM recurring_plans WHERE id=?", (plan_id,))
        conn.commit()
        conn.close()


def update_recurring_plan(plan_id: int, name: str = None, room_email: str = None,
                           subject: str = None, day_of_week: int = None,
                           start_time: str = None, end_time: str = None,
                           max_days_ahead: int = None):
    """Update a recurring plan's fields."""
    with _lock:
        conn = _conn()
        sets = []
        vals = []
        for col, val in [("name", name), ("room_email", room_email), ("subject", subject),
                         ("day_of_week", day_of_week), ("start_time", start_time),
                         ("end_time", end_time), ("max_days_ahead", max_days_ahead)]:
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(val)
        if not sets:
            conn.close()
            return
        sets.append("updated_at=?")
        vals.append(time.time())
        vals.append(plan_id)
        conn.execute(f"UPDATE recurring_plans SET {','.join(sets)} WHERE id=?", vals)
        conn.commit()
        conn.close()


# ─── Calendar: Booking History ───────────────────────────────


def save_booking(room_email: str, subject: str, date: str, start_time: str,
                 end_time: str, attendees: str = "", source: str = "manual",
                 plan_id: int = None, status: str = "booked"):
    """Save a booking record. Returns booking id."""
    with _lock:
        conn = _conn()
        cursor = conn.execute("""
            INSERT INTO booking_history (room_email, subject, date, start_time, end_time,
                                         attendees, source, plan_id, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (room_email, subject, date, start_time, end_time,
              attendees, source, plan_id, status, time.time()))
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return booking_id


def list_bookings(page: int = 1, page_size: int = 30, source: str = None) -> dict:
    """List booking history with pagination, newest first."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        if source:
            total = conn.execute(
                "SELECT COUNT(*) FROM booking_history WHERE source=?", (source,)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM booking_history WHERE source=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (source, page_size, (page - 1) * page_size)).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM booking_history").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM booking_history ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size)).fetchall()
        conn.close()
    pages = max(1, (total + page_size - 1) // page_size)
    data = []
    for r in rows:
        d = dict(r)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        data.append(d)
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "data": data}


def get_upcoming_bookings(days: int = 7) -> list:
    """Get upcoming bookings in the next N days."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    future = (date.today() + timedelta(days=days)).isoformat()
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM booking_history WHERE date >= ? AND date <= ? AND status='booked' "
            "ORDER BY date, start_time",
            (today, future)).fetchall()
        conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        data.append(d)
    return data


# ─── Calendar: AI Suggestions ────────────────────────────────


def save_ai_suggestion(suggestion: str, reason: str):
    """Save an AI suggestion. Returns suggestion id."""
    with _lock:
        conn = _conn()
        cursor = conn.execute("""
            INSERT INTO ai_suggestions (suggestion, reason, action, created_at)
            VALUES (?,?, 'pending', ?)
        """, (suggestion, reason, time.time()))
        suggestion_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return suggestion_id


def list_ai_suggestions() -> list:
    """List all AI suggestions, newest first."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM ai_suggestions ORDER BY id DESC").fetchall()
        conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        data.append(d)
    return data


def respond_ai_suggestion(suggestion_id: int, action: str):
    """Accept or ignore an AI suggestion."""
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE ai_suggestions SET action=? WHERE id=?",
            (action, suggestion_id))
        conn.commit()
        conn.close()


def get_booking_stats() -> dict:
    """Get booking statistics for AI analysis."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM booking_history").fetchone()[0]
        rooms = conn.execute(
            "SELECT room_email, COUNT(*) as cnt FROM booking_history "
            "GROUP BY room_email ORDER BY cnt DESC").fetchall()
        times = conn.execute(
            "SELECT start_time, COUNT(*) as cnt FROM booking_history "
            "GROUP BY start_time ORDER BY cnt DESC").fetchall()
        sources = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM booking_history "
            "GROUP BY source").fetchall()
        conn.close()
    return {
        "total": total,
        "rooms": [dict(r) for r in rooms],
        "times": [dict(r) for r in times],
        "sources": [dict(r) for r in sources],
    }


# ─── EDM List History ────────────────────────────────────────────────


def save_edm_list_history(sn='', list_id='', list_title='', import_type='',
                          xlsx_path='', csv_path='', import_status='',
                          import_result='', verify_email_status='',
                          verify_email_result='', verify_deep_status='',
                          verify_deep_result=''):
    """Save an EDM list import/verify history record. Returns row id."""
    with _lock:
        conn = _conn()
        cursor = conn.execute("""
            INSERT INTO edm_list_history (
                sn, list_id, list_title, import_type, xlsx_path, csv_path,
                import_status, import_result, verify_email_status, verify_email_result,
                verify_deep_status, verify_deep_result, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (sn, list_id, list_title, import_type, xlsx_path, csv_path,
              import_status, import_result, verify_email_status, verify_email_result,
              verify_deep_status, verify_deep_result, time.time()))
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
    logger.info(f"[task_queue] save_edm_list_history: id={row_id} sn={sn} list_id={list_id}")
    return row_id


def update_edm_list_verify(history_id, verify_email_status=None,
                            verify_email_result=None,
                            verify_deep_status=None, verify_deep_result=None):
    """Update verification status on an existing history record."""
    with _lock:
        conn = _conn()
        sets = []
        vals = []
        for col, val in [
            ('verify_email_status', verify_email_status),
            ('verify_email_result', verify_email_result),
            ('verify_deep_status', verify_deep_status),
            ('verify_deep_result', verify_deep_result),
        ]:
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(val)
        if not sets:
            conn.close()
            return
        vals.append(history_id)
        conn.execute(f"UPDATE edm_list_history SET {','.join(sets)} WHERE id=?", vals)
        conn.commit()
        conn.close()


def get_latest_edm_list_history(sn, list_id):
    """Get the most recent history record matching sn + list_id. Returns dict or None."""
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM edm_list_history WHERE sn=? AND list_id=? ORDER BY id DESC LIMIT 1",
            (sn, list_id),
        ).fetchone()
        conn.close()
    return dict(row) if row else None


def list_edm_list_history(page=1, page_size=20, sn=None):
    """List EDM list history with pagination, newest first.

    Returns: {"total": int, "page": int, "page_size": int, "pages": int, "data": [...]}
    """
    with _lock:
        conn = _conn()
        conn.row_factory = sqlite3.Row
        if sn:
            total = conn.execute("SELECT COUNT(*) FROM edm_list_history WHERE sn=?", (sn,)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM edm_list_history WHERE sn=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (sn, page_size, (page - 1) * page_size)).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM edm_list_history").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM edm_list_history ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size)).fetchall()
        conn.close()
    pages = max(1, (total + page_size - 1) // page_size)
    data = []
    for r in rows:
        d = dict(r)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        data.append(d)
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "data": data}
