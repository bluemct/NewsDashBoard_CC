"""
CC Usage Monitor — Floating usage bar overlay.

Shows per-model latest token usage with progress bars.
Polls cc-switch.db every 5 seconds, stays on top of other windows.

Usage:
    python .claude/skills/ccusage/usage_monitor.py
    python .claude/skills/ccusage/usage_monitor.py --interval 3  # 3s poll
    python .claude/skills/ccusage/usage_monitor.py --limit 1000000  # 1M context (Opus 1M)
"""
import ctypes
import json
import re
import sqlite3
import sys
import threading
import tkinter as tk
from pathlib import Path

DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"

GREEN = "#22c55e"
YELLOW = "#eab308"
RED = "#ef4444"
BG = "#1e1e2e"
BAR_BG = "#313244"
TEXT_COLOR = "#cdd6f4"

MODELS = ["Opus", "Sonnet", "Haiku"]
BAR_WIDTH = 100
PADDING = 14


def fmt_num(n):
    if n is None or n == 0:
        return "0"
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.0f}K"
    return str(n)


def get_color(pct):
    if pct < 0.6:
        return GREEN
    if pct < 0.8:
        return YELLOW
    return RED


def find_current_session_id():
    project_dir = Path.home() / ".claude" / "projects"
    if not project_dir.exists():
        return None
    for pattern in ["C--Users-SI-Agent-AgentProject", "c--Users-SI-Agent-AgentProject"]:
        d = project_dir / pattern
        if d.exists():
            files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files:
                if f.stat().st_size > 1000:
                    return f.stem
            break
    return None


