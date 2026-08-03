"""EDM module for EML — Full EML-only workflow, no Outlook COM dependency.

Drop-in replacement for routes/edm.py.
- No .eml → .msg conversion (skips Outlook COM CreateItem)
- xlsx discover from .eml HTML body (pure Python)
- edm_process_eml.py for processing (pure Python, no OpenSharedItem)

No Outlook COM / win32com required.
"""
import os
import sys
import json
import re
import shutil
import time
import logging
import subprocess
import threading
import email as email_lib
from datetime import datetime
from urllib import parse as urllib_parse

from flask import Blueprint, jsonify, current_app, Response, request
from routes.auth import require_auth
from utils import task_queue

logger = logging.getLogger(__name__)

edm_eml_bp = Blueprint('edm_eml', __name__, url_prefix='/api/edm')

# ---------------------------------------------------------------------------
# Listener state
# ---------------------------------------------------------------------------
_listener_proc: subprocess.Popen | None = None
_listener_thread: threading.Thread | None = None
_listener_lock = threading.Lock()

TARGET_SENDER = "ma.chuntao"
KEYWORD = "EDM Agent"

# Cached at import time so background threads can use it without Flask context.
# Updated by _set_project_root() during app startup.
_project_root: str | None = None


def _set_project_root(path: str):
    """Call during app startup to set the project root for background threads."""
    global _project_root
    _project_root = path


def _get_project_root():
    """Get project root. Works inside and outside Flask context."""
    if _project_root:
        return _project_root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_config():
    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_ews_config():
    """Load EWS config from .edm_agent_config.json."""
    project_root = _get_project_root()
    ews_config_path = os.path.join(project_root, ".edm_agent_config.json")
    with open(ews_config_path, 'r', encoding='utf-8') as f:
        return json.load(f)["ews"]


def _add_event(event: dict):
    """Add a detection event to the database."""
    event_type = event.get("type", "info")
    event_time = event.get("time", datetime.now().isoformat())
    task_queue.save_event(
        event_time=event_time,
        event_type=event_type,
        message=event.get("message", ""),
        subject=event.get("subject", ""),
        from_addr=event.get("from", ""),
        sn=event.get("sn", ""),
    )


# ---------------------------------------------------------------------------
# Streaming listener — launches ews_streaming.ps1 and reads JSON events
# ---------------------------------------------------------------------------

def _listener_reader():
    """Background thread: read JSON events from PowerShell streaming subprocess."""
    project_root = _get_project_root()
    temp_dir = os.path.join(project_root, "EDM", "Temp")
    os.makedirs(temp_dir, exist_ok=True)

    config_path = os.path.join(project_root, ".edm_agent_config.json")
    ps_script = os.path.join(project_root, "ews_streaming.ps1")
    dll_path_40 = os.path.join(project_root, "EWS", "lib", "40", "Microsoft.Exchange.WebServices.dll")
    dll_path_35 = os.path.join(project_root, "EWS", "extracted", "lib", "net35", "Microsoft.Exchange.WebServices.dll")

    if not os.path.isfile(ps_script):
        msg = f"Streaming script not found: {ps_script}"
        logger.error(f"[edm-listener] {msg}")
        _add_event({"time": datetime.now().isoformat(), "type": "error", "message": msg})
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        ews = cfg["ews"]
    except Exception as e:
        msg = f"无法读取配置: {e}"
        logger.error(f"[edm-listener] {msg}")
        _add_event({"time": datetime.now().isoformat(), "type": "error", "message": msg})
        return

    ps_args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", ps_script,
        '-EwsUrl', ews["url"],
        '-DomainUser', ews["domain_user"],
        '-Password', ews["password"],
        '-FolderName', ews.get("folder_name", "EDM"),
    ]

    if os.path.isfile(dll_path_40):
        ps_args += ['-DllPath', dll_path_40]
    elif os.path.isfile(dll_path_35):
        ps_args += ['-DllPath', dll_path_35]

    logger.info(f"[edm-listener] Launching: {' '.join(ps_args[:6])} ...")
    _add_event({"time": datetime.now().isoformat(), "type": "info", "message": "正在启动 EWS Streaming ..."})

    try:
        proc = subprocess.Popen(
            ps_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception as e:
        msg = f"启动 PowerShell 失败: {e}"
        logger.error(f"[edm-listener] {msg}")
        _add_event({"time": datetime.now().isoformat(), "type": "error", "message": msg})
        return

    with _listener_lock:
        global _listener_proc
        _listener_proc = proc

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            with _listener_lock:
                should_stop = _listener_proc is None
            if should_stop:
                break

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"[edm-listener] PS output: {line[:200]}")
                continue

            etype = event.get("type", "")

            if etype == "connected":
                sub_id = event.get("subscription_id", "")
                logger.info(f"[edm-listener] Streaming connected: {sub_id}")
                _add_event({"time": datetime.now().isoformat(), "type": "info", "message": "EWS Streaming 连接成功，正在监听..."})

            elif etype == "newmail":
                item_id = event.get("item_id", "")
                subject = event.get("subject", "")
                sender = event.get("from", event.get("sender", ""))
                has_attachments = event.get("has_attachments", False)

                logger.info(f"[edm-listener] [Event] ItemReceived: {subject} from {sender}")
                _add_event({
                    "time": datetime.now().isoformat(),
                    "type": "info",
                    "message": f"收到邮件事件: {subject}",
                    "subject": subject,
                    "from": sender,
                    "has_attachments": has_attachments,
                })

                if TARGET_SENDER not in sender.lower():
                    logger.debug(f"[edm-listener] Skipped (sender={sender})")
                    continue

                # Download MIME to check keyword
                mime_bytes = _get_mime_content(_load_ews_config(), item_id)
                if not mime_bytes:
                    logger.warning(f"[edm-listener] No MIME content for {item_id}")
                    continue

                # Check keyword in body
                emsg = email_lib.message_from_bytes(mime_bytes)
                text_body = _extract_text_body(mime_bytes)
                if KEYWORD not in text_body:
                    logger.debug(f"[edm-listener] Skipped (keyword not in body)")
                    continue

                # Matched! Save to EDM/Temp/
                sn = _extract_sn_from_subject(subject)
                if sn:
                    filename = f"{sn}_email.eml"
                else:
                    filename = f"edm_agent_{item_id[:12]}.eml"

                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(mime_bytes)

                logger.info(f"[edm-listener] [OK] {filename} | {subject}")
                _add_event({
                    "time": datetime.now().isoformat(),
                    "type": "success",
                    "message": f"检测到新邮件: {filename}",
                    "subject": subject,
                    "from": sender,
                    "sn": sn,
                })

            elif etype == "error":
                err_msg = event.get("message", "")
                logger.error(f"[edm-listener] Streaming error: {err_msg}")
                _add_event({"time": datetime.now().isoformat(), "type": "error", "message": f"Streaming 错误: {err_msg}"})

            elif etype == "disconnected":
                logger.warning("[edm-listener] Streaming disconnected")
                _add_event({"time": datetime.now().isoformat(), "type": "error", "message": "Streaming 连接断开"})
                break

    except Exception as e:
        logger.error(f"[edm-listener] Reader error: {e}")
        _add_event({"time": datetime.now().isoformat(), "type": "error", "message": f"读取错误: {e}"})
    finally:
        with _listener_lock:
            if _listener_proc is not None and _listener_proc.poll() is None:
                try:
                    _listener_proc.terminate()
                except Exception:
                    pass
            _listener_proc = None


# ---------------------------------------------------------------------------
# EWS helpers (for downloading MIME content after event received)
# ---------------------------------------------------------------------------
T = "http://schemas.microsoft.com/exchange/services/2006/types"
M = "http://schemas.microsoft.com/exchange/services/2006/messages"
S = "http://schemas.xmlsoap.org/soap/envelope/"


