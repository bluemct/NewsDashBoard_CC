"""
Context Guard — Daemon: polls CC Switch DB every 30s,
estimates next-turn input+output, auto-backs up skill+memory
when context approaches the 262K token limit.

Usage:
    python context_guard.py                  # Run daemon (default)
    python context_guard.py --interval 60    # Every 60s
    python context_guard.py --status         # One-shot context usage display
    python context_guard.py --backup         # Force backup now
    python context_guard.py --check          # One-shot check + auto-backup if needed
"""
import datetime
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import threading
import signal
from pathlib import Path

# Force UTF-8 stdout on Windows
if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Defaults ────────────────────────────────────────────────────────────

DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
PROJECT_DIR = Path(__file__).parent.parent.parent.parent
MEMORY_DIR = PROJECT_DIR / ".claude" / "memory"
SKILLS_DIR = PROJECT_DIR / ".claude" / "skills"
LOG_DIR = PROJECT_DIR / "Log"
LOG_FILE = LOG_DIR / "context_guard.log"
BACKUP_DIR = PROJECT_DIR / ".claude_backups"
PID_FILE = LOG_DIR / "context_guard.pid"

DEFAULT_LIMIT = 262144
DEFAULT_WARN = 80
DEFAULT_INTERVAL = 30

BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

_shutdown = threading.Event()
_backup_state = {"done": False}

# ── Logging ─────────────────────────────────────────────────────────────

LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("context_guard")


# ── Helpers ─────────────────────────────────────────────────────────────

