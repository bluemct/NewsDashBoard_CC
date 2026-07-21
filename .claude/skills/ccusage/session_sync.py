"""
Session Sync — On session end, detect changes made during the session
and update skill files / memory accordingly.

Reads stdin JSON for session_id, checks git diff and file mtime changes,
then syncs modified skills and memory files.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).parent.parent.parent.parent
MEMORY_DIR = PROJECT_DIR / ".claude" / "memory"
SKILLS_DIR = PROJECT_DIR / ".claude" / "skills"
LOG_DIR = PROJECT_DIR / "Log"
LOG_FILE = LOG_DIR / "session_sync.log"

BEIJING_TZ = timezone(timedelta(hours=8))

LOG_DIR.mkdir(exist_ok=True)

# ── Logging ─────────────────────────────────────────────────────────────

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("session_sync")


def find_session_jsonl(session_id):
    """Find the JSONL file for this session."""
    project_dir = Path.home() / ".claude" / "projects"
    if not project_dir.exists():
        return None
    for d in project_dir.iterdir():
        if d.is_dir():
            f = d / f"{session_id}.jsonl"
            if f.exists():
                return f
    return None


def get_session_start_time(session_id):
    """Get the first timestamp from the session JSONL."""
    jsonl = find_session_jsonl(session_id)
    if not jsonl:
        return None
    try:
        with open(jsonl, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    ts = data.get("timestamp")
                    if ts:
                        return ts[:19]  # 2026-07-16T10:08:38
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def detect_git_changes():
    """Get list of modified/new files via git status."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True, timeout=10,
        )
        changes = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split(None, 1)
            status = parts[0]
            file_path = parts[1] if len(parts) > 1 else ""
            changes.append({"status": status, "path": file_path})
        return changes
    except Exception as e:
        logger.error("Git status failed: %s", e)
        return []


def detect_memory_changes():
    """Check if memory files were modified."""
    if not MEMORY_DIR.exists():
        return []
    changes = []
    for f in MEMORY_DIR.rglob("*"):
        if f.is_file():
            changes.append({"path": str(f.relative_to(PROJECT_DIR)), "type": "memory"})
    return changes


def detect_skill_changes():
    """Check if skill files were modified."""
    if not SKILLS_DIR.exists():
        return []
    changes = []
    for f in SKILLS_DIR.rglob("*"):
        if f.is_file():
            changes.append({"path": str(f.relative_to(PROJECT_DIR)), "type": "skill"})
    return changes


def sync_session(session_id):
    """Main sync logic: detect changes, log, create snapshot."""
    start_time = get_session_start_time(session_id)
    now = datetime.now(tz=BEIJING_TZ)

    logger.info("=== Session Sync: %s ===", session_id)
    logger.info("  Started: %s", start_time or "unknown")
    logger.info("  Ended:   %s", now.strftime("%Y-%m-%d %H:%M:%S"))

    # 1. Git changes
    git_changes = detect_git_changes()
    skills_changed = []
    memory_changed = []
    other_changed = []

    for gc in git_changes:
        path = gc["path"]
        if ".claude/skills/" in path or ".claude\\skills\\" in path:
            skills_changed.append(gc)
        elif ".claude/memory/" in path or ".claude\\memory\\" in path:
            memory_changed.append(gc)
        else:
            other_changed.append(gc)

    # 2. Summary
    logger.info("  Git changes: %d total", len(git_changes))
    logger.info("    Skills:    %d", len(skills_changed))
    logger.info("    Memory:    %d", len(memory_changed))
    logger.info("    Other:     %d", len(other_changed))

    # 3. Create snapshot if there are changes
    if skills_changed or memory_changed:
        ts = now.strftime("%Y%m%d_%H%M%S")
        snapshot_dir = PROJECT_DIR / ".session_snapshots" / ts
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot = {
            "session_id": session_id,
            "started": start_time,
            "ended": now.isoformat(),
            "skills_changed": [s["path"] for s in skills_changed],
            "memory_changed": [m["path"] for m in memory_changed],
            "other_changed": [o["path"] for o in other_changed],
            "total_changes": len(git_changes),
        }

        # Save snapshot manifest
        with open(snapshot_dir / "snapshot.json", "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        # Copy changed skill files
        if skills_changed:
            skills_dest = snapshot_dir / "skills"
            for s in skills_changed:
                src = PROJECT_DIR / s["path"]
                if src.exists():
                    dest = skills_dest / s["path"]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dest))
            logger.info("  Snapshot: %s (skills)", snapshot_dir.name)

        # Copy changed memory files
        if memory_changed:
            mem_dest = snapshot_dir / "memory"
            for m in memory_changed:
                src = PROJECT_DIR / m["path"]
                if src.exists():
                    dest = mem_dest / m["path"]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dest))
            logger.info("  Snapshot: %s (memory)", snapshot_dir.name)

        # Cleanup old snapshots (keep last 10)
        snap_dir = PROJECT_DIR / ".session_snapshots"
        if snap_dir.exists():
            snaps = sorted(snap_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in snaps[10:]:
                shutil.rmtree(str(old))

    else:
        logger.info("  No skill/memory changes detected — snapshot skipped")

    # 4. Output JSON for hook system
    output = {
        "systemMessage": f"Session sync complete: {len(git_changes)} changes ({len(skills_changed)} skills, {len(memory_changed)} memory)",
    }
    print(json.dumps(output))


def main():
    # Read session data from stdin
    try:
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            data = json.loads(stdin_data)
            session_id = data.get("session_id", "")
        else:
            # No stdin — try to find session from arguments
            session_id = sys.argv[1] if len(sys.argv) > 1 else ""
    except json.JSONDecodeError:
        session_id = sys.argv[1] if len(sys.argv) > 1 else ""

    if not session_id:
        logger.warning("No session_id provided")
        # Fallback: just sync based on current git state
        session_id = "standalone"

    sync_session(session_id)


if __name__ == "__main__":
    main()
