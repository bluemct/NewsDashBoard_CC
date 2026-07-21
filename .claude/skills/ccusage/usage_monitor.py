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


class UsageMonitor:
    CORNER_RADIUS = 12

    def __init__(self, interval=5, limit=262144):
        self.interval = interval
        self.limit = limit
        self.session_id = find_current_session_id()
        self._last_size = (0, 0)

        self.root = tk.Tk()
        self.root.title("CC Usage")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)

        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._do_drag)
        self._drag_x = 0
        self._drag_y = 0

        self._close_btn = tk.Button(self.root, text="✕", bg=BG, fg="#888899",
                                     font=("Arial", 8), bd=0, relief="flat",
                                     command=self.root.destroy, cursor="hand2")

        self._labels = []
        self._update()

        # Apply rounded corners AFTER layout, with enough delay for actual size
        self.root.after(100, self._apply_rounded_corners)

        self._stop = False
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _apply_rounded_corners(self):
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w != self._last_size[0] or h != self._last_size[1]:
                hwnd = self.root.winfo_id()
                if w > 0 and h > 0:
                    hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, self.CORNER_RADIUS, self.CORNER_RADIUS)
                    if hrgn:
                        ctypes.windll.user32.SetWindowRgn(hwnd, hrgn, True)
                        self._last_size = (w, h)
        except Exception:
            pass

    def _start_drag(self, event):
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _do_drag(self, event):
        x = self.root.winfo_x() + event.x_root - self._drag_x
        y = self.root.winfo_y() + event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _poll(self):
        while not self._stop:
            self.root.after(0, self._update)
            import time
            time.sleep(self.interval)

    def _update(self):
        for lbl in self._labels:
            lbl.destroy()
        self._labels = []

        rows = query_latest(session_id=self.session_id)
        if not rows:
            return

        models = ["Opus", "Sonnet", "Haiku"]
        bar_width = 100
        padding = 14
        font_main = ("Consolas", 8, "bold")
        font_small = ("Consolas", 7)

        y_pos = 34
        for model_short, inp, outp in reversed(rows):
            if model_short not in models:
                continue
            input_pct = inp / self.limit
            output_pct = outp / self.limit

            name_lbl = tk.Label(self.root, text=model_short, font=font_main,
                                bg=BG, fg=TEXT_COLOR)
            name_lbl.place(x=padding, y=y_pos)
            self._labels.append(name_lbl)

            in_bg = tk.Canvas(self.root, width=bar_width, height=10,
                              bg=BAR_BG, highlightthickness=0)
            in_bg.place(x=padding + 64, y=y_pos + 1)
            self._labels.append(in_bg)

            in_color = get_color(input_pct)
            in_filled = max(0, min(round(input_pct * bar_width), bar_width))
            if in_filled > 0:
                in_bg.create_rectangle(0, 0, in_filled, 10, fill=in_color, outline="")

            in_text = tk.Label(self.root, text=f" {fmt_num(inp)}",
                               font=font_small, bg=BG, fg=in_color)
            in_text.place(x=padding + 64 + bar_width + 2, y=y_pos)
            self._labels.append(in_text)

            out_bg = tk.Canvas(self.root, width=bar_width, height=10,
                               bg=BAR_BG, highlightthickness=0)
            out_bg.place(x=padding + 64, y=y_pos + 18)
            self._labels.append(out_bg)

            out_color = get_color(output_pct)
            out_filled = max(0, min(round(output_pct * bar_width), bar_width))
            if out_filled > 0:
                out_bg.create_rectangle(0, 0, out_filled, 10, fill=out_color, outline="")

            out_text = tk.Label(self.root, text=f" {fmt_num(outp)}",
                                font=font_small, bg=BG, fg=out_color)
            out_text.place(x=padding + 64 + bar_width + 2, y=y_pos + 17)
            self._labels.append(out_text)

            y_pos += 40

        total_width = padding + 64 + bar_width + 56
        total_height = y_pos + 18

        # Set window geometry so it matches content
        self.root.geometry(f"{total_width}x{total_height}")

        title = tk.Label(self.root, text="☁  CC Usage",
                         font=("Microsoft YaHei UI", 9, "bold"),
                         bg=BG, fg=TEXT_COLOR)
        title.place(x=padding, y=8)
        self._labels.append(title)

        self._close_btn.place(x=total_width - 22, y=4)

        # Re-apply corners after geometry change
        self.root.after(50, self._apply_rounded_corners)

    def run(self):
        self.root.mainloop()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CC Usage floating monitor")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--limit", type=int, default=262144, help="Context limit in tokens")
    args = parser.parse_args()

    monitor = UsageMonitor(interval=args.interval, limit=args.limit)
    monitor.run()


if __name__ == "__main__":
    main()