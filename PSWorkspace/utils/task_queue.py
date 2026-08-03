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
        conn.commit()
        conn.close()
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
