"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import ctypes
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path

PID_FILE = Path.home() / ".claude" / "ccusage_monitor.pid"
LOG_FILE = Path(__file__).parent / ".usage_monitor_debug.log"

# Windows: OPENPROCESS query right for IsProcessIdle, SYNCHRONIZE right for WaitForSingleObject
_OPEN_PROCESS_FLAGS = 0x0400 | 0x0010  # PROCESS_QUERY_INFORMATION | SYNCHRONIZE
_STILL_ACTIVE = 259


def log(msg):
    from datetime import datetime
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def _is_process_alive(pid):
    """Check if a Windows process is alive using OpenProcess + WaitForSingleObject."""
    try:
        handle = ctypes.windll.kernel32.OpenProcess(_OPEN_PROCESS_FLAGS, 0, pid)
        if not handle:
            return False
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        ctypes.windll.kernel32.CloseHandle(handle)
        # WAIT_OBJECT_0 (0) = terminated, STILL_ACTIVE (259) = alive
        return result == _STILL_ACTIVE
    except Exception:
        return False


# A global lock to prevent two calls from launching simultaneously
_launch_lock = threading.Lock()


def is_running(pid_file):
    """Read PID file and check if the process is still alive."""
    log(f"is_running called. PID_FILE exists: {pid_file.exists()}")
    if not pid_file.exists():
        log("  No PID file found — returning False")
        return False
    try:
        pid = int(pid_file.read_text().strip())
        alive = _is_process_alive(pid)
        log(f"  PID={pid}, alive={alive}")
        return alive
    except ValueError:
        log("  ValueError — bad PID content")
        return False


def main():
    log("=" * 60)
    log("usage_monitor_start.py called")
    log(f"  CWD: {os.getcwd()}")
    log(f"  sys.executable: {sys.executable}")

    with _launch_lock:
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
            # Write PID immediately — don't wait for child
            try:
                PID_FILE.write_text(str(result.pid))
            except Exception:
                pass
            log(f"  → Popen succeeded, pid={result.pid}, PID_FILE written")
        except Exception as e:
            log(f"  → Popen FAILED: {e}")
            log(traceback.format_exc())


if __name__ == "__main__":
    main()
