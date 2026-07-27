"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

PID_FILE = Path.home() / ".claude" / "ccusage_monitor.pid"


def is_running(pid_file):
    """Read PID file and check if the process is still alive."""
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        # Try to signal the process (pid 0 means it's alive on Windows)
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def main():
    if is_running(PID_FILE):
        return  # Already running, skip
    # Fork usage_monitor in background
    script_dir = Path(__file__).parent
    subprocess.Popen(
        [sys.executable.replace("python", "pythonw"),
         str(script_dir / "usage_monitor.py"),
         "--interval", "3",
         "--pid-file", str(PID_FILE)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
