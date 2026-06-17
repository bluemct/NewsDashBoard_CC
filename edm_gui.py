"""
EDM Email Processor — Windows GUI Tool

Standalone tkinter application for processing EDM emails:
- Extract SN from .msg, create folder in output directory
- Extract nested .msg (0 recipients), convert to HTML with token replacement
- Generate formal and test CSVs
- Log all steps to process.log

Output (exactly 5 files):
  1. Nested .msg
  2. EDM_template.html
  3. formal_*.csv
  4. test_*.csv
  5. process.log

Usage:
    python edm_gui.py

Config files (same directory as this script/exe):
    config.json        — test email addresses
    Tokenmapping.json  — token name→value mappings
"""
import csv
import glob
import json
import os
import re
import shutil
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------
# Resolve script directory — works for both .py and PyInstaller .exe
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Running as PyInstaller exe — config files are next to the exe
    _SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Import core functions from edm_process
# ---------------------------------------------------------------------------
_SKILL_DIR = os.path.join(_SCRIPT_DIR, ".claude", "skills", "edm-process")
if not getattr(sys, "frozen", False) and _SKILL_DIR not in sys.path:
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
# Import xlsx_to_csv functions directly (no subprocess needed)
# ---------------------------------------------------------------------------
_XLSX_SKILL_DIR = os.path.join(_SCRIPT_DIR, ".claude", "skills", "xlsx-to-csv")
if not getattr(sys, "frozen", False) and _XLSX_SKILL_DIR not in sys.path:
    sys.path.insert(0, _XLSX_SKILL_DIR)

try:
    from xlsx_to_csv import xlsx_to_csv as _xlsx_to_csv
