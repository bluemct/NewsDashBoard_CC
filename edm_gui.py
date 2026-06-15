"""
EDM Email Processor — Windows GUI Tool

Standalone tkinter application for processing EDM emails:
- Extract SN from .msg, create Desktop\\EDM\\SN-xxxxx\\ folder
- Extract nested .msg (0 recipients), convert to HTML with token replacement
- Convert .xlsx to CSV, generate formal and test CSVs
- Log all steps to process.log

Usage:
    python edm_gui.py

Dependencies: extract-msg, olefile, win32com, openpyxl (same as edm_process.py)
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------
# Import core functions from edm_process
# ---------------------------------------------------------------------------
_SKILL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".claude", "skills", "edm-process"
)
sys.path.insert(0, _SKILL_DIR)

try:
    from edm_process import (
        _get_short_path,
        extract_sn,
        find_target_attachment_idx,
        replace_span_tokens,
        save_target_attachment,
    )
except ImportError as e:
    print(f"Warning: Could not import edm_process: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TOKENMAP_NAME = "Tokenmapping.json"
OUTPUT_BASE = os.path.join(os.path.expanduser("~"), "Desktop", "EDM")

# ---------------------------------------------------------------------------
# ProcessLogger — logs to GUI + in-memory list (written to file at end)
# ---------------------------------------------------------------------------


class ProcessLogger:
    def __init__(self, root: tk.Tk, text_widget: tk.Text):
        self.root = root
        self.text_widget = text_widget
        self.lines: list[str] = []

    def log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.lines.append(line)
        self.root.after(0, self._append_gui, line)

    def _append_gui(self, line: str):
        self.text_widget.config(state="normal")
        self.text_widget.insert("end", line + "\n")
        self.text_widget.see("end")
        self.text_widget.config(state="disabled")

    def write_file(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def find_tokenmap(override_path: str | None = None) -> tuple[str | None, dict]:
    """Return (path, token_dict)."""
    if override_path and os.path.isfile(override_path):
        return _load_tokenmap(override_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, DEFAULT_TOKENMAP_NAME)
    if os.path.isfile(path):
        return _load_tokenmap(path)
    return None, {}


def _load_tokenmap(path: str) -> tuple[str, dict]:
    with open(path, "r", encoding="utf-8") as f:
        mapping_list = json.load(f)
    mapping = {item["Name"]: item["Value"] for item in mapping_list}
    return path, mapping


def _convert_xlsx_to_csv(xlsx_path: str, logger: ProcessLogger) -> bool:
    """Call xlsx_to_csv.py subprocess."""
    xlsx_skill = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".claude", "skills", "xlsx-to-csv", "xlsx_to_csv.py",
    )
    if not os.path.isfile(xlsx_skill):
        logger.log(f"[CSV] xlsx_to_csv skill not found: {xlsx_skill}")
        return False
    result = subprocess.run(
        [sys.executable, xlsx_skill, xlsx_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in result.stdout.strip().splitlines():
        logger.log(f"  {line}")
    if result.returncode != 0:
        logger.log(f"[CSV] xlsx_to_csv failed: {result.stderr.strip()}")
    return result.returncode == 0


def _generate_formal_test_csv(xlsx_path: str, logger: ProcessLogger) -> None:
    """Generate formal_*.csv and test_*.csv from the source CSV."""
    sn_dir = os.path.dirname(xlsx_path)
    base = os.path.splitext(os.path.basename(xlsx_path))[0]
    import glob

    csv_files = glob.glob(os.path.join(sn_dir, base + "*.csv"))
    csv_path = csv_files[0] if csv_files else None
    if not csv_path or not os.path.exists(csv_path):
        logger.log("[CSV] no source CSV found for formal/test generation")
        return

    with open(csv_path, encoding="gb18030", newline="") as f:
        reader = list(csv.reader(f))
        header = reader[0]
        rows = reader[1:]

    # Formal CSV
    formal_path = os.path.join(sn_dir, f"formal_{base}.csv")
    shutil.copy2(csv_path, formal_path)
    logger.log(f"[CSV-FORMAL] saved: {os.path.basename(formal_path)} ({len(rows)} rows)")

    # Test CSV
    email_idx = None
    for i, col in enumerate(header):
        if col.strip().lower() == "email":
            email_idx = i
            break

    token_cols = [i for i, col in enumerate(header) if col.strip().lower().startswith("token")]
    row_scores = []
    for i, row in enumerate(rows):
        score = sum(1 for idx in token_cols if idx < len(row) and row[idx].strip())
        if score > 0:
            row_scores.append((score, i, row))
    row_scores.sort(reverse=True)

    if len(row_scores) >= 2:
        r1 = list(row_scores[0][2])
        r2 = list(row_scores[1][2])
    else:
        r1 = list(row_scores[0][2]) if row_scores else list(rows[0]) if rows else ["" for _ in header]
        r2 = list(row_scores[1][2]) if len(row_scores) > 1 else (list(rows[1]) if len(rows) > 1 else ["" for _ in header])

    if email_idx is not None:
        r1[email_idx] = "ma.chuntao@oe.21vianet.com"
        r2[email_idx] = "microsoft.163163@163.com"

    test_path = os.path.join(sn_dir, f"test_{base}.csv")
    with open(test_path, "w", encoding="gb18030", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(r1)
        writer.writerow(r2)
    logger.log(f"[CSV-TEST] saved: {os.path.basename(test_path)} (2 rows)")


def _convert_msg_to_html(
    msg_path: str,
    output_html: str,
    token_mapping: dict | None,
    logger: ProcessLogger,
) -> bool:
    """Convert .msg to HTML via win32com, with token replacement."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
    except Exception as e:
        logger.log(f"[HTML] could not connect to Outlook: {e}")
        pythoncom.CoUninitialize()
        return False

    short_path = _get_short_path(msg_path)
    try:
        msg = namespace.OpenSharedItem(short_path)
    except Exception as e:
        logger.log(f"[HTML] could not open .msg: {e}")
        pythoncom.CoUninitialize()
        return False

    html_body = msg.HTMLBody or ""
    subject = msg.Subject or ""

    try:
        msg.Close(0)
    except Exception:
        pass

    pythoncom.CoUninitialize()

    if not html_body:
        logger.log("[HTML] no HTMLBody found")
        return False

    # Insert subject line
    safe_subject = subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    subject_block = (
        f"<p class=MsoNormal><b><span lang=ZH-CN\n"
        f"style='font-family:等线;mso-hansi-font-family:Calibri;mso-bidi-font-family:等线;\n"
        f"color:black'>主题</span></b><span style='font-family:等线;mso-hansi-font-family:Calibri;\n"
        f"mso-bidi-font-family:等线;color:black'>: {safe_subject}</span></p>\n"
        f"\n"
        f"<p class=MsoNormal><o:p>&nbsp;</o:p></p>\n"
    )
    body_pos = html_body.lower().find("<body")
    if body_pos > 0:
        body_close = html_body.find(">", body_pos)
        if body_close > 0:
            html_body = html_body[:body_close + 1] + "\n" + subject_block + html_body[body_close + 1:]

    # Token replacement
    if token_mapping:
        html_body = replace_span_tokens(html_body, token_mapping)

    # Remove _MailOriginal anchor, add blank line
    html_body = re.sub(
        r'<a\s+name="_MailOriginal">\s*<span[^>]*>\s*<o:p>\s*&nbsp;\s*</o:p>\s*</span>\s*</a>\s*</p>',
        "<p class=MsoNormal><o:p>&nbsp;</o:p></p>",
        html_body,
        flags=re.DOTALL | re.IGNORECASE,
    )

    with open(output_html, "w", encoding="utf-8", newline="") as f:
        f.write(html_body)

    # Save combined head+body
    head_match = re.search(r"<head[^>]*>(.*?)</head>", html_body, re.DOTALL | re.IGNORECASE)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_body, re.DOTALL | re.IGNORECASE)
    if head_match and body_match:
        combined_path = output_html.replace(".html", "_combined.html")
        combined = head_match.group(1) + body_match.group(1)
        with open(combined_path, "w", encoding="utf-8", newline="") as f:
            f.write(combined)
        size_kb = os.path.getsize(combined_path) / 1024
        logger.log(f"[HTML-COMBINED] saved: {os.path.basename(combined_path)} ({size_kb:.1f} KB)")

    size_kb = os.path.getsize(output_html) / 1024
    logger.log(f"[HTML] saved: {os.path.basename(output_html)} ({size_kb:.1f} KB)")
    return True