def _ews_soap(cfg, body_xml: str):
    """Send EWS SOAP request, return parsed root."""
    import requests
    from requests_ntlm import HttpNtlmAuth
    from xml.etree import ElementTree as ET

    envelope = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="{M}"
               xmlns:t="{T}"
               xmlns:soap="{S}">
  <soap:Header><t:RequestServerVersion Version="Exchange2013"/></soap:Header>
  <soap:Body>{body_xml}</soap:Body>
</soap:Envelope>'''
    sess = requests.Session()
    sess.auth = HttpNtlmAuth(cfg["domain_user"], cfg["password"])
    r = sess.post(
        cfg["url"],
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"},
        timeout=60,
    )
    r.raise_for_status()
    return ET.fromstring(r.text)


def _get_mime_content(cfg, item_id: str) -> bytes:
    """Download full MIME content for an email item."""
    import base64
    body = f'''<m:GetItem>
      <m:ItemShape>
        <t:BaseShape>IdOnly</t:BaseShape>
        <t:AdditionalProperties>
          <t:FieldURI FieldURI="item:MimeContent"/>
        </t:AdditionalProperties>
      </m:ItemShape>
      <m:ItemIds><t:ItemId Id="{item_id}"/></m:ItemIds>
    </m:GetItem>'''
    root = _ews_soap(cfg, body)
    msgs = root.findall(f".//{{{M}}}GetItemResponseMessage/{{{M}}}Items/{{{T}}}Message")
    if not msgs:
        return b""
    mime_el = msgs[0].find(f"{{{T}}}MimeContent")
    if mime_el is not None and mime_el.text:
        return base64.b64decode(mime_el.text)
    return b""


def _extract_text_body(mime_bytes: bytes) -> str:
    """Extract plain text body from MIME email."""
    msg = email_lib.message_from_bytes(mime_bytes)
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="ignore")
    return ""


def _extract_sn_from_subject(subject: str):
    """Extract SN-xxxxx from subject line."""
    m = re.search(r"SN\s*-\s*(\d+)", subject)
    return f"SN-{m.group(1)}" if m else None


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@edm_eml_bp.route('/listener/status', methods=['GET'])
@require_auth
def listener_status():
    with _listener_lock:
        proc = _listener_proc
        thread = _listener_thread

    is_running = (proc is not None and proc.poll() is None) or \
                 (thread is not None and thread.is_alive())
    return jsonify({
        "running": is_running,
        "mode": "streaming",
        "rules": {
            "sender": TARGET_SENDER,
            "keyword": KEYWORD,
            "has_attachments": True,
        },
    })


@edm_eml_bp.route('/listener/start', methods=['POST'])
@require_auth
def listener_start():
    global _listener_proc, _listener_thread
    with _listener_lock:
        if _listener_proc is not None and _listener_proc.poll() is None:
            return jsonify({"ok": True, "message": "监听器已在运行中"})
        if _listener_thread is not None and _listener_thread.is_alive():
            return jsonify({"ok": True, "message": "监听器已在运行中"})

    t = threading.Thread(target=_listener_reader, daemon=True)
    t.start()
    with _listener_lock:
        _listener_thread = t

    logger.info("[edm-listener] Streaming listener thread started")
    return jsonify({"ok": True, "message": "监听器已启动（Streaming 模式）"})


@edm_eml_bp.route('/listener/stop', methods=['POST'])
@require_auth
def listener_stop():
    global _listener_proc, _listener_thread
    with _listener_lock:
        if _listener_proc is not None and _listener_proc.poll() is None:
            try:
                _listener_proc.terminate()
            except Exception:
                pass
            _listener_proc = None
        _listener_thread = None
    logger.info("[edm-listener] Listener stopped by user")
    _add_event({"time": datetime.now().isoformat(), "type": "info", "message": "监听器已停止"})
    return jsonify({"ok": True, "message": "监听器已停止"})


@edm_eml_bp.route('/listener/events', methods=['GET'])
@require_auth
def listener_events():
    max_events = request.args.get('max', 50, type=int)
    events = task_queue.list_events(max_events)
    mapped = []
    for ev in events:
        mapped.append({
            "time": ev["event_time"],
            "type": ev["event_type"],
            "message": ev["message"],
            "subject": ev["subject"] or "",
            "from": ev["from_addr"] or "",
            "sn": ev["sn"] or "",
        })
    return jsonify({"events": mapped})


# ---------------------------------------------------------------------------
# Temp Files & History
# ---------------------------------------------------------------------------

@edm_eml_bp.route('/temp-files', methods=['GET'])
@require_auth
def temp_files():
    project_root = _get_project_root()
    temp_dir = os.path.join(project_root, "EDM", "Temp")
    if not os.path.isdir(temp_dir):
        return jsonify({"files": [], "message": "Temp directory not found"})

    processed = task_queue.processed_eml_files()

    files = []
    for f in sorted(os.listdir(temp_dir)):
        fp = os.path.join(temp_dir, f)
        if os.path.isfile(fp):
            stat = os.stat(fp)
            files.append({
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "ext": os.path.splitext(f)[1].lower(),
                "processed": f in processed,
                "processed_at": processed.get(f, ""),
            })
    return jsonify({"files": files})


@edm_eml_bp.route('/history', methods=['GET'])
@require_auth
def history():
    project_root = _get_project_root()
    edm_dir = os.path.join(project_root, "EDM")
    if not os.path.isdir(edm_dir):
        return jsonify({"history": []})

    processed = task_queue.processed_eml_files()
    processed_sns = set()
    for fname in processed:
        m = re.match(r"(SN-\d+)", fname)
        if m:
            processed_sns.add(m.group(1))

    sns = []
    for entry in sorted(os.listdir(edm_dir)):
        if entry.startswith("SN-"):
            fp = os.path.join(edm_dir, entry)
            if os.path.isdir(fp):
                files = [f for f in os.listdir(fp) if os.path.isfile(os.path.join(fp, f))]
                latest = max([os.path.getmtime(os.path.join(fp, f)) for f in files], default=0)
                has_template = any("EDM_template.html" in f for f in files)
                sns.append({
                    "sn": entry,
                    "has_template": has_template,
                    "file_count": len(files),
                    "updated": datetime.fromtimestamp(latest).isoformat() if latest else "",
                    "processed": entry in processed_sns,
                })

    return jsonify({"history": list(reversed(sns))})


# ---------------------------------------------------------------------------
# XLSX Discovery helpers — .eml version (no Outlook COM)
# ---------------------------------------------------------------------------

def _extract_xlsx_filename_from_eml(eml_path: str) -> str | None:
    """Extract xlsx filename from .eml HTML body SharePoint URL. Pure Python."""
    try:
        with open(eml_path, "rb") as f:
            mime = f.read()
        emsg = email_lib.message_from_bytes(mime)

        # Walk all MIME parts to find text/html body
        html_str = ""
        for part in emsg.walk():
            ct = part.get_content_type()
            fn = part.get_filename()
            if ct == "text/html" and not fn:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset("utf-8")
                    html_str = payload.decode(charset, errors="replace")
                    break

        urls = re.findall(r'https?://[^\s<>"\']+\.xlsx[^\s<>"\']*', html_str)
        if urls:
            after_last_slash = urls[0].rsplit("/", 1)[-1]
            filename = urllib_parse.unquote(after_last_slash.split("?")[0])
            return filename if filename else None

        # Fallback: plain text body
        text_str = ""
        for part in emsg.walk():
            ct = part.get_content_type()
            fn = part.get_filename()
            if ct == "text/plain" and not fn:
                payload = part.get_payload(decode=True)
                if payload:
                    text_str = payload.decode("utf-8", errors="ignore")
                    break

        urls = re.findall(r'https?://[^\s<>"\']+\.xlsx[^\s<>"\']*', text_str)
        if urls:
            after_last_slash = urls[0].rsplit("/", 1)[-1]
            filename = urllib_parse.unquote(after_last_slash.split("?")[0])
            return filename if filename else None

        return None
    except Exception:
        return None


def _load_xlsx_search_dir(project_root: str) -> str:
    """Load xlsx_search_dir.json or return default."""
    xlsx_config_path = os.path.join(project_root, "xlsx_search_dir.json")
    default_dir = os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "Microsoft", "Windows", "INetCache", "Content.MSO"
    )
    if os.path.isfile(xlsx_config_path):
        try:
            with open(xlsx_config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("search_directory", default_dir)
        except (json.JSONDecodeError, IOError):
            pass
    return default_dir


def _discover_xlsx(eml_path: str, project_root: str) -> str | None:
    """Discover xlsx file: extract filename from EML body, then search locally.

    Strict file discovery — mirror edm_agent.py:
      - If filename extracted from EML body → exact filename match only
      - If no filename extracted → fall back to SN folder match
    """
    filename_hint = _extract_xlsx_filename_from_eml(eml_path)
    search_dir = _load_xlsx_search_dir(project_root)

    if not os.path.isdir(search_dir):
        return None

    # If we got a filename hint, ONLY do exact match — no fuzzy fallback
    if filename_hint:
        logger.info(f"[edm-process] Searching xlsx: '{filename_hint}' (len={len(filename_hint)})")
        hint_lower = filename_hint.lower().strip()
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                f_lower = f.lower().strip()
                if f_lower == hint_lower:
                    found = os.path.join(root, f)
                    logger.info(f"[edm-process] Found xlsx (exact match): {f} -> {found}")
                    return found
                if filename_hint.split()[0].lower() in f_lower or any(s.lower() in f_lower for s in filename_hint.split() if len(s) > 3):
                    logger.debug(f"[edm-process] Near miss: '{f}' vs '{filename_hint}'")
        logger.warning(
            f"[edm-process] xlsx '{filename_hint}' not found in {search_dir}, giving up (no fuzzy match)"
        )
        return None

    # No filename hint — fall back to SN folder match
    sn_match = re.search(r"SN-\d+", os.path.basename(eml_path))
    if sn_match:
        sn = sn_match.group(0)
        sn_no_dash = sn.replace("-", "")
        for root, dirs, files in os.walk(search_dir):
            folder_name = os.path.basename(root).lower()
            if sn_no_dash.lower() in folder_name.replace("-", "") or sn.lower() in folder_name:
                xlsx_files = [f for f in files if f.lower().endswith(".xlsx")]
                if xlsx_files:
                    found = os.path.join(root, xlsx_files[0])
                    logger.info(f"[edm-process] Found xlsx (SN match): {found}")
                    return found

    return None


# ---------------------------------------------------------------------------
# Process a single .eml file (pure Python — no Outlook COM)
# ---------------------------------------------------------------------------

@edm_eml_bp.route('/process-file/<filename>', methods=['POST'])
@require_auth
def process_file(filename):
    """POST /api/edm/process-file/<filename> - Process .eml directly (no .msg conversion).

    Pipeline:
      Step 1: Discover xlsx from .eml body URL → copy to Temp/
      Step 2: Run edm_process_eml.py (pure Python, no Outlook COM)
    """
    from utils.task_queue import run_task

    project_root = _get_project_root()
    temp_dir = os.path.join(project_root, "EDM", "Temp")
    eml_path = os.path.join(temp_dir, filename)

    if not os.path.isfile(eml_path):
        return jsonify({"error": f"File not found: {filename}"}), 404

    if not filename.lower().endswith('.eml'):
        return jsonify({"error": "Only .eml files are supported"}), 400

    def _process():
        sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # PSWorkspace/
        project_root_local = os.path.dirname(sys_path)  # project root

        # ── Step 1: Discover xlsx (from .eml body URL) ──────────────
        logger.info(f"[edm-process] Discovering xlsx for {filename} ...")
        yield f"[STEP 1/2] 正在查找 xlsx 联系人列表 ..."

        xlsx_path = _discover_xlsx(eml_path, project_root_local)
        if xlsx_path:
            # Clean stale .xlsx from Temp/
            for stale in os.listdir(temp_dir):
                if stale.lower().endswith(".xlsx"):
                    stale_path = os.path.join(temp_dir, stale)
                    if os.path.isfile(stale_path):
                        os.remove(stale_path)

            # Copy xlsx to Temp/
            xlsx_in_temp = os.path.join(temp_dir, os.path.basename(xlsx_path))
            shutil.copy2(xlsx_path, xlsx_in_temp)
            yield f"[XLSX] ✓ 已复制到 Temp/: {os.path.basename(xlsx_path)}"
            logger.info(f"[edm-process] Copied xlsx to Temp/: {os.path.basename(xlsx_path)}")
        else:
            yield f"[XLSX] ⚠ 未找到 xlsx 文件，将跳过 xlsx 处理"
            logger.warning(f"[edm-process] No xlsx found for {filename}")

        # ── Step 2: Run edm_process_eml.py (pure Python) ────────────
        logger.info(f"[edm-process] Running edm_process_eml for {filename} ...")
        yield f"\n[STEP 2/2] 正在运行 EDM Process (纯 Python) ..."

        edm_script = os.path.join(
            project_root_local,
            ".claude", "skills", "edm-process", "edm_process_eml.py"
        )
        result = subprocess.run(
            [sys.executable, edm_script, "--temp-dir", temp_dir, "--file", filename],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                yield line
        if result.returncode != 0:
            raise RuntimeError(f"edm_process_eml failed: {result.stderr.strip()}")

        logger.info(f"[edm-process] Done processing {filename}")
        yield f"\n[DONE] 处理完成（无需 Outlook COM）"

        # Extract SN for activity log
        sn_match = re.search(r"SN-\d+", filename)
        task_queue.save_activity("edm", f"EDM Process {sn_match.group(0) if sn_match else filename}",
                                 f"处理完成: {filename}", "ok")

    task_id = run_task(f"edm-process-{filename}", _process())
    return jsonify({"task_id": task_id, "filename": filename})


# ---------------------------------------------------------------------------
# Dashboard Data (for EDM dashboard section)
# ---------------------------------------------------------------------------

STEPS = [
    {"name": "EDM Request", "desc": "Initial EDM request received and logged"},
    {"name": "Test Sent", "desc": "Test EDM sent to PS team, awaiting internal approval"},
    {"name": "Peer Reviewed", "desc": "Peer review completed, awaiting Nanbo's final approval"},
    {"name": "Approved", "desc": "EDM approved by all reviewers"},
    {"name": "Result Notified", "desc": "Approval result notified to PS team"},
    {"name": "Formal EDM Sent", "desc": "Formal EDM email sent to end customers"},
    {"name": "Confirmed, Closed", "desc": "Customer confirmed receipt, ticket closed"},
]


@edm_eml_bp.route('/dashboard', methods=['GET'])
@require_auth
def dashboard():
    project_root = _get_project_root()
    config = _load_config()
    data_file = os.path.join(project_root, config['paths']['edm_dashboard_data'])

    if not os.path.exists(data_file):
        return jsonify({"error": "Dashboard data file not found", "data": _empty_dashboard()})

    try:
        with open(data_file, 'r', encoding='utf-8-sig') as f:
            emails = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return jsonify({"error": f"Failed to load data: {e}", "data": _empty_dashboard()})

    from utils import task_queue as _tq
    _tq._edm_dashboard_handlers = set()
    handlers_file = os.path.join(project_root, config['paths']['edm_handlers'])
    try:
        with open(handlers_file, 'r', encoding='utf-8-sig') as f:
            raw_handlers = json.load(f)
        _tq._edm_dashboard_handlers = {h.lower() for h in raw_handlers.get("handlers", [])}
    except Exception:
        pass

    import sys as _sys
    _sys.path.insert(0, os.path.join(project_root, ".claude/skills/edm-dashboard"))
    import importlib as _lib
    _edm_dash = _lib.import_module("edm_dashboard")
    _edm_dash._handlers = _tq._edm_dashboard_handlers
    convs = _edm_dash.build_conversations(emails)

    result = []
    for c in convs:
        step_count = len(c.get("emails", []))
        is_done = step_count >= 7
        dates = [e.get("date", "") for e in c.get("emails", []) if e.get("date")]
        latest = max(dates) if dates else ""
        result.append({
            "conversation_id": c["conversation_id"],
            "sn": c.get("sn", ""),
            "subject": c.get("subject", ""),
            "step": step_count,
            "total_steps": 7,
            "is_done": is_done,
            "handler": c.get("firstSender", ""),
            "latest_date": latest,
            "email_count": len(c.get("emails", [])),
        })

    result.sort(key=lambda x: x.get("latest_date", ""), reverse=True)

    summary = {
        "total": len(result),
        "in_progress": len([r for r in result if not r["is_done"]]),
        "completed": len([r for r in result if r["is_done"]]),
        "steps": STEPS,
        "conversations": result,
    }
    return jsonify(summary)


@edm_eml_bp.route('/dashboard/refresh', methods=['POST'])
@require_auth
def dashboard_refresh():
    project_root = _get_project_root()
    config = _load_config()
    json_file = os.path.join(project_root, config['paths']['edm_dashboard_data'])

    import sys as _sys
    _sys.path.insert(0, os.path.join(project_root, ".claude/skills/edm-dashboard"))
    import importlib as _lib
    _edm_dash = _lib.import_module("edm_dashboard")
    _edm_dash._handlers = set()
    handlers_file = os.path.join(project_root, config['paths']['edm_handlers'])
    try:
        from utils import task_queue as _tq
        _tq._edm_dashboard_handlers = set()
        with open(handlers_file, 'r', encoding='utf-8-sig') as f:
            raw_handlers = json.load(f)
        _edm_dash._handlers = {h.lower() for h in raw_handlers.get("handlers", [])}
    except Exception:
        pass

    result = _edm_dash.do_refresh(
        json_file,
        _edm_dash.GITHUB_RAW_URL,
        _edm_dash.GITHUB_PROXY_URL,
    )
    status_str = "ok" if result.get("ok") else "warn"
    task_queue.save_activity("dashboard", "EDM 看板刷新",
                             f"来源: {result.get('source', 'unknown')}, {result.get('count', 0)} 条记录", status_str)
    return jsonify(result)


@edm_eml_bp.route('/dashboard/export', methods=['GET'])
@require_auth
def dashboard_export():
    from io import StringIO
    from flask import Response

    data = dashboard().get_json()
    conversations = data.get("conversations", [])

    output = StringIO()
    output.write("SN,Subject,Handler,Status,Step,Latest Date,Email Count\n")
    for conv in conversations:
        sn = conv.get("sn", "").replace(",", ";")
        subject = conv.get("subject", "").replace(",", ";").replace("\n", " ")
        handler = conv.get("handler", "").replace(",", ";")
        status = "Done" if conv.get("is_done") else "In Progress"
        step = f"{conv.get('step', 0)}/7"
        latest = conv.get("latest_date", "")
        count = conv.get("email_count", 0)
        output.write(f"{sn},{subject},{handler},{status},{step},{latest},{count}\n")

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content.encode('gb18030', errors='replace'),
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment; filename=edm_dashboard.csv"},
    )


def _empty_dashboard():
    return {
        "total": 0,
        "in_progress": 0,
        "completed": 0,
        "steps": STEPS,
        "conversations": [],
    }
