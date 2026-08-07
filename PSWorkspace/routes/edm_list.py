"""EDM List Import & Verify Blueprint for PS Workspace.

Provides REST APIs for:
  - List import (test/formal)
  - List discovery by SN
  - XLSX file upload
  - Email-only verification
  - Deep field-level verification

Reuses existing project modules via importlib:
  - unimarketing_test_list.py  (import pipeline)
  - verify_list_contacts.py    (email verify)
  - deep_verify_list.py        (deep verify)
"""
import os
import sys
import json
import re
import time
import importlib
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app
from routes.auth import require_auth
from utils import task_queue

logger = logging.getLogger(__name__)

edm_list_bp = Blueprint('edm_list', __name__, url_prefix='/api/edm/list')

# Cached at import time so background threads can use it without Flask context.
# Updated by _set_project_root() during app startup.
_project_root: str | None = None


def _set_project_root(path: str):
    """Call during app startup to set the project root for background threads."""
    global _project_root
    _project_root = path


# ---------------------------------------------------------------------------
# Dynamic module loading
# ---------------------------------------------------------------------------

def _get_project_root():
    """Get project root (AgentProject/), parent of PSWorkspace/. Works in/out of app context."""
    if _project_root:
        return _project_root
    base = current_app.config.get('BASE_DIR', '')
    if base:
        return os.path.abspath(os.path.join(base, ".."))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_module(module_name):
    """Load a module from project root using importlib."""
    project_root = _get_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        logger.warning(f"[edm-list] Could not load {module_name}: {e}")
        return None


def _normalize_sn(sn: str) -> str:
    """Normalize SN format: strip whitespace, ensure SN- prefix."""
    sn = sn.strip()
    if not sn:
        return sn
    # If user typed just digits like "55247", add SN- prefix
    m = re.search(r"(\d+)", sn)
    if m:
        return f"SN-{m.group(1)}"
    return sn


def _verify_mod():
    """Load verify_list_contacts module."""
    return _load_module("verify_list_contacts")


def _deep_mod():
    """Load deep_verify_list module."""
    return _load_module("deep_verify_list")


def _import_mod():
    """Load unimarketing_test_list module from project root."""
    return _load_module("unimarketing_test_list")


# ---------------------------------------------------------------------------
# List Discovery
# ---------------------------------------------------------------------------

@edm_list_bp.route('/discover', methods=['POST'])
@require_auth
def discover_lists():
    """Discover lists by SN number via Unimarketing API.

    POST body: {"sn": "SN-56287" or "56287"}
    Returns: {"lists": [{"list_id": ..., "title": ..., "type": "test"/"formal"}]}
    """
    data = request.get_json(force=True, silent=True) or {}
    sn = data.get('sn', '').strip()
    if not sn:
        return jsonify({"error": "SN is required"}), 400

    mod = _verify_mod()
    if mod is None:
        return jsonify({"error": "verify_list_contacts module not available"}), 500

    try:
        lists = mod.find_lists_by_sn(sn)
        # Sort by list_id descending (newest first)
        lists.sort(key=lambda x: int(x[0]), reverse=True)
        result = []
        for list_id, title, lst_type in lists:
            result.append({
                "list_id": list_id,
                "title": title,
                "type": lst_type,
            })
        return jsonify({"lists": result})
    except Exception as e:
        logger.exception(f"[edm-list] Discover error for SN {sn}")
        return jsonify({"error": str(e)}), 500


@edm_list_bp.route('/info', methods=['GET'])
@require_auth
def list_info():
    """Get list info (activeCount, etc.)

    Query: ?list_id=12345
    """
    list_id = request.args.get('list_id', '').strip()
    if not list_id:
        return jsonify({"error": "list_id is required"}), 400

    mod = _verify_mod()
    if mod is None:
        return jsonify({"error": "verify_list_contacts module not available"}), 500

    try:
        info = mod.get_list_info(list_id)
        if info is None:
            return jsonify({"error": "List not found"}), 404
        info["list_id"] = list_id
        return jsonify(info)
    except Exception as e:
        logger.exception(f"[edm-list] Info error for list {list_id}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# List Import (Test / Formal)
# ---------------------------------------------------------------------------

@edm_list_bp.route('/import', methods=['POST'])
@require_auth
def import_list():
    """Import xlsx to Unimarketing list.

    POST body: {
        "xlsx_path": "/path/to/file.xlsx",
        "sn": "SN-56287",
        "mode": "test" | "formal"
    }
    Returns: {"task_id": "..."} (async task)
    """
    from utils.task_queue import run_task

    data = request.get_json(force=True, silent=True) or {}
    xlsx_path = data.get('xlsx_path', '').strip()
    sn = data.get('sn', '').strip()
    mode = data.get('mode', 'test').strip()

    if not xlsx_path:
        return jsonify({"error": "xlsx_path is required"}), 400
    if not sn:
        return jsonify({"error": "sn is required"}), 400

    def _import_task():
        import_mod = _load_module("unimarketing_test_list")
        if import_mod is None:
            raise RuntimeError("unimarketing_test_list module not available")

        # Read test emails from .edm_agent_config.json
        config_path = os.path.join(_get_project_root(), ".edm_agent_config.json")
        default_test_emails = ["ma.chuntao@oe.21vianet.com", "microsoft.163163@163.com"]
        try:
            with open(config_path, "r", encoding="utf-8") as cf:
                edm_cfg = json.load(cf)
            test_emails = edm_cfg.get("test_emails", default_test_emails)
        except (FileNotFoundError, json.JSONDecodeError):
            test_emails = default_test_emails

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        yield "=== Import Started ==="
        yield f"=== Unimarketing {'Test' if mode == 'test' else 'Formal'} List Import ==="
        yield f"SN: {sn}"

        xlsx_name = os.path.splitext(os.path.basename(xlsx_path))[0]
        now_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        list_title = f"{mode}_{sn}_{xlsx_name}_{now_ts}"
        yield f"List: {list_title}"

        if mode == 'test':
            yield f"Test emails: {test_emails}"

        yield ""

        output_dir = os.path.dirname(xlsx_path)

        # Generate CSV
        if mode == 'test':
            yield "[CSV] generating test CSV..."
            csv_path = import_mod.generate_test_csv(
                xlsx_path, output_dir,
                test_emails
            )
        else:
            yield "[CSV] generating formal CSV..."
            csv_path = import_mod.generate_formal_csv(xlsx_path, output_dir)
        yield f"[CSV] saved: {os.path.basename(csv_path)}"

        # Read CSV header for attributes
        with open(csv_path, encoding="gbk", newline="") as f:
            import csv as csv_mod
            csv_header = next(csv_mod.reader(f))

        attrs = import_mod.get_attr_mapping(csv_header)
        yield f"Attributes: {[(a[0], a[1]) for a in attrs]}"

        yield ""
        yield "[API] creating list..."
        list_id = import_mod.create_list(list_title, attrs)
        if not list_id:
            raise RuntimeError("Failed to create list")
        yield f"[API] list created: {list_id}"

        yield "[API] creating import task..."
        import_id = import_mod.create_import_task(list_id, f"API导入_{now_ts}")
        if not import_id:
            raise RuntimeError("Failed to create import task")
        yield f"[API] import task created: {import_id}"

        yield "[API] submitting contacts..."
        contact_count = import_mod.submit_contacts(import_id, csv_path, attrs)
        if not contact_count:
            raise RuntimeError("Failed to submit contacts")
        yield f"[API] contacts submitted: {contact_count}"

        yield "[API] executing import..."
        if not import_mod.execute_import(import_id):
            raise RuntimeError("Failed to execute import")
        yield "[API] polling import status..."

        result = import_mod.poll_import_status(import_id, contact_count)

        yield ""
        if result.get('status') in ('导入成功', 'execute_succeed'):
            yield f"SUCCESS: Import complete — listId={list_id}, importId={import_id}"
            yield f"  Total: {result.get('total', '?')} | Valid: {result.get('validNum', '?')} | Invalid: {result.get('inValidNum', '?')} | Added: {result.get('addToListSuccessNum', '?')} | New: {result.get('addSuccessNum', '?')} | Updated: {result.get('updateSuccessNum', '?')}"
        else:
            yield f"FAILED: Import error — {result.get('status', 'unknown')}"
            yield f"  Total: {result.get('total', '?')} | Valid: {result.get('validNum', '?')} | Invalid: {result.get('inValidNum', '?')}"

        yield ""
        yield "=== Import Done ==="

        # Record to history
        import_status = 'success' if result.get('status') in ('导入成功', 'execute_succeed') else 'failed'
        row_id = task_queue.save_edm_list_history(
            sn=_normalize_sn(sn),
            list_id=list_id,
            list_title=list_title,
            import_type=mode,
            xlsx_path=xlsx_path,
            csv_path=csv_path,
            import_status=import_status,
            import_result=json.dumps(result, ensure_ascii=False),
        )
        logger.info(f"[edm-list] Import history saved: id={row_id} sn={sn} list_id={list_id} mode={mode} status={import_status}")

        # Save activity
        task_queue.save_activity(
            "edm",
            f"List Import {sn} ({mode})",
            f"list_id={list_id} | {result.get('total', '?')} contacts | {import_status}",
            "ok" if import_status == 'success' else "error",
        )

    task_id = run_task(f"edm-import-{sn}-{mode}-{int(time.time())}", _import_task())
    return jsonify({"task_id": task_id, "mode": mode})


# ---------------------------------------------------------------------------
# XLSX Discover
# ---------------------------------------------------------------------------

@edm_list_bp.route('/xlsx-discover', methods=['POST'])
@require_auth
def xlsx_discover():
    """Discover xlsx file matching SN — EML body filename extraction + exact match.

    Strategy (matches EDM GUI Discover logic):
      1. Find .eml in EDM/Temp/ by SN match
      2. Extract xlsx filename from EML HTML body (SharePoint URL)
      3. Do exact filename match in xlsx_search_dir
      4. If no filename extracted, fall back to SN folder search

    POST body: {"sn": "SN-56287"}
    Returns: {"xlsx_path": "...", "xlsx_name": "..."}
    """
    data = request.get_json(force=True, silent=True) or {}
    sn = data.get('sn', '').strip()

    if not sn:
        logger.info(f"[edm-list] xlsx-discover: sn is empty")
        return jsonify({"error": "sn is required"}), 400

    project_root = _get_project_root()
    temp_dir = os.path.join(project_root, "EDM", "Temp")

    logger.info(f"[edm-list] xlsx-discover: SN={sn}, temp_dir={temp_dir}")
    logger.info(f"[edm-list] xlsx-discover: temp_dir exists={os.path.isdir(temp_dir)}")

    # Load xlsx_search_dir config (same as EDM GUI)
    xlsx_config_path = os.path.join(project_root, "xlsx_search_dir.json")
    default_dir = os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "Microsoft", "Windows", "INetCache", "Content.MSO"
    )
    search_dir = default_dir
    if os.path.isfile(xlsx_config_path):
        try:
            with open(xlsx_config_path, "r", encoding="utf-8") as f:
                search_dir = json.load(f).get("search_directory", default_dir)
        except (json.JSONDecodeError, IOError):
            pass

    logger.info(f"[edm-list] xlsx-discover: search_dir={search_dir}")
    logger.info(f"[edm-list] xlsx-discover: search_dir exists={os.path.isdir(search_dir)}")

    if not os.path.isdir(search_dir):
        logger.warning(f"[edm-list] xlsx-discover: search_dir not found: {search_dir}")
        return jsonify({"error": f"Search directory not found: {search_dir}"}), 404

    # Step 1: Find EML file in Temp/ by SN
    sn_match = re.search(r"SN\s*-\s*(\d+)", sn, re.IGNORECASE)
    sn_digits = sn_match.group(1) if sn_match else sn.replace("-", "").replace(" ", "")
    logger.info(f"[edm-list] xlsx-discover: sn_digits={sn_digits}")

    eml_path = None
    if os.path.isdir(temp_dir):
        for f in sorted(os.listdir(temp_dir)):
            if f.lower().endswith(".eml") and sn_digits in f.replace("-", ""):
                eml_path = os.path.join(temp_dir, f)
                break
    logger.info(f"[edm-list] xlsx-discover: eml_found={eml_path is not None}, eml={eml_path}")

    # Step 2: Extract xlsx filename from EML body if found
    filename_hint = None
    if eml_path:
        filename_hint = _extract_xlsx_filename_from_eml(eml_path)
        logger.info(f"[edm-list] EML: {os.path.basename(eml_path)}, xlsx hint: {filename_hint}")

    # Step 3: Exact filename match if hint available
    if filename_hint:
        hint_lower = filename_hint.lower().strip()
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f.lower() == hint_lower:
                    full_path = os.path.join(root, f).replace(os.sep, "/")
                    return jsonify({
                        "xlsx_path": full_path,
                        "xlsx_name": f,
                    })
        logger.warning(f"[edm-list] xlsx '{filename_hint}' not found in {search_dir}")

    # Step 4: Fall back to SN folder search
    sn_no_dash = sn.replace("-", "").replace(" ", "")
    for root, dirs, files in os.walk(search_dir):
        folder_name = os.path.basename(root).lower()
        if sn_no_dash.lower() in folder_name.replace("-", "") or sn.lower() in folder_name:
            xlsx_files = [f for f in files if f.lower().endswith(".xlsx")]
            if xlsx_files:
                full_path = os.path.join(root, xlsx_files[0]).replace(os.sep, "/")
                return jsonify({
                    "xlsx_path": full_path,
                    "xlsx_name": xlsx_files[0],
                })

    return jsonify({"error": f"No xlsx file found for SN '{sn}' in {search_dir}"}), 404


def _extract_xlsx_filename_from_eml(eml_path: str) -> str | None:
    """Extract xlsx filename from .eml HTML body SharePoint URL."""
    import email as email_lib
    from urllib import parse as urllib_parse
    try:
        with open(eml_path, "rb") as f:
            mime = f.read()
        emsg = email_lib.message_from_bytes(mime)
        html_str = ""
        for part in emsg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset("utf-8")
                    html_str = payload.decode(charset, errors="replace")
                    break
        if html_str:
            urls = re.findall(r'https?://[^\s<>"\']+\.xlsx[^\s<>"\']*', html_str)
            if urls:
                after_last_slash = urls[0].rsplit("/", 1)[-1]
                filename = urllib_parse.unquote(after_last_slash.split("?")[0])
                if filename:
                    return filename
        text_str = ""
        for part in emsg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    text_str = payload.decode("utf-8", errors="ignore")
                    break
        if text_str:
            urls = re.findall(r'https?://[^\s<>"\']+\.xlsx[^\s<>"\']*', text_str)
            if urls:
                after_last_slash = urls[0].rsplit("/", 1)[-1]
                filename = urllib_parse.unquote(after_last_slash.split("?")[0])
                if filename:
                    return filename
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# XLSX Browse — list xlsx files in xlsx_search_dir only
# ---------------------------------------------------------------------------

@edm_list_bp.route('/xlsx-browse', methods=['GET'])
@require_auth
def xlsx_browse():
    """Build a directory tree of xlsx files in xlsx_search_dir."""
    project_root = _get_project_root()

    # Load xlsx_search_dir
    xlsx_config_path = os.path.join(project_root, "xlsx_search_dir.json")
    default_cache = os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "Microsoft", "Windows", "INetCache", "Content.MSO"
    )
    search_dir = default_cache
    if os.path.isfile(xlsx_config_path):
        try:
            with open(xlsx_config_path, "r", encoding="utf-8") as f:
                search_dir = json.load(f).get("search_directory", default_cache)
        except (json.JSONDecodeError, IOError):
            pass

    if not os.path.isdir(search_dir):
        return jsonify({"error": f"Search directory not found: {search_dir}"}), 404

    def build_tree(dir_path):
        """Recursively build directory tree with xlsx file info."""
        node = {
            "name": os.path.basename(dir_path),
            "path": dir_path,
            "children": [],
            "files": [],
            "depth": dir_path.replace(search_dir, "").count(os.sep),
        }
        try:
            entries = sorted(os.listdir(dir_path), key=lambda x: x.lower())
        except PermissionError:
            return node

        for entry in entries:
            full = os.path.join(dir_path, entry)
            if os.path.isdir(full):
                node["children"].append(build_tree(full))
            elif entry.lower().endswith(".xlsx"):
                try:
                    stat = os.stat(full)
                    node["files"].append({
                        "name": entry,
                        "path": full.replace(os.sep, "/"),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except OSError:
                    pass

        # Sort children by name
        node["children"].sort(key=lambda x: x["name"].lower())
        return node

    root_node = build_tree(search_dir)
    return jsonify({"tree": root_node, "search_dir": search_dir})


# ---------------------------------------------------------------------------
# Email-Only Verification
# ---------------------------------------------------------------------------

@edm_list_bp.route('/verify-email', methods=['POST'])
@require_auth
def verify_email():
    """Email-only list verification.

    POST body: {
        "list_id": "12345",
        "xlsx_path": "/path/to/file.xlsx",
        "sn": "SN-56287"  (optional, for logging)
    }
    Returns: {"task_id": "..."} (async task)
    """
    from utils.task_queue import run_task

    data = request.get_json(force=True, silent=True) or {}
    list_id = data.get('list_id', '').strip()
    xlsx_path = data.get('xlsx_path', '').strip()
    sn = data.get('sn', '').strip()

    if not list_id or not xlsx_path:
        return jsonify({"error": "list_id and xlsx_path are required"}), 400

    def _verify_task():
        vmod = _load_module("verify_list_contacts")
        if vmod is None:
            raise RuntimeError("verify_list_contacts module not available")

        project_root = _get_project_root()
        save_dir = os.path.join(project_root, "Log", "list_verify")
        os.makedirs(save_dir, exist_ok=True)

        log_lines = []
        result_data = {}
        class _Logger:
            def log(self, msg):
                log_lines.append(msg)

        yield "[VERIFY] Email-only verification"
        yield f"[VERIFY] List ID: {list_id}"
        yield f"[VERIFY] XLSX: {os.path.basename(xlsx_path)}"
        yield ""

        # Read xlsx emails for summary
        xlsx_emails = vmod.read_xlsx_emails(xlsx_path)

        # Get list info
        info = vmod.get_list_info(list_id)
        list_title = info["title"] if info else list_id
        total_in_list = (
            info["activeCount"] + info["unsubscribeCount"]
            + info["invalidateCount"] + info["unconfirmCount"]
        ) if info else "?"

        passed, msg = vmod.verify_list_import(
            list_id, xlsx_path, save_dir, _Logger()
        )

        for line in log_lines:
            if line.strip():
                yield line

        # Yield structured result as JSON line
        result_data = {
            "type": "email",
            "passed": passed,
            "list_id": list_id,
            "list_title": list_title,
            "total_in_list": total_in_list,
            "xlsx_emails": len(xlsx_emails),
            "msg": msg,
        }
        yield f"__RESULT__{json.dumps(result_data, ensure_ascii=False)}"

        # Always create a new history record for each verification
        row_id = task_queue.save_edm_list_history(
            sn=_normalize_sn(sn),
            list_id=list_id,
            list_title=list_title,
            import_type='',
            xlsx_path=xlsx_path,
            csv_path='',
            import_status='',
            import_result='',
            verify_email_status='pass' if passed else 'fail',
            verify_email_result=msg,
        )
        logger.info(f"[edm-list] Email verify history saved: id={row_id} sn={sn} list_id={list_id} status={'pass' if passed else 'fail'}")

    task_id = run_task(f"edm-verify-email-{list_id}-{int(time.time())}", _verify_task())
    return jsonify({"task_id": task_id})


# ---------------------------------------------------------------------------
# Deep Verification
# ---------------------------------------------------------------------------

@edm_list_bp.route('/verify-deep', methods=['POST'])
@require_auth
def verify_deep():
    """Deep field-level list verification.

    POST body: {
        "list_id": "12345",
        "xlsx_path": "/path/to/file.xlsx",
        "sn": "SN-56287"  (optional, for logging)
    }
    Returns: {"task_id": "..."} (async task)
    """
    from utils.task_queue import run_task

    data = request.get_json(force=True, silent=True) or {}
    list_id = data.get('list_id', '').strip()
    xlsx_path = data.get('xlsx_path', '').strip()
    sn = data.get('sn', '').strip()

    if not list_id or not xlsx_path:
        return jsonify({"error": "list_id and xlsx_path are required"}), 400

    def _deep_task():
        dmod = _load_module("deep_verify_list")
        if dmod is None:
            raise RuntimeError("deep_verify_list module not available")

        project_root = _get_project_root()
        save_dir = os.path.join(project_root, "Log", "list_verify")
        os.makedirs(save_dir, exist_ok=True)

        log_lines = []
        class _Logger:
            def log(self, msg):
                log_lines.append(msg)

        yield "[DEEP] Deep verification (field-level)"
        yield f"[DEEP] List ID: {list_id}"
        yield f"[DEEP] XLSX: {os.path.basename(xlsx_path)}"
        yield ""

        # Get list info for title
        info = dmod.get_list_info(list_id)
        list_title = info["title"] if info else ""

        passed, msg = dmod.deep_verify(
            list_id, xlsx_path, save_dir, _Logger(), max_workers=10
        )

        for line in log_lines:
            if line.strip():
                yield line

        # Yield structured result as JSON line
        result_data = {
            "type": "deep",
            "passed": passed,
            "list_id": list_id,
            "list_title": list_title,
            "msg": msg,
        }
        yield f"__RESULT__{json.dumps(result_data, ensure_ascii=False)}"

        # Always create a new history record for each verification
        row_id = task_queue.save_edm_list_history(
            sn=_normalize_sn(sn),
            list_id=list_id,
            list_title=list_title,
            import_type='',
            xlsx_path=xlsx_path,
            csv_path='',
            import_status='',
            import_result='',
            verify_deep_status='pass' if passed else 'fail',
            verify_deep_result=msg,
        )
        logger.info(f"[edm-list] Deep verify history saved: id={row_id} sn={sn} list_id={list_id} status={'pass' if passed else 'fail'}")

    task_id = run_task(f"edm-verify-deep-{list_id}-{int(time.time())}", _deep_task())
    return jsonify({"task_id": task_id})


# ---------------------------------------------------------------------------
# Verification History
# ---------------------------------------------------------------------------

@edm_list_bp.route('/history', methods=['GET'])
@require_auth
def verify_history():
    """Get recent list import/verify history.

    Query: ?page=1&page_size=20&sn=SN-56287 (optional filter)
    """
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    sn_filter = request.args.get('sn', '').strip()

    result = task_queue.list_edm_list_history(
        page=page, page_size=page_size, sn=sn_filter if sn_filter else None
    )

    # Parse JSON fields back to dicts
    for item in result.get('data', []):
        if item.get('import_result'):
            try:
                item['import_result'] = json.loads(item['import_result'])
            except (json.JSONDecodeError, TypeError):
                pass
    return jsonify(result)
