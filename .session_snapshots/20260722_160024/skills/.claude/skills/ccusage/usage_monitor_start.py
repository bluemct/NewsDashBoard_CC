"""
CC Usage Monitor — Simple launcher.

Just starts usage_monitor.py in background and exits.
Single-instance is handled by usage_monitor.py via Windows named mutex.
"""
import os
import subprocess
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent / ".usage_monitor_debug.log"


def log(msg):
    from datetime import datetime
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def main():
    script_dir = Path(__file__).parent
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    monitor_script = str(script_dir / "usage_monitor.py")

    log(f"Launching usage_monitor.py...")

    subprocess.Popen(
        [pythonw, monitor_script, "--interval", "3"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log(f"  → Popen done")


if __name__ == "__main__":
    main()