# ---------------------------------------------------------------------------
# Main processing thread
# ---------------------------------------------------------------------------


def _process(
    logger: ProcessLogger,
    msg_path: str,
    xlsx_path: str,
    tokenmap_override: str | None,
    on_done: callable,
    on_error: callable,
):
    try:
        from extract_msg import Message as MsgParser
    except ImportError:
        on_error("Missing dependency 'extract-msg'. Run: pip install extract-msg")
        return

    logger.log("=== EDM Processing Started ===")
    logger.log(f"MSG file: {msg_path}")
    logger.log(f"XLSX file: {xlsx_path}")

    # Step 1: Extract SN
    msg = MsgParser(msg_path)
    subject = msg.subject or ""
    logger.log(f"Subject: {subject}")

    sn = extract_sn(subject)
    if not sn:
        sn = extract_sn(msg_path)
    if not sn:
        msg.close()
        on_error("No SN number found. Subject or filename should contain SN-xxxxx.")
        return

    logger.log(f"SN extracted: {sn}")

    # Step 2: Create folder
    sn_folder = os.path.join(OUTPUT_BASE, sn)
    os.makedirs(sn_folder, exist_ok=True)
    if os.listdir(sn_folder):
        logger.log(f"Output folder already existed: {sn_folder}")
    logger.log(f"Output folder: {sn_folder}")

    # Step 3: Copy xlsx & convert to CSV
    xlsx_dst = os.path.join(sn_folder, os.path.basename(xlsx_path))
    shutil.copy2(xlsx_path, xlsx_dst)
    logger.log(f"[COPY] {os.path.basename(xlsx_path)} -> {sn}/")
    _convert_xlsx_to_csv(xlsx_dst, logger)

    # Step 4: Generate formal & test CSVs
    _generate_formal_test_csv(xlsx_dst, logger)

    # Step 5: Extract nested .msg
    target_idx = find_target_attachment_idx(msg_path)
    attach_path = None
    if target_idx is not None and target_idx < len(msg.attachments):
        matched_att = msg.attachments[target_idx]
        attach_path = save_target_attachment(matched_att, sn_folder)
        logger.log(f"[ATTACH] saved nested .msg")
    else:
        logger.log("[ATTACH] no nested .msg found, skipping HTML conversion")
    msg.close()

    # Step 6: Convert to HTML
    if attach_path:
        logger.log("[HTML] converting to HTML via Outlook...")
        html_path = os.path.join(sn_folder, "EDM_template.html")

        # Token mapping
        tokenmap_path, token_mapping = find_tokenmap(tokenmap_override)
        if tokenmap_path:
            logger.log(f"[TOKEN] loaded {len(token_mapping)} tokens from {os.path.basename(tokenmap_path)}")
        else:
            logger.log("[TOKEN] Tokenmapping.json not found, skipping token replacement")

        success = _convert_msg_to_html(attach_path, html_path, token_mapping, logger)
        if not success:
            logger.log("[HTML] conversion failed")

    # Step 7: Write log
    log_path = os.path.join(sn_folder, "process.log")
    logger.log("=== Processing Complete ===")
    logger.log(f"Output folder: {sn_folder}")
    logger.write_file(log_path)

    on_done(sn_folder)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class EDMGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EDM Email Processor")
        self.root.geometry("750x540")
        self.root.minsize(640, 400)

        # State
        self.msg_var = tk.StringVar()
        self.xlsx_var = tk.StringVar()
        self.tokenmap_var = tk.StringVar()
        self.last_sn_folder = None

        self._detect_tokenmap()
        self._build_ui()

    def _detect_tokenmap(self):
        path, mapping = find_tokenmap()
        if path:
            self.tokenmap_var.set(path)
        else:
            self.tokenmap_var.set("")

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#333333")
        style.configure("Title.TLabel", font=("", 14, "bold"), foreground="#222222")
        style.configure("TButton", padding=(10, 4), font=("", 9))
        style.configure("Action.TButton", font=("", 10, "bold"), padding=(16, 8))
        style.configure("Log.TText", font=("Consolas", 9), background="#f5f5f5", foreground="#222222")
        style.map("TButton", background=[("active", "#e0e0e0")])
        style.map("Action.TButton", background=[("active", "#3b82f6")])

        # Main container
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        # Title
        ttk.Label(main, text="EDM Email Processor", style="Title.TLabel").pack(
            anchor="w", pady=(0, 16)
        )

        # Input files
        input_frame = ttk.LabelFrame(main, text="Input Files", padding=12)
        input_frame.pack(fill="x", pady=(0, 12))

        # MSG row
        ttk.Label(input_frame, text="MSG File:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        msg_entry = ttk.Entry(input_frame, textvariable=self.msg_var, width=55, state="readonly")
        msg_entry.grid(row=0, column=1, padx=(0, 6))
        ttk.Button(input_frame, text="Browse...", command=self._browse_msg).grid(row=0, column=2)

        # XLSX row
        ttk.Label(input_frame, text="XLSX File:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        xlsx_entry = ttk.Entry(input_frame, textvariable=self.xlsx_var, width=55, state="readonly")
        xlsx_entry.grid(row=1, column=1, padx=(0, 6), pady=(8, 0))
        ttk.Button(input_frame, text="Browse...", command=self._browse_xlsx).grid(row=1, column=2, pady=(8, 0))

        # Info row
        info_frame = ttk.LabelFrame(main, text="Settings", padding=12)
        info_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(info_frame, text="Output:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(info_frame, text=OUTPUT_BASE, foreground="#666666", font=("Consolas", 9)).grid(
            row=0, column=1, columnspan=2, sticky="w"
        )

        ttk.Label(info_frame, text="Tokenmap:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        tk.Label(
            info_frame,
            textvariable=self.tokenmap_var if self.tokenmap_var.get() else tk.StringVar(value="Tokenmapping.json  "),
            fg="#22c55e" if self.tokenmap_var.get() else "#ef4444",
            font=("", 9),
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Button(info_frame, text="Override...", command=self._browse_tokenmap).grid(
            row=1, column=2, pady=(6, 0)
        )

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 12))

        self.process_btn = ttk.Button(
            btn_frame, text="  Process  ", command=self._run_process, style="Action.TButton"
        )
        self.process_btn.pack(side="left")

        self.open_btn = ttk.Button(
            btn_frame, text="Open Output Folder", command=self._open_folder, state="disabled"
        )
        self.open_btn.pack(side="right")

        # Log
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=14, wrap="word", state="disabled",
                                font=("Consolas", 9), bg="#f5f5f5", fg="#222222",
                                insertborderwidth=0, relief="flat")
        self.log_text.pack(fill="both", expand=True)

    def _browse_msg(self):
        path = filedialog.askopenfilename(
            title="Select MSG File",
            filetypes=[("MSG files", "*.msg"), ("All files", "*.*")],
        )
        if path:
            self.msg_var.set(path)

    def _browse_xlsx(self):
        path = filedialog.askopenfilename(
            title="Select XLSX File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if path:
            self.xlsx_var.set(path)

    def _browse_tokenmap(self):
        path = filedialog.askopenfilename(
            title="Select Tokenmapping.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.tokenmap_var.set(path)

    def _run_process(self):
        msg_path = self.msg_var.get().strip()
        xlsx_path = self.xlsx_var.get().strip()
        tokenmap = self.tokenmap_var.get().strip() or None

        if not msg_path or not os.path.isfile(msg_path):
            messagebox.showerror("Error", "Please select a valid .msg file.")
            return
        if not xlsx_path or not os.path.isfile(xlsx_path):
            messagebox.showerror("Error", "Please select a valid .xlsx file.")
            return

        self.process_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        logger = ProcessLogger(self.root, self.log_text)

        def on_done(sn_folder):
            self.last_sn_folder = sn_folder
            self.root.after(0, lambda: self.process_btn.config(state="normal"))
            self.root.after(0, lambda: self.open_btn.config(state="normal"))
            self.root.after(0, lambda: messagebox.showinfo("Done", f"Processing complete for {sn_folder.split('/')[-1]}"))

        def on_error(msg):
            logger.log(f"ERROR: {msg}")
            logger.write_file(os.path.join(OUTPUT_BASE, "error.log"))
            self.root.after(0, lambda: self.process_btn.config(state="normal"))
            self.root.after(0, lambda: messagebox.showerror("Error", msg))

        thread = threading.Thread(
            target=_process,
            args=(logger, msg_path, xlsx_path, tokenmap, on_done, on_error),
            daemon=True,
        )
        thread.start()

    def _open_folder(self):
        if self.last_sn_folder:
            os.startfile(self.last_sn_folder)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = EDMGUI()
    app.run()
