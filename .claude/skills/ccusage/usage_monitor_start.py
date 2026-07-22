"""
CC Usage Monitor — Simple launcher.

Starts usage_monitor.py in background via pythonw.
Single-instance is handled by usage_monitor.py via Windows named mutex.
"""
import subprocess
import sys
from pathlib import Path


def main():
    script_dir = Path(__file__).parent
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    monitor_script = str(script_dir / "usage_monitor.py")

    subprocess.Popen(
        [pythonw, monitor_script, "--interval", "3"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
