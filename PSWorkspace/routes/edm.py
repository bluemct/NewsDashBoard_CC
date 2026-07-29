"""EDM module - Real-time EWS listener for new EDM Agent emails.

Uses ews_streaming.ps1 (EWS Managed API DLL) for server-push streaming notifications.
"""
import os
import json
import re
import time
import logging
import subprocess
import threading
import email as email_lib
from datetime import datetime

from flask import Blueprint, jsonify, current_app, Response, request
from routes.auth import require_auth

logger = logging.getLogger(__name__)

edm_bp = Blueprint('edm', __name__, url_prefix='/api/edm')

# ---------------------------------------------------------------------------
# Listener state
# ---------------------------------------------------------------------------
_listener_proc: subprocess.Popen | None = None
_listener_thread: threading.Thread | None = None
_listener_lock = threading.Lock()
_event_log: list = []            # recent detection events
_event_lock = threading.Lock()

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
    # Best-effort fallback — only if _set_project_root hasn't been called yet.
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_config():
    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_ews_config():
    """Load EWS config from .edm_agent_config.json. Works inside and outside Flask context."""
    project_root = _get_project_root()
    ews_config_path = os.path.join(project_root, ".edm_agent_config.json")
    with open(ews_config_path, 'r', encoding='utf-8') as f:
        return json.load(f)["ews"]


def _add_event(event: dict):
    """Add a detection event to the log."""
    with _event_lock:
        _event_log.insert(0, event)
        if len(_event_log) > 200:
            _event_log.pop()


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

    # Load EWS config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        ews = cfg["ews"]
    except Exception as e:
        msg = f"无法读取配置: {e}"
        logger.error(f"[edm-listener] {msg}")
        _add_event({"time": datetime.now().isoformat(), "type": "error", "message": msg})
        return

    # Build PowerShell args
    ps_args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", ps_script,
        '-EwsUrl', ews["url"],
        '-DomainUser', ews["domain_user"],
        '-Password', ews["password"],
        '-FolderName', ews.get("folder_name", "EDM"),
    ]

    # Add DLL path
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

            # Check if thread should stop
            with _listener_lock:
                should_stop = _listener_proc is None

            if should_stop:
                break

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # PowerShell info output, not JSON
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

                # Quick filter: sender
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
    import base64
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
    m = re.search(r"SN-?(\d+)", subject)
    return f"SN-{m.group(1)}" if m else None


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@edm_bp.route('/listener/status', methods=['GET'])
@require_auth
def listener_status():
    """GET /api/edm/listener/status - Get listener status."""
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


@edm_bp.route('/listener/start', methods=['POST'])
@require_auth
def listener_start():
    """POST /api/edm/listener/start - Start the EWS streaming listener."""
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


@edm_bp.route('/listener/stop', methods=['POST'])
@require_auth
def listener_stop():
    """POST /api/edm/listener/stop - Stop the EWS listener."""
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


@edm_bp.route('/listener/events', methods=['GET'])
@require_auth
def listener_events():
    """GET /api/edm/listener/events?max=50 - Get recent detection events."""
    max_events = request.args.get('max', 50, type=int)
    with _event_lock:
        events = list(_event_log[:max_events])
    return jsonify({"events": events})


# ---------------------------------------------------------------------------
# Temp Files & History
# ---------------------------------------------------------------------------

@edm_bp.route('/temp-files', methods=['GET'])
@require_auth
def temp_files():
    """GET /api/edm/temp-files - List files in EDM/Temp/"""
    project_root = _get_project_root()
    temp_dir = os.path.join(project_root, "EDM", "Temp")
    if not os.path.isdir(temp_dir):
        return jsonify({"files": [], "message": "Temp directory not found"})

    files = []
    for f in sorted(os.listdir(temp_dir)):
        fp = os.path.join(temp_dir, f)
        if os.path.isfile(fp):
            stat = os.stat(fp)
            files.append({
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return jsonify({"files": files})


@edm_bp.route('/history', methods=['GET'])
@require_auth
def history():
    """GET /api/edm/history - List processed SN folders."""
    project_root = _get_project_root()
    edm_dir = os.path.join(project_root, "EDM")
    if not os.path.isdir(edm_dir):
        return jsonify({"history": []})

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
                })

    return jsonify({"history": list(reversed(sns))})


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


@edm_bp.route('/dashboard', methods=['GET'])
@require_auth
def dashboard():
    """GET /api/edm/dashboard - Get grouped EDM conversation data."""
    project_root = _get_project_root()
    config = _load_config()
    data_file = os.path.join(project_root, config['paths']['edm_dashboard_data'])

    if not os.path.exists(data_file):
        return jsonify({"error": "Dashboard data file not found", "data": _empty_dashboard()})

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            emails = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return jsonify({"error": f"Failed to load data: {e}", "data": _empty_dashboard()})

    # Load handlers
    handlers_file = os.path.join(project_root, config['paths']['edm_handlers'])
    handlers = []
    try:
        with open(handlers_file, 'r', encoding='utf-8') as f:
            handlers = json.load(f)
    except Exception:
        pass

    # Group by conversation_id, cap at 7 steps
    cutoff = datetime(2026, 5, 26)
    conversations = {}
    topic_map = {}

    for email in emails:
        conv_id = email.get("conversation_id", "")
        if not conv_id:
            continue

        email_date = email.get("date", "")
        try:
            dt = datetime.fromisoformat(email_date.replace("Z", "+00:00")).replace(tzinfo=None)
            if dt < cutoff:
                continue
        except (ValueError, AttributeError):
            pass

        subject = email.get("subject", "")
        if subject.startswith("[EDM test and distribution]"):
            sn = _extract_sn_from_subject(subject)
            topic_map[conv_id] = {"subject": subject, "sn": sn}

        if conv_id not in conversations:
            conversations[conv_id] = []
        conversations[conv_id].append(email)

    valid_convs = {k: v for k, v in conversations.items() if k in topic_map}

    result = []
    for conv_id, conv_emails in valid_convs.items():
        step_count = min(len(conv_emails), 7)
        is_done = step_count >= 7

        conv_emails.sort(key=lambda e: e.get("date", ""))

        topic = topic_map.get(conv_id, {})
        sn = topic.get("sn", "")
        subject = topic.get("subject", "")

        handler = ""
        for em in reversed(conv_emails):
            sender = em.get("sender", "")
            for h in handlers:
                if h.lower() in sender.lower():
                    handler = h
                    break
            if handler:
                break

        dates = [e.get("date", "") for e in conv_emails if e.get("date")]
        latest = max(dates) if dates else ""

        result.append({
            "conversation_id": conv_id,
            "sn": sn,
            "subject": subject,
            "step": step_count,
            "total_steps": 7,
            "is_done": is_done,
            "handler": handler,
            "latest_date": latest,
            "email_count": len(conv_emails),
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


@edm_bp.route('/dashboard/export', methods=['GET'])
@require_auth
def dashboard_export():
    """GET /api/edm/dashboard/export - Export dashboard data as CSV."""
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