except ImportError as e:
    print(f"Warning: Could not import xlsx_to_csv: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_BASE = os.path.join(os.path.expanduser("~"), "Desktop", "EDM")

CONFIG_PATH = os.path.join(_SCRIPT_DIR, "config.json")
TOKENMAP_PATH = os.path.join(_SCRIPT_DIR, "Tokenmapping.json")

# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config.json from script directory. Returns defaults if missing."""
    defaults = {
        "test_emails": [
            "ma.chuntao@oe.21vianet.com",
            "microsoft.163163@163.com",
        ]
    }
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    return defaults

def _load_tokenmap() -> dict:
    """Load Tokenmapping.json from script directory. Returns empty dict if missing."""
    if not os.path.isfile(TOKENMAP_PATH):
        return {}
    with open(TOKENMAP_PATH, "r", encoding="utf-8") as f:
        mapping_list = json.load(f)
    return {item["Name"]: item["Value"] for item in mapping_list}

def _load_raw_json(path: str) -> str | None:
    """Return raw file content or None."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

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


def _convert_xlsx_to_csv(xlsx_path: str, logger: ProcessLogger) -> bool:
    """Convert xlsx to CSV using openpyxl directly (no subprocess)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.log("[CSV] openpyxl not available")
        return False

    try:
        wb = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
        sheet_name = wb.sheetnames[0]
        ws = wb[sheet_name]

        csv_path = os.path.splitext(xlsx_path)[0] + ".csv"
        encodings_to_try = ["gb18030", "utf-8"]
        success = False

        try:
            for enc in encodings_to_try:
                try:
                    with open(csv_path, "w", encoding=enc, errors="replace", newline="") as f:
                        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
                        for row in ws.iter_rows(values_only=True):
                            str_row = [""] if row == [None] else [str(c) if c is not None else "" for c in row]
                            writer.writerow(str_row)
                    success = True
                    logger.log(f"[CSV] {os.path.basename(csv_path)} ({enc})")
                    break
                except UnicodeEncodeError:
                    continue

            if not success:
                logger.log("[CSV] all encodings failed")
        finally:
            wb.close()

        return success
    except Exception as e:
        logger.log(f"[CSV] xlsx_to_csv failed: {e}")
        return False


def _generate_formal_test_csv(xlsx_path: str, config: dict, logger: ProcessLogger) -> None:
    """Generate formal_*.csv (all rows) and test_*.csv (2 rows) from the source CSV."""
    sn_dir = os.path.dirname(xlsx_path)
    base = os.path.splitext(os.path.basename(xlsx_path))[0]

    csv_files = glob.glob(os.path.join(sn_dir, base + "*.csv"))
    csv_path = csv_files[0] if csv_files else None
    if not csv_path or not os.path.exists(csv_path):
        logger.log("[CSV] no source CSV found for formal/test generation")
        return

    with open(csv_path, encoding="gb18030", newline="") as f:
        reader = list(csv.reader(f))
        header = reader[0]
        rows = reader[1:]

    # Formal CSV — copy all rows
    formal_path = os.path.join(sn_dir, f"formal_{base}.csv")
    shutil.copy2(csv_path, formal_path)
    logger.log(f"[CSV-FORMAL] saved: {os.path.basename(formal_path)} ({len(rows)} rows)")

    # Test CSV — pick rows with most tokens filled, replace email column
    test_emails = config.get("test_emails", [
        "ma.chuntao@oe.21vianet.com",
        "microsoft.163163@163.com",
    ])
    test_count = max(len(test_emails), 2)

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

    # Collect up to test_count distinct rows (round-robin from top-scored)
    selected = []
    idx = 0
    while len(selected) < test_count:
        if idx < len(row_scores):
            selected.append(list(row_scores[idx][2]))
        elif len(rows) > len(selected):
            selected.append(list(rows[len(selected)]))
        else:
            selected.append(["" for _ in header])
        idx += 1

    if email_idx is not None:
        for i, row in enumerate(selected):
            if i < len(test_emails):
                row[email_idx] = test_emails[i]

    test_path = os.path.join(sn_dir, f"test_{base}.csv")
    with open(test_path, "w", encoding="gb18030", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in selected:
            writer.writerow(row)
    logger.log(f"[CSV-TEST] saved: {os.path.basename(test_path)} ({len(selected)} rows)")

    # Clean up raw CSV — only keep formal_ and test_
    os.remove(csv_path)
    logger.log(f"[CLEANUP] removed raw CSV: {os.path.basename(csv_path)}")


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

    with open(output_html, "wb") as f:
        f.write(html_body.encode("utf-8"))

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
    output_base: str,
    config: dict,
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
    sn_folder = os.path.join(output_base, sn)
    os.makedirs(sn_folder, exist_ok=True)
    logger.log(f"Output folder: {sn_folder}")

    # Step 3: Copy xlsx & convert to CSV
    xlsx_dst = os.path.join(sn_folder, os.path.basename(xlsx_path))
    shutil.copy2(xlsx_path, xlsx_dst)
    logger.log(f"[COPY] {os.path.basename(xlsx_path)} -> {sn}/")
    _convert_xlsx_to_csv(xlsx_dst, logger)

    # Step 4: Generate formal & test CSVs (removes raw CSV)
    _generate_formal_test_csv(xlsx_dst, config, logger)

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

        token_mapping = _load_tokenmap()
        if token_mapping:
            logger.log(f"[TOKEN] loaded {len(token_mapping)} tokens from Tokenmapping.json")
        else:
            logger.log("[TOKEN] Tokenmapping.json not found, skipping token replacement")

        success = _convert_msg_to_html(attach_path, html_path, token_mapping, logger)
        if not success:
            logger.log("[HTML] conversion failed")

    # Step 7: Write log
    logger.log("=== Processing Complete ===")
    logger.log(f"Output folder: {sn_folder}")
    log_path = os.path.join(sn_folder, "process.log")
    logger.write_file(log_path)

    on_done(sn_folder)


# ---------------------------------------------------------------------------
# Config Editor Dialog
# ---------------------------------------------------------------------------

class ConfigEditorDialog:
    """Simple modal dialog to view/edit a JSON file."""

    def __init__(self, parent: tk.Tk, title: str, path: str, content: str | None):
        self.path = path
        self.result = None

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("500x400")
        self.win.resizable(True, True)
        self.win.transient(parent)
        self.win.grab_set()

        # Center on parent
        self.win.focus_set()

        # Top bar — title + buttons
        top = ttk.Frame(self.win, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text=f"{os.path.basename(path)}").pack(side="left", anchor="w", expand=True)

        if content is None:
            ttk.Label(top, text="File not found — creating new.", foreground="#e67e22").pack(side="left", padx=(0, 8))

        ttk.Button(top, text="Save", command=lambda: self._save(text)).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Cancel", command=self.win.destroy).pack(side="right")

        # Text area with scrollbar
        text_frame = ttk.Frame(self.win)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        sb = ttk.Scrollbar(text_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        text = tk.Text(text_frame, font=("Consolas", 9), wrap="word",
                       padx=6, pady=6, yscrollcommand=sb.set)
        text.pack(fill="both", expand=True)
        sb.config(command=text.yview)

        if content:
            text.insert("1.0", content)
        else:
            # Default template based on file name
            if "tokenmap" in os.path.basename(path).lower():
                text.insert("1.0", "[\n  {\n    \"Name\": \"\",\n    \"Value\": \"\"\n  }\n]\n")
            else:
                text.insert("1.0", "{\n  \"test_emails\": [\n    \"\",\n    \"\"\n  ]\n}\n")

    def _save(self, text_widget: tk.Text):
        raw = text_widget.get("1.0", "end-1c")
        try:
            # Validate JSON
            parsed = json.loads(raw)
            # Re-format for consistency
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(formatted + "\n")
            self.result = parsed
        except json.JSONDecodeError as e:
            messagebox.showerror("Invalid JSON", str(e), parent=self.win)
            return
        self.win.destroy()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class EDMGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EDM Email Processor")
        self.root.geometry("800x600")
        self.root.minsize(640, 450)

        # State
        self.msg_var = tk.StringVar()
        self.xlsx_var = tk.StringVar()
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT_BASE)
        self.last_sn_folder = None
        self._config_widgets = {}
        self.config_collapsed = False

        self._build_ui()

        # Window resize handler — auto-collapse config when window is small
        self.root.bind("<Configure>", self._on_resize)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#333333")
        style.configure("Title.TLabel", font=("", 14, "bold"), foreground="#222222")
        style.configure("TButton", padding=(10, 4), font=("", 9))
        style.configure("Action.TButton", font=("", 10, "bold"), padding=(16, 8))
        style.configure("Status.TLabel", font=("Consolas", 9))
        style.map("TButton", background=[("active", "#e0e0e0")])
        style.map("Action.TButton", background=[("active", "#3b82f6")])

        # Main container
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        # Title
        ttk.Label(main, text="EDM Email Processor", style="Title.TLabel").pack(
            anchor="w", pady=(0, 10)
        )

        # Input files
        input_frame = ttk.LabelFrame(main, text="Input Files", padding=8)
        input_frame.pack(fill="x", pady=(0, 6))
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="MSG File:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        msg_entry = ttk.Entry(input_frame, textvariable=self.msg_var, width=30, state="readonly")
        msg_entry.grid(row=0, column=1, padx=(0, 6), sticky="ew")
        ttk.Button(input_frame, text="Browse...", command=self._browse_msg).grid(row=0, column=2, sticky="e")

        ttk.Label(input_frame, text="XLSX File:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(4, 0))
        xlsx_entry = ttk.Entry(input_frame, textvariable=self.xlsx_var, width=30, state="readonly")
        xlsx_entry.grid(row=1, column=1, padx=(0, 6), pady=(4, 0), sticky="ew")
        ttk.Button(input_frame, text="Browse...", command=self._browse_xlsx).grid(row=1, column=2, sticky="e", pady=(4, 0))

        # Output folder
        output_frame = ttk.LabelFrame(main, text="Output", padding=8)
        output_frame.pack(fill="x", pady=(0, 6))
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="Folder:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        out_entry = ttk.Entry(output_frame, textvariable=self.output_var, width=30, state="readonly")
        out_entry.grid(row=0, column=1, padx=(0, 6), sticky="ew")
        ttk.Button(output_frame, text="Browse...", command=self._browse_output).grid(row=0, column=2, sticky="e")

        # Config section — collapsible
        config_outer = ttk.Frame(main)
        config_outer.pack(fill="x", pady=(0, 6))

        self.config_frame = ttk.LabelFrame(config_outer, text="Config", padding=6)
        self.config_frame.pack(fill="x")

        # Notebook for two tabs
        self.config_notebook = ttk.Notebook(self.config_frame)
        self.config_notebook.pack(fill="x")

        # Tab 1: Test Emails
        self.tab_config = ttk.Frame(self.config_notebook, padding=4)
        self.config_notebook.add(self.tab_config, text="  Test Emails  ")

        self._build_config_tab(self.tab_config, "config.json", _load_raw_json(CONFIG_PATH))

        # Tab 2: Tokenmapping
        self.tab_token = ttk.Frame(self.config_notebook, padding=4)
        self.config_notebook.add(self.tab_token, text="  Tokenmapping  ")

        self._build_config_tab(self.tab_token, "Tokenmapping.json", _load_raw_json(TOKENMAP_PATH))

        # Config toggle button
        self.config_toggle_btn = ttk.Button(
            config_outer, text="▼ Collapse Config", command=self._toggle_config
        )
        # Start collapsed so Process button is always visible
        self._toggle_config()

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 10))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=2)
        btn_frame.columnconfigure(2, weight=1)

        self.process_btn = ttk.Button(
            btn_frame, text="  Process  ", command=self._run_process, style="Action.TButton"
        )
        self.process_btn.grid(row=0, column=1, pady=4, sticky="ew")

        self.open_btn = ttk.Button(
            btn_frame, text="Open Output Folder", command=self._open_folder, state="disabled"
        )
        self.open_btn.grid(row=0, column=2, pady=4, sticky="e")

        # Log
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled",
                                font=("Consolas", 9), bg="#f5f5f5", fg="#222222",
                                insertborderwidth=0, relief="flat")
        self.log_text.pack(fill="both", expand=True)

    def _build_config_tab(self, parent: ttk.Frame, label: str, raw_content: str | None):
        """Build a config tab with a read-only preview and Edit button."""
        status_text = _format_config_status(label, raw_content)
        status = tk.Label(
            parent, text=status_text, justify="left", anchor="w",
            font=("Consolas", 9), fg="#222222", bg="#ffffff"
        )
        status.pack(fill="x", pady=(0, 6))

        # Read-only content preview with scrollbar
        inner = ttk.Frame(parent)
        inner.pack(fill="x", pady=(0, 6))

        sb = ttk.Scrollbar(inner, orient="vertical")
        sb.pack(side="right", fill="y")

        preview = tk.Text(inner, height=4, wrap="word", state="disabled",
                          font=("Consolas", 9), bg="#f5f5f5", fg="#333333",
                          insertborderwidth=0, relief="flat", padx=4, pady=4,
                          yscrollcommand=sb.set)
        preview.pack(side="left", fill="x", expand=True)
        sb.config(command=preview.yview)

        if raw_content:
            formatted = json.dumps(json.loads(raw_content), indent=2, ensure_ascii=False)
        else:
            formatted = "(file not found)"
        preview.config(state="normal")
        preview.insert("1.0", formatted)
        preview.config(state="disabled")

        ttk.Button(parent, text="Edit...", command=lambda: self._edit_config(label)).pack(
            anchor="w", pady=(4, 0)
        )

        # Store references for refresh
        self._config_widgets[label] = {"status": status, "preview": preview}

    def _edit_config(self, label: str):
        path = CONFIG_PATH if label == "config.json" else TOKENMAP_PATH
        content = _load_raw_json(path)
        dialog = ConfigEditorDialog(self.root, f"Edit {label}", path, content)
        self.root.wait_window(dialog.win)
        if dialog.result is not None:
            self._refresh_config_preview(label)

    def _refresh_config_preview(self, label: str):
        """Update the status label and preview text after editing."""
        path = CONFIG_PATH if label == "config.json" else TOKENMAP_PATH
        raw = _load_raw_json(path)

        widgets = self._config_widgets.get(label)
        if not widgets:
            return

        widgets["status"].config(text=_format_config_status(label, raw))

        preview = widgets["preview"]
        if raw:
            formatted = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        else:
            formatted = "(file not found)"
        preview.config(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", formatted)
        preview.config(state="disabled")

    def _toggle_config(self):
        self.config_collapsed = not self.config_collapsed
        if self.config_collapsed:
            self.config_frame.pack_forget()
            self.config_toggle_btn.config(text="▶ Expand Config")
        else:
            self.config_frame.pack(fill="x")
            self.config_toggle_btn.config(text="▼ Collapse Config")

    def _on_resize(self, event):
        """Auto-collapse/expand config panel based on window height."""
        if event.widget is self.root:
            if event.height < 450 and not self.config_collapsed:
                self._toggle_config()
            elif event.height >= 480 and self.config_collapsed:
                self._toggle_config()

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

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_var.set(path)

    def _run_process(self):
        msg_path = self.msg_var.get().strip()
        xlsx_path = self.xlsx_var.get().strip()
        output_base = self.output_var.get().strip() or DEFAULT_OUTPUT_BASE

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
        config = _load_config()

        def on_done(sn_folder):
            self.last_sn_folder = sn_folder
            self.root.after(0, lambda: self.process_btn.config(state="normal"))
            self.root.after(0, lambda: self.open_btn.config(state="normal"))
            self.root.after(0, lambda: messagebox.showinfo("Done", f"Processing complete for {sn_folder.split('/')[-1]}"))

        def on_error(msg):
            logger.log(f"ERROR: {msg}")
            os.makedirs(output_base, exist_ok=True)
            logger.write_file(os.path.join(output_base, "error.log"))
            self.root.after(0, lambda: self.process_btn.config(state="normal"))
            self.root.after(0, lambda: messagebox.showerror("Error", msg))

        thread = threading.Thread(
            target=_process,
            args=(logger, msg_path, xlsx_path, output_base, config, on_done, on_error),
            daemon=True,
        )
        thread.start()

    def _open_folder(self):
        if self.last_sn_folder:
            os.startfile(self.last_sn_folder)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Helpers for config display
# ---------------------------------------------------------------------------

def _format_config_status(label: str, raw: str | None) -> str:
    if raw is None:
        return f"{label}: not found"
    try:
        data = json.loads(raw)
        if label == "config.json":
            emails = data.get("test_emails", [])
            parts = [f"{label}: {len(emails)} email(s)"]
            for e in emails:
                parts.append(f"  → {e}")
            return "\n".join(parts)
        else:
            count = len(data) if isinstance(data, list) else len(data)
            return f"{label}: {count} token(s)"
    except json.JSONDecodeError:
        return f"{label}: invalid JSON"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = EDMGUI()
    app.run()
