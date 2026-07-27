"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import os
import subprocess
import sys
import traceback
from pathlib import Path

PID_FILE = Path.home() / ".claude" / "ccusage_monitor.pid"
LOG_FILE = Path(__file__).parent / ".usage_monitor_debug.log"


def log(msg):
    from datetime import datetime
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def is_running(pid_file):
    """Read PID file and check if the process is still alive."""
    log(f"is_running called. PID_FILE exists: {pid_file.exists()}")
    if not pid_file.exists():
        log("  No PID file found — returning False")
        return False
    try:
        pid = int(pid_file.read_text().strip())
        log(f"  PID={pid}, calling os.kill(pid, 0)...")
        os.kill(pid, 0)
        log("  os.kill succeeded — process alive")
        return True
    except ValueError:
        log("  ValueError — bad PID content")
        return False
    except ProcessLookupError:
        log("  ProcessLookupError — process gone")
        return False
    except PermissionError:
        log("  PermissionError — process alive (Windows behavior)")
        return True
    except OSError as e:
        log(f"  OSError({e}) — process gone")
        return False


def main():
    log("=" * 60)
    log("usage_monitor_start.py called")
    log(f"  CWD: {os.getcwd()}")
    log(f"  sys.executable: {sys.executable}")

    if is_running(PID_FILE):
        log("  → Skipping, monitor already running")
        return
    else:
        # Clean up stale PID file
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    script_dir = Path(__file__).parent
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    monitor_script = str(script_dir / "usage_monitor.py")
    log(f"  pythonw: {pythonw}")
    log(f"  monitor: {monitor_script}")
    log(f"  pythonw exists: {os.path.exists(pythonw)}")

    try:
        result = subprocess.Popen(
            [pythonw,
             monitor_script,
             "--interval", "3",
             "--pid-file", str(PID_FILE)],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"  → Popen succeeded, pid={result.pid}")
    except Exception as e:
        log(f"  → Popen FAILED: {e}")
        log(traceback.format_exc())


if __name__ == "__main__":
    main()
