"""
CC Usage Monitor — One-instance launcher.

Starts usage_monitor.py only if no instance is already running (PID-file check).
Used as SessionStart hook to avoid spawning multiple windows.
"""
import os
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
        os.kill(pid, 0)
        # On Windows, os.kill(pid, 0) raises PermissionError for alive processes
        # that belong to another process group, so treat it as alive.
        return True  # Process is alive (or unreachable — treat as alive)
    except ValueError:
        return False  # Bad PID content
    except ProcessLookupError:
        return False  # Process definitely gone
    except PermissionError:
        return True   # Windows: process exists but we can't signal it
    except OSError:
        # FileNotFoundError on Windows means process is gone
        return False


def main():
    if is_running(PID_FILE):
        return  # Already running, skip
    # Fork usage_monitor in background
    script_dir = Path(__file__).parent
    pythonw = sys.executable.replace("python.exe", "pythonw.exe").replace("pythonw", "pythonw.exe")
    subprocess.Popen(
        [pythonw,
         str(script_dir / "usage_monitor.py"),
         "--interval", "3",
         "--pid-file", str(PID_FILE)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