def find_session():
    project_dir = Path.home() / ".claude" / "projects"
    if not project_dir.exists():
        return None
    candidates = []
    for pattern in ["C--Users-SI-Agent-AgentProject", "c--Users-SI-Agent-AgentProject"]:
        d = project_dir / pattern
        if d.exists():
            for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.stat().st_size > 1000:
                    candidates.append(f)
            break
    if not candidates:
        for dd in project_dir.iterdir():
            if dd.is_dir():
                for f in sorted(dd.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
                    if f.stat().st_size > 1000:
                        candidates.append(f)
    return max(candidates, key=lambda p: p.stat().st_mtime).stem if candidates else None


def query_turns(session_id, n=30):
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT created_at, request_model, model, input_tokens, output_tokens, latency_ms
        FROM proxy_request_logs
        WHERE session_id = ? AND input_tokens > 0
        ORDER BY created_at DESC LIMIT ?
    """, (session_id, n)).fetchall()
    conn.close()
    # Dedup by (input, output, created_at minute) to keep distinct turns
    seen = set()
    unique = []
    for r in rows:
        key = (r[3], r[4], r[0] // 60)  # Same input+output in same minute = dup
        if key not in seen:
            seen.add(key)
            unique.append({
                "created_at": r[0], "request_model": r[1], "model": r[2],
                "input_tokens": r[3], "output_tokens": r[4], "latency_ms": r[5],
            })
    unique.reverse()
    return unique or None


def estimate_next(turns):
    if len(turns) < 2:
        return turns[-1]["input_tokens"] if turns else 0, 0
    deltas = [turns[i]["input_tokens"] - turns[i-1]["input_tokens"] for i in range(1, len(turns))]
    recent = deltas[-5:]
    w = [2.0]*len(recent)
    w[-1] = 3.0
    avg = sum(r*c for r, c in zip(recent, w)) / sum(w)
    return turns[-1]["input_tokens"] + int(avg), avg


# ── Backup ──────────────────────────────────────────────────────────────

def do_backup(reason="unknown"):
    ts = datetime.datetime.now(tz=BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    bp = BACKUP_DIR / f"context_{ts}"
    bp.mkdir(parents=True, exist_ok=True)
    logger.info("=== BACKUP: %s (reason: %s) ===", bp.name, reason)

    items = []

    if MEMORY_DIR.exists():
        shutil.copytree(str(MEMORY_DIR), str(bp / "memory"))
        items.append(f"memory/")

    if SKILLS_DIR.exists():
        dest = bp / "skills"
        dest.mkdir(exist_ok=True)
        count = 0
        for sd in SKILLS_DIR.iterdir():
            if sd.is_dir():
                shutil.copytree(str(sd), str(dest / sd.name), dirs_exist_ok=True)
                count += 1
        items.append(f"skills/ ({count})")

    try:
        r = subprocess.run(["git", "status", "--short"], cwd=str(PROJECT_DIR),
                           capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            (bp / "git_status.txt").write_text(r.stdout, encoding="utf-8")
            items.append("git_status.txt")
    except Exception:
        pass

    manifest = {
        "timestamp": datetime.datetime.now(tz=BEIJING_TZ).isoformat(),
        "reason": reason, "project": PROJECT_DIR.name,
        "items": items, "path": str(bp),
    }
    (bp / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    backups = sorted(BACKUP_DIR.glob("context_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[5:]:
        shutil.rmtree(str(old))
        logger.info("  - Cleaned old: %s", old.name)

    logger.info("=== BACKUP DONE: %s ===", bp)
    return bp


# ── Core ────────────────────────────────────────────────────────────────

def check(session_id, limit, warn):
    turns = query_turns(session_id, n=30)
    if not turns:
        logger.warning("No turns for session %s", session_id)
        return 0

    model = (turns[-1].get("request_model") or "?")[:30]
    last_in = turns[-1]["input_tokens"]
    last_out = turns[-1]["output_tokens"]
    current = last_in + last_out
    est_in, delta = estimate_next(turns)
    pct = (current / limit) * 100
    pct_next = ((est_in + last_out) / limit) * 100

    bar = "█" * min(20, int(20 * pct / 100)) + "░" * max(0, 20 - int(20 * pct / 100))
    logger.info("T%d | %s | %s | in=%6d out=%4d | [%s] %.1f%% | next~%d | Δ+%.0f",
                len(turns), model, bar, last_in, last_out, bar, pct, est_in, delta)

    if delta > 0:
        left = (limit - current) / delta
        logger.info("  → ~%.0f turns remaining", left)

    if pct >= warn:
        if not _backup_state["done"]:
            _backup_state["done"] = True
            do_backup(f"pct_{pct:.0f}_turn{len(turns)}")
            logger.warning("⚠ ≥ %d%% — backup done!", warn)
    elif pct_next >= 100:
        if not _backup_state["done"]:
            _backup_state["done"] = True
            do_backup(f"next_over_{pct_next:.0f}pct")
            logger.critical("⛔ Next turn exceeds limit!")
    else:
        logger.info("  ✓ OK (%.1f%% < %d%%)", pct, warn)

    return pct


def show_status(session_id, limit):
    turns = query_turns(session_id, n=10)
    if not turns:
        print("No data.")
        return
    last_in = turns[-1]["input_tokens"]
    last_out = turns[-1]["output_tokens"]
    current = last_in + last_out
    est_in, delta = estimate_next(turns)
    pct = (current / limit) * 100
    bar = "█" * min(40, int(40 * pct / 100)) + "░" * max(0, 40 - int(40 * pct / 100))
    model = (turns[-1].get("request_model") or "?")[:30]
    print(f"\n  Context: [{bar}] {pct:.1f}%")
    print(f"  Current:       {current:>10,}  ({last_in:,} in + {last_out:,} out)")
    print(f"  Est. Next:     {est_in + last_out:>10,}")
    print(f"  Limit:         {limit:>10,}")
    print(f"  Model:         {model}")
    print(f"  Turns:         {len(turns)}")
    print(f"  Δ/turn:        +{delta:,.0f}")
    if delta > 0:
        print(f"  Turns left:    ~{(limit - current) / delta:.0f}")
    print()


def run_daemon(interval, limit, warn):
    PID_FILE.write_text(str(os.getpid()))
    signal.signal(signal.SIGINT, lambda s, f: _shutdown.set())
    signal.signal(signal.SIGTERM, lambda s, f: _shutdown.set())

    logger.info("Context Guard started")
    logger.info("  Interval: %ds | Limit: %d | Warn: %d%% | PID: %d", interval, limit, warn, os.getpid())

    while not _shutdown.is_set():
        sid = find_session()
        if not sid:
            _shutdown.wait(interval)
            continue
        pct = check(sid, limit, warn)
        wait = min(interval, 10) if pct >= 60 else interval
        _shutdown.wait(wait)

    if PID_FILE.exists():
        PID_FILE.unlink()
    logger.info("Daemon stopped (PID %d)", os.getpid())


# ── Main ────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="Context Guard — Auto-backup near context limit")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--warn", type=int, default=DEFAULT_WARN)
    p.add_argument("--session", type=str, default=None)
    p.add_argument("--status", action="store_true")
    p.add_argument("--backup", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()

    sid = args.session or find_session()
    if not sid:
        logger.error("No session found")
        sys.exit(1)

    if args.status:
        show_status(sid, args.limit)
        return
    if args.backup:
        _backup_state["done"] = True
        bp = do_backup("manual")
        print(f"Backup: {bp}")
        return
    if args.check:
        pct = check(sid, args.limit, args.warn)
        sys.exit(2 if pct >= args.warn else 0)
    # Default: daemon
    run_daemon(args.interval, args.limit, args.warn)


if __name__ == "__main__":
    main()
