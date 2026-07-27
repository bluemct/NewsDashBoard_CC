"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import ctypes
import os
import subprocess
import sys
import traceback
import time
from pathlib import Path

PID_FILE = Path.home() / ".claude" / "ccusage_monitor.pid"
LOG_FILE = Path(__file__).parent / ".usage_monitor_debug.log"
LOCK_FILE = Path.home() / ".claude" / "ccusage_monitor.lock"

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
        return result == _STILL_ACTIVE
    except Exception:
        return False


def _acquire_lock():
    """Acquire a cross-process file lock by repeatedly trying to create LOCK_FILE.

    Returns True if acquired, False if timeout (another process holds it)."""
    deadline = time.monotonic() + 5.0  # 5 second timeout
    while time.monotonic() < deadline:
        try:
            # Exclusive create — fails if file already exists
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            pass
        except OSError:
            pass
        time.sleep(0.1)
    return False


def _release_lock():
    """Remove the lock file."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _is_running(pid_file):
    """Read PID file and check if the process is still alive."""
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        alive = _is_process_alive(pid)
        return alive
    except ValueError:
        return False


def main():
    log("=" * 60)
    log("usage_monitor_start.py called")

    # Cross-process lock — only one process proceeds at a time
    if not _acquire_lock():
        log("  → Could not acquire lock, another instance is starting. Exiting.")
        return
    try:
        log("  → Lock acquired")

        if _is_running(PID_FILE):
            log("  → Monitor already running, skipping")
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
    finally:
        _release_lock()
        log("  → Lock released")


if __name__ == "__main__":
    main()
