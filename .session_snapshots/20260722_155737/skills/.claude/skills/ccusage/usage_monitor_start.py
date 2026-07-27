"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import os
import subprocess
import sys
import traceback
import time
from pathlib import Path

PID_FILE = Path.home() / ".claude" / "ccusage_monitor.pid"
LOG_FILE = Path(__file__).parent / ".usage_monitor_debug.log"
LOCK_FILE = Path.home() / ".claude" / "ccusage_monitor.lock"


def log(msg):
    from datetime import datetime
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def _is_process_alive(pid):
    """Check if a Windows process is alive.

    On Windows, pythonw is a GUI-subsystem process — os.kill(pid, 0) cannot
    send signals to it and raises OSError([WinError 87] 参数错误).
    That means the process EXISTS but is unreachable for signaling → treat as alive.

    Only ProcessLookupError means the PID is truly gone.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as e:
        # WinError 87 = pythonw GUI process, alive
        # WinError 5 = ACCESS_DENIED, alive
        log(f"  OSError for pid={pid}: {e} → treating as alive")
        return True
    except Exception:
        return False


def _acquire_lock():
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
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
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _is_running(pid_file):
    log(f"  Checking PID_FILE: exists={pid_file.exists()}")
    if not pid_file.exists():
        log("  → No PID file, not running")
        return False
    try:
        pid = int(pid_file.read_text().strip())
        alive = _is_process_alive(pid)
        log(f"  → PID={pid}, alive={alive}")
        return alive
    except ValueError:
        log("  → Bad PID content, not running")
        return False


def main():
    log("=" * 60)
    log("usage_monitor_start.py called")

    if not _acquire_lock():
        log("  → Could not acquire lock, another instance is starting. Exiting.")
        return
    try:
        log("  → Lock acquired")

        if _is_running(PID_FILE):
            log("  → Monitor already running, skipping")
            return
        else:
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