def get_session_name(session_id):
    """Get session display name from /rename command in jsonl.
    Returns the LAST /rename if there are multiple. None if no rename found."""
    if not session_id:
        return None
    project_dir = Path.home() / ".claude" / "projects"
    for pattern in ["C--Users-SI-Agent-AgentProject", "c--Users-SI-Agent-AgentProject"]:
        d = project_dir / pattern
        if not d.exists():
            continue
        jsonl_path = d / f"{session_id}.jsonl"
        if not jsonl_path.exists():
            continue
        try:
            last_rename = None
            with open(jsonl_path, encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    obj = json.loads(line)
                    if obj.get("type") != "user":
                        continue
                    content = obj.get("message", {}).get("content", "")
                    if isinstance(content, str) and "/rename" in content:
                        m = re.search(r"<command-args>(.+?)</command-args>", content)
                        if m:
                            last_rename = m.group(1).strip()
            return last_rename
        except Exception:
            pass
    return None


def query_latest(session_id=None):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    where_sql = ""
    params = []
    if session_id:
        where_sql = "WHERE session_id = ?"
        params.append(session_id)
    query = f"""
        SELECT request_model, input_tokens, output_tokens
        FROM proxy_request_logs p
        INNER JOIN (
            SELECT MAX(created_at) AS latest_at
            FROM proxy_request_logs
            {where_sql}
            GROUP BY CASE
                WHEN request_model LIKE '%sonnet%' OR model LIKE '%sonnet%' THEN 'sonnet'
                WHEN request_model LIKE '%opus%' OR model LIKE '%opus%' THEN 'opus'
                WHEN request_model LIKE '%haiku%' OR model LIKE '%haiku%' THEN 'haiku'
                ELSE request_model
            END
        ) latest
        ON p.created_at = latest.latest_at
        {where_sql}
    """
    rows = conn.execute(query, params + params).fetchall()
    conn.close()
    results = []
    for r in rows:
        model = (r["request_model"] or r["model"] or "?").lower()
        if "sonnet" in model:
            short = "Sonnet"
        elif "opus" in model:
            short = "Opus"
        elif "haiku" in model:
            short = "Haiku"
        else:
            short = r["request_model"] or "?"
        results.append((short, r["input_tokens"] or 0, r["output_tokens"] or 0))
    return results


def _make_bar(frame, y):
    """Create an empty bar widget set (canvas + text label) at position y."""
    bar = tk.Canvas(frame, width=BAR_WIDTH, height=10,
                    bg=BAR_BG, highlightthickness=0)
    bar.place(x=PADDING + 64, y=y)
    txt = tk.Label(frame, text=" 0",
                   font=("Consolas", 7), bg=BG, fg=TEXT_COLOR)
    txt.place(x=PADDING + 64 + BAR_WIDTH + 2, y=y - 1)
    return bar, txt


class ModelBar:
    """Widgets for one model row: name, input bar, output bar."""

    def __init__(self, root, model_name, y_base):
        self.name_lbl = tk.Label(root, text=model_name,
                                 font=("Consolas", 8, "bold"),
                                 bg=BG, fg=TEXT_COLOR)
        self.name_lbl.place(x=PADDING, y=y_base)

        self.in_canvas, self.in_text = _make_bar(root, y_base + 1)
        self.out_canvas, self.out_text = _make_bar(root, y_base + 18)

    def update(self, inp, outp, limit):
        input_pct = inp / limit
        output_pct = outp / limit
        in_color = get_color(input_pct)
        out_color = get_color(output_pct)

        self.in_canvas.delete("all")
        in_filled = max(0, min(round(input_pct * BAR_WIDTH), BAR_WIDTH))
        if in_filled > 0:
            self.in_canvas.create_rectangle(0, 0, in_filled, 10, fill=in_color, outline="")
        self.in_text.config(text=f" {fmt_num(inp)}", fg=in_color)

        self.out_canvas.delete("all")
        out_filled = max(0, min(round(output_pct * BAR_WIDTH), BAR_WIDTH))
        if out_filled > 0:
            self.out_canvas.create_rectangle(0, 0, out_filled, 10, fill=out_color, outline="")
        self.out_text.config(text=f" {fmt_num(outp)}", fg=out_color)

    def hide_all(self):
        self.name_lbl.place_forget()
        self.in_canvas.place_forget()
        self.in_text.place_forget()
        self.out_canvas.place_forget()
        self.out_text.place_forget()


class UsageMonitor:
    CORNER_RADIUS = 20

    def __init__(self, interval=5, limit=198000):
        self.interval = interval
        self.limit = limit
        self.session_id = None
        self._last_size = (0, 0)
        self._dragging = False

        self.root = tk.Tk()
        self.root.title("CC Usage")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.8)
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)

        # Drag: manual, guarded by _dragging flag
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0
        self._drag_start_ptr_x = 0
        self._drag_start_ptr_y = 0
        self.root.bind("<ButtonPress-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._do_drag)
        self.root.bind("<ButtonRelease-1>", self._end_drag)

        # Close button
        self._close_btn = tk.Button(self.root, text="✕", bg=BG, fg="#888899",
                                     font=("Arial", 8), bd=0, relief="flat",
                                     command=self.root.destroy, cursor="hand2")

        # Title label
        self._title_lbl = tk.Label(self.root, text="☁  CC Usage",
                                    font=("Microsoft YaHei UI", 9, "bold"),
                                    bg=BG, fg=TEXT_COLOR)

        # Session label
        self._session_lbl = tk.Label(self.root, text="",
                                      font=("Microsoft YaHei UI", 8, "bold"),
                                      bg=BG, fg="#cdd6f4")

        # Model bars — pre-create 3 (max models)
        self._bars = [ModelBar(self.root, MODELS[i], 34 + i * 40) for i in range(3)]

        # Initial render
        self._update()

        # Apply rounded corners ONCE after layout settles
        self.root.after(150, self._apply_rounded_corners)

        # Polling thread
        self._stop = False
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _apply_rounded_corners(self):
        """Apply rounded corners once — never again (avoids drag issues)."""
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w > 0 and h > 0:
                hwnd = self.root.winfo_id()
                hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, self.CORNER_RADIUS, self.CORNER_RADIUS)
                if hrgn:
                    ctypes.windll.user32.SetWindowRgn(hwnd, hrgn, True)
        except Exception:
            pass

    def _start_drag(self, event):
        self._dragging = True
        self._drag_start_win_x = self.root.winfo_x()
        self._drag_start_win_y = self.root.winfo_y()
        self._drag_start_ptr_x = self.root.winfo_pointerx()
        self._drag_start_ptr_y = self.root.winfo_pointery()

    def _do_drag(self, event):
        dx = self.root.winfo_pointerx() - self._drag_start_ptr_x
        dy = self.root.winfo_pointery() - self._drag_start_ptr_y
        self.root.geometry(f"+{self._drag_start_win_x + dx}+{self._drag_start_win_y + dy}")

    def _end_drag(self, event=None):
        self._dragging = False

    def _poll(self):
        while not self._stop:
            self.root.after(0, self._update)
            import time
            time.sleep(self.interval)

    def _update(self):
        if self._dragging:
            return

        # Refresh session_id on every poll
        self.session_id = find_current_session_id()

        rows = query_latest(session_id=self.session_id)
        if not rows:
            return

        y_pos = 34

        # Build a dict from rows for name-based lookup
        data_by_name = {row[0]: row for row in rows}

        for i, bar in enumerate(self._bars):
            model_name = MODELS[i]
            if model_name in data_by_name:
                _, inp, outp = data_by_name[model_name]
                bar.update(inp, outp, self.limit)
                y_pos += 40
            else:
                bar.hide_all()

        total_width = PADDING + 64 + BAR_WIDTH + 56
        session_height = 24 if self.session_id else 0
        total_height = y_pos + 18 + session_height

        self.root.geometry(f"{total_width}x{total_height}")

        # Position persistent widgets
        self._title_lbl.place(x=PADDING, y=8)
        self._close_btn.place(x=total_width - 22, y=4)

        # Session name at bottom
        if self.session_id:
            session_name = get_session_name(self.session_id) or self.session_id[:8]
            self._session_lbl.config(text=f"Session: {session_name}", fg="#cdd6f4")
            self._session_lbl.place(x=PADDING, y=y_pos + 10)
        else:
            self._session_lbl.place_forget()

    def run(self):
        self.root.mainloop()


def main():
    import argparse

    # Single-instance via Windows named mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Local\\CCUsageMonitor_4a8f2c1d")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return

    parser = argparse.ArgumentParser(description="CC Usage floating monitor")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--limit", type=int, default=198000, help="Context limit in tokens (default 198K = 262K - 64K max_tokens)")
    args = parser.parse_args()

    monitor = UsageMonitor(interval=args.interval, limit=args.limit)
    monitor.run()


if __name__ == "__main__":
    main()
