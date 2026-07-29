"""ICM module - pure Python ICM API client (no PowerShell)."""
import os
import json
import logging
import base64
import urllib.request
import urllib.error
import threading
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from routes.auth import require_auth
from utils import task_queue

import urllib.parse

logger = logging.getLogger(__name__)

icm_bp = Blueprint('icm', __name__, url_prefix='/api/icm')

# ─── Module-level state (set at app startup for background threads) ──
_PROJECT_ROOT: str | None = None
_AUTO_REFRESH_THREAD: threading.Thread | None = None


def _set_project_root(path: str):
    """Cache PROJECT_ROOT so background threads don't need Flask app context."""
    global _PROJECT_ROOT
    _PROJECT_ROOT = path


def _start_auto_refresh():
    """Start ICM Token auto-refresh daemon thread (checks every 15 min, refreshes if < 1h remaining)."""
    global _AUTO_REFRESH_THREAD
    if _AUTO_REFRESH_THREAD and _AUTO_REFRESH_THREAD.is_alive():
        logger.info("ICM auto-refresh already running, skipping")
        return
    _AUTO_REFRESH_THREAD = threading.Thread(target=_icm_auto_refresh_loop, daemon=True)
    _AUTO_REFRESH_THREAD.start()
    logger.info("ICM Token auto-refresh daemon started")


def _parse_jwt_expiry(token: str) -> datetime:
    """Parse JWT payload 'exp' field, return UTC datetime."""
    parts = token.split('.')
    payload = parts[1]
    payload += '=' * (4 - len(payload) % 4) if len(payload) % 4 else ''
    payload = payload.replace('-', '+').replace('_', '/')
    dec = json.loads(base64.b64decode(payload))
    return datetime.fromtimestamp(dec['exp'], tz=timezone.utc)


def _do_token_refresh():
    """Refresh ICM token using Cookie.
    Returns dict with keys: ok, message, remaining_min, old_token, new_token, expires_at, obtained_at,
                            error_message, cookie_updated, cookie_expires_at
    """
    old_token = ""
    try:
        orig_config_path = os.path.join(_get_project_root(), 'IcMHelper', 'icm_config.json')
        with open(orig_config_path, 'r', encoding='utf-8') as f:
            orig_cfg = json.load(f)

        old_token = orig_cfg.get('access_token', '')
        cookie_string = orig_cfg.get('cookie_string', '')
        auth_cookie = None
        for part in cookie_string.split(';'):
            trimmed = part.strip()
            if trimmed.startswith("CloudESAuthCookie="):
                auth_cookie = trimmed[len("CloudESAuthCookie="):]
                break
        if not auth_cookie:
            logger.error("Token refresh: CloudESAuthCookie not found")
            return {"ok": False, "message": "CloudESAuthCookie not found", "remaining_min": 0.0,
                    "old_token": old_token, "new_token": "", "expires_at": "", "obtained_at": "",
                    "error_message": "CloudESAuthCookie not found", "cookie_updated": None,
                    "cookie_expires_at": None}

        # Exchange cookie for new token
        token_data = "grant_type=cookie".encode('utf-8')
        req = urllib.request.Request(
            "https://portal.microsofticm.com/sso2/token",
            data=token_data,
            method='POST',
        )
        req.add_header('Content-Type', 'application/json;charset=UTF-8')
        req.add_header('Origin', 'https://portal.microsofticm.com')
        req.add_header('Referer', 'https://portal.microsofticm.com/imp/v3/')
        req.add_header('Cookie', f'CloudESAuthCookie={auth_cookie}')

        resp = urllib.request.urlopen(req, timeout=30)
        resp_body = json.loads(resp.read().decode('utf-8'))
        new_token = resp_body.get('access_token', '')
        if not new_token:
            return {"ok": False, "message": "No access_token in refresh response", "remaining_min": 0.0,
                    "old_token": old_token, "new_token": "", "expires_at": "", "obtained_at": "",
                    "error_message": "No access_token in refresh response", "cookie_updated": None,
                    "cookie_expires_at": None}

        # Check Set-Cookie header for new CloudESAuthCookie and its expiry
        cookie_updated = None
        cookie_expires_at = None
        set_cookie_header = resp.getheader('Set-Cookie', '')
        logger.info("Token refresh Set-Cookie header: [%s]", set_cookie_header)
        if set_cookie_header:
            for sc_part in set_cookie_header.split(';'):
                sct = sc_part.strip()
                if sct.startswith("CloudESAuthCookie="):
                    new_cookie_val = sct[len("CloudESAuthCookie="):]
                    if new_cookie_val:
                        orig_cfg['cookie_string'] = f'CloudESAuthCookie={new_cookie_val}'
                        cookie_updated = "yes"
                elif sct.lower().startswith("expires="):
                    exp_str = sct[len("expires="):].strip()
                    # Parse cookie expiry: "Wed, 05 Aug 2026 02:43:22 GMT" or "Thu, 30-Jul-2026 23:20:35 GMT"
                    try:
                        # Remove day-of-week prefix: "Thu, 30-Jul-2026 23:20:35 GMT" -> "30-Jul-2026 23:20:35 GMT"
                        exp_clean = exp_str.split(',')[1].strip() if ',' in exp_str else exp_str
                        # Normalize "30-Jul-2026" -> "30 Jul 2026"
                        exp_clean = exp_clean.replace('-', ' ')
                        exp_dt = datetime.strptime(exp_clean, "%d %b %Y %H:%M:%S %Z")
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        cookie_expires_at = exp_dt.isoformat()
                    except Exception:
                        cookie_expires_at = exp_str

        # Fallback: if no Set-Cookie returned, use existing cookie_expires from config
        if not cookie_expires_at:
            cookie_expires_at = orig_cfg.get('cookie_expires')
        if cookie_expires_at:
            orig_cfg['cookie_expires'] = cookie_expires_at

        # Write configs
        orig_cfg['access_token'] = new_token
        ps_config_path = os.path.join(_get_project_root(), 'IcMHelperPS', 'icm_config.json')
        with open(orig_config_path, 'w', encoding='utf-8') as f:
            json.dump(orig_cfg, f, indent=2, ensure_ascii=False)
        with open(ps_config_path, 'w', encoding='utf-8') as f:
            json.dump(orig_cfg, f, indent=2, ensure_ascii=False)

        # Compute remaining time
        exp = _parse_jwt_expiry(new_token)
        remaining_min = (exp - datetime.now(tz=timezone.utc)).total_seconds() / 60
        expires_at = exp.isoformat()
        obtained_at = datetime.now(tz=timezone.utc).isoformat()

        return {"ok": True, "message": f"Token refreshed, expires in {remaining_min:.0f} min",
                "remaining_min": remaining_min, "old_token": old_token, "new_token": new_token,
                "expires_at": expires_at, "obtained_at": obtained_at, "error_message": "",
                "cookie_updated": cookie_updated, "cookie_expires_at": cookie_expires_at}
    except Exception as e:
        logger.error("Token refresh error: %s", e)
        return {"ok": False, "message": str(e), "remaining_min": 0.0,
                "old_token": old_token, "new_token": "", "expires_at": "", "obtained_at": "",
                "error_message": str(e), "cookie_updated": None, "cookie_expires_at": None}


def _icm_auto_refresh_loop():
    """Daemon loop: every 15 min, check token and cookie expiry → auto-refresh as needed."""
    check_interval = 15 * 60  # 15 minutes
    cookie_refresh_threshold_hours = 48  # refresh cookie if < 48h remaining
    while True:
        try:
            ps_config_path = os.path.join(_get_project_root(), 'IcMHelperPS', 'icm_config.json')
            with open(ps_config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            token = cfg.get('access_token', '')
            if not token:
                time.sleep(check_interval)
                continue

            # ── Check token expiry ──
            exp = _parse_jwt_expiry(token)
            token_remaining = (exp - datetime.now(tz=timezone.utc)).total_seconds() / 60

            if token_remaining < 60:
                logger.info("ICM token expiring in %.1f min, auto-refreshing...", token_remaining)
                result = _do_token_refresh()
                if result["ok"]:
                    logger.info("ICM token auto-refresh: %s", result["message"])
                    _record_token_history(result, "auto")
                else:
                    logger.error("ICM token auto-refresh failed: %s", result["message"])
                    _record_token_history(result, "auto")

            # ── Check cookie expiry ──
            cookie_expires_str = cfg.get('cookie_expires', '')
            if cookie_expires_str:
                try:
                    cookie_exp = datetime.fromisoformat(cookie_expires_str)
                    if cookie_exp.tzinfo is None:
                        cookie_exp = cookie_exp.replace(tzinfo=timezone.utc)
                    cookie_remaining_hours = (cookie_exp - datetime.now(tz=timezone.utc)).total_seconds() / 3600
                    if cookie_remaining_hours < cookie_refresh_threshold_hours:
                        logger.info("ICM cookie expiring in %.1f h (<%dh), attempting cookie refresh...",
                                    cookie_remaining_hours, cookie_refresh_threshold_hours)
                        result = _do_token_refresh()
                        if result["ok"] and result.get("cookie_updated") == "yes":
                            logger.info("ICM cookie auto-refresh: got new cookie, expires %s",
                                        result.get("cookie_expires_at", "unknown"))
                            _record_token_history(result, "auto-cookie")
                        elif result["ok"]:
                            logger.info("ICM cookie refresh: token refreshed but no new cookie from API")
                            _record_token_history(result, "auto-cookie")
                        else:
                            logger.error("ICM cookie refresh failed: %s", result["message"])
                            _record_token_history(result, "auto-cookie")
                    else:
                        logger.debug("ICM cookie OK: %.0f h remaining", cookie_remaining_hours)
                except Exception as e:
                    logger.debug("Failed to parse cookie expiry [%s]: %s", cookie_expires_str, e)
            else:
                logger.debug("ICM cookie: no cookie_expires in config, skipping cookie check")

        except Exception as e:
            logger.error("ICM auto-refresh check error: %s", e)

        time.sleep(check_interval)


# Cached config loaded at startup (avoids Flask app context in background threads)
_ICM_CONFIG: dict | None = None
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # PSWorkspace/


def _get_project_root():
    if _PROJECT_ROOT is None:
        return os.getcwd()
    return _PROJECT_ROOT


def _load_config():
    global _ICM_CONFIG
    if _ICM_CONFIG is None:
        config_path = os.path.join(_BASE_DIR, 'ps_workspace_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            _ICM_CONFIG = json.load(f)
    return _ICM_CONFIG


# ─── Token Management ─────────────────────────────────────────

@icm_bp.route('/token/verify', methods=['GET'])
@require_auth
def token_verify():
    """GET /api/icm/token/verify - Verify ICM token is valid (Python-native, no PowerShell)."""
    error_msg = ""
    exp_str = ""
    remaining_min = 0.0
    cookie_expires_at = None
    try:
        # Load config
        config_path = os.path.join(_get_project_root(), 'IcMHelperPS', 'icm_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        token = cfg.get('access_token', '')
        if not token:
            error_msg = "No access_token in config"
            _save_verify_history(False, "", "", 0.0, error_msg, {})
            return jsonify({"ok": False, "error": error_msg}), 400

        # Read cookie expiry from config
        cookie_expires_at = cfg.get('cookie_expires')

        # Parse JWT expiry
        parts = token.split('.')
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4) if len(payload) % 4 else ''
        payload = payload.replace('-', '+').replace('_', '/')
        dec = json.loads(base64.b64decode(payload))
        exp = datetime.fromtimestamp(dec['exp'], tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        remaining_min = (exp - now).total_seconds() / 60
        exp_str = exp.isoformat()
        obtained_at = datetime.fromtimestamp(dec.get('iat', dec['exp']), tz=timezone.utc).isoformat()

        # Actual API call to verify
        req = urllib.request.Request(
            'https://prod.microsofticm.com/api2/incidentapi/incidents?$top=1',
            method='GET'
        )
        req.add_header('Authorization', 'Bearer ' + token)
        req.add_header('Accept', 'application/json')

        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())

        is_valid = resp.status == 200
        count = len(data.get('value', [])) if isinstance(data, dict) else 0

        _save_verify_history(True, obtained_at, exp_str, remaining_min, "",
                             {"incidents_returned": count}, cookie_expires_at=cookie_expires_at)

        return jsonify({
            "ok": is_valid,
            "expiring_at": exp.strftime('%Y-%m-%d %H:%M:%S UTC'),
            "remaining_minutes": round(remaining_min, 1),
            "incidents_returned": count,
        })
    except urllib.error.HTTPError as e:
        if e.code == 401:
            error_msg = "Token expired or invalid (401)"
        else:
            error_msg = f"HTTP {e.code}"
        _save_verify_history(False, obtained_at if obtained_at else "", exp_str, remaining_min,
                             error_msg, {}, cookie_expires_at=cookie_expires_at)
        return jsonify({"ok": False, "error": error_msg})
    except Exception as e:
        error_msg = str(e)
        _save_verify_history(False, "", "", 0.0, error_msg, {}, cookie_expires_at=cookie_expires_at)
        return jsonify({"ok": False, "error": str(e)})


# ─── Token Refresh (Pure Python — Cookie → Token via Portal API) ────

@icm_bp.route('/token/refresh', methods=['POST'])
@require_auth
def token_refresh():
    """POST /api/icm/token/refresh - Refresh ICM access token using Cookie (pure Python)."""
    result = _do_token_refresh()
    _record_token_history(result, "manual")
    if result["ok"]:
        return jsonify({"ok": True, "message": result["message"],
                        "remaining_minutes": round(result["remaining_min"], 1)})
    else:
        return jsonify({"ok": False, "error": result["message"]}), 500


# ─── Token History Helpers ────────────────────────────────────

def _save_verify_history(success, obtained_at, expires_at, remaining_min, error_message, detail,
                         cookie_expires_at=None):
    """Save a verify operation to the ICM token history."""
    task_queue.save_icm_token_history(
        action="verify", success=success, got_new_token=None,
        token_obtained_at=obtained_at, token_expires_at=expires_at,
        remaining_min=remaining_min, error_message=error_message,
        detail=json.dumps(detail, ensure_ascii=False) if detail else "",
        cookie_expires_at=cookie_expires_at)


def _record_token_history(result, source):
    """Record a refresh operation to the ICM token history.

    Args:
        result: dict from _do_token_refresh()
        source: 'manual' or 'auto'
    """
    got_new = "yes" if result.get("ok") and result.get("old_token") != result.get("new_token") else None
    if not result.get("ok"):
        got_new = "no"
    detail_dict = {"source": source}
    task_queue.save_icm_token_history(
        action="refresh", success=result.get("ok", False), got_new_token=got_new,
        token_obtained_at=result.get("obtained_at", ""),
        token_expires_at=result.get("expires_at", ""),
        remaining_min=result.get("remaining_min", 0.0),
        error_message=result.get("error_message", ""),
        detail=json.dumps(detail_dict, ensure_ascii=False),
        cookie_updated=result.get("cookie_updated"),
        cookie_expires_at=result.get("cookie_expires_at"))


@icm_bp.route('/token/history', methods=['GET'])
@require_auth
def token_history():
    """GET /api/icm/token/history?page=1&size=20 - Paginated ICM token operation history."""
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 20, type=int)
    size = min(max(size, 1), 100)
    result = task_queue.list_icm_token_history(page, size)
    return jsonify({"ok": True, "total": result["total"], "page": result["page"],
                    "pages": result["pages"], "size": result["page_size"],
                    "data": result["data"]})


# ─── Query Incidents (Pure Python — fast, no PowerShell) ──────

def _get_token():
    """Load access_token from config, return it."""
    config_path = os.path.join(_get_project_root(), 'IcMHelperPS', 'icm_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    return cfg.get('access_token', '')

def _icm_get(url: str, timeout: int = 30):
    """GET request to ICM API using token from config. Returns (data_dict, http_status)."""
    token = _get_token()
    req = urllib.request.Request(url, method='GET')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    return (json.loads(raw) if raw else {}), resp.status

def _icm_post(url: str, body: dict, timeout: int = 60):
    """POST request to ICM API. Returns (data_dict, http_status)."""
    token = _get_token()
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    return (json.loads(raw) if raw else {}), resp.status

def _icm_patch(url: str, body: dict, timeout: int = 60):
    """PATCH request to ICM API. Returns (data_dict, http_status)."""
    token = _get_token()
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='PATCH')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    return (json.loads(raw) if raw else {}), resp.status

@icm_bp.route('/search', methods=['GET'])
@require_auth
def search():
    """GET /api/icm/search?filter=...&top=10 - Query incidents (pure Python, no PowerShell).

    Query params:
        filter: OData filter string (e.g., "Severity eq 3")
        top: Max results (default 10)
    """
    filter_str = request.args.get('filter', '')
    top = request.args.get('top', 10, type=int)

    base = 'https://prod.microsofticm.com/api2/incidentapi/incidents'
    query_parts = [urllib.parse.urlencode({'$top': str(top)})]
    filters = ["OwningTeamId eq 37883"]
    if filter_str:
        filters.append(filter_str)
    query_parts.append(urllib.parse.urlencode({'$filter': ' and '.join(filters)}))
    url = base + '?' + '&'.join(query_parts)

    try:
        data, status = _icm_get(url)
        return jsonify({"ok": True, "data": data})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace') if e.fp else ''
        return jsonify({"ok": False, "error": f"HTTP {e.code}", "body": body}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@icm_bp.route('/<int:incident_id>', methods=['GET'])
@require_auth
def get_incident(incident_id: int):
    """GET /api/icm/<id> - Get single incident (pure Python)."""
    url = f'https://prod.microsofticm.com/api2/incidentapi/incidents?$filter=Id eq {incident_id}&$top=1'
    try:
        data, status = _icm_get(url)
        if isinstance(data, dict) and 'value' in data:
            items = data['value']
            if items:
                return jsonify({"ok": True, "data": items[0]})
            else:
                return jsonify({"ok": False, "error": f"Incident {incident_id} not found"}), 404
        return jsonify({"ok": True, "data": data})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace') if e.fp else ''
        return jsonify({"ok": False, "error": f"HTTP {e.code}", "body": body}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Create Incident ──────────────────────────────────────────

@icm_bp.route('/create', methods=['POST'])
@require_auth
def create():
    """POST /api/icm/create - Create a new ICM incident (pure Python, no PowerShell)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    def _do_create():
        now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        body = {
            "Id": 0,
            "Title": data.get("title", ""),
            "Description": data.get("description", "Incident Created"),
            "Summary": data.get("summary", ""),
            "CreatedDate": now_str,
            "LastModifiedDate": now_str,
            "OccuringLocation": {
                "Environment": "PROD",
                "Datacenter": None,
                "Role": None,
                "Instance": None,
                "Slice": None,
            },
            "IsSecurityRisk": data.get("is_security_risk", False),
            "IsCustomerImpacting": data.get("is_customer_impacting", False),
            "IsNoise": False,
            "State": "ACTIVE",
            "Severity": data.get("severity", 3),
            "Attachments": [],
            "CloudInstanceId": 3,
            "Type": data.get("type", "customerreported"),
            "OwningServiceId": data.get("owning_service_id", 20284),
            "OwningTeamId": data.get("owning_team_id", 37883),
            "IsAcknowledged": False,
            "Keywords": data.get("keywords", ""),
            "SubscriptionId": data.get("subscription_id", ""),
            "SupportTicketId": data.get("support_ticket_id", ""),
            "CustomerName": data.get("customer_name", ""),
            "LinkedIncidentCount": 0,
            "ExternalLinksCount": 0,
            "SourceCreateTime": now_str,
            "HitCount": 0,
            "ChildCount": 0,
            "ImpactedServices": data.get("impacted_services", [{"ServiceId": 20284}]),
            "ImpactedTeams": data.get("impacted_teams", []),
            "ImpactedComponents": data.get("impacted_components", []),
            "CustomFields": data.get("custom_fields", []),
        }

        url = "https://prod.microsofticm.com/api2/incidentapi/incidents"
        resp_data, status = _icm_post(url, body)
        return json.dumps(resp_data, ensure_ascii=False), "", 0

    task_id = task_queue.submit(_do_create, name="ICM Create")
    return jsonify({"task_id": task_id, "status": "running"})


# ─── Internal helpers for ICM operations (shared by single + batch) ────

def _ack_incident(iid: int):
    """Acknowledge a single incident (pure Python). Raises on error."""
    body = {"AcknowledgementParameters": {"AcknowledgeContactAlias": None}}
    url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})/AcknowledgeIncident'
    _icm_post(url, body)


def _update_description(iid: int, description: str):
    """Update incident description (pure Python). Raises on error."""
    body = {"Id": iid, "Description": description}
    url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})'
    _icm_patch(url, body)


def _mitigate_incidents(ids: list, message: str = ""):
    """Mitigate one or more incidents via Portal API (pure Python). Raises on error."""
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    html_msg = ""
    if message:
        html_msg = f'<div style="font-family: Calibri, Arial, Helvetica, sans-serif; font-size: 11pt; color: rgb(0, 0, 0);">{message}<br></div>'
    body = {
        "Description": html_msg,
        "incidentIds": ids,
        "HowFixed": "Other",
        "IsCustomerImpacting": False,
        "MitigationTimeStamp": now_str,
        "CustomFields": [],
        "IsNoise": False,
        "RootCauseNeedsInvestigation": False,
        "AutoResolve": False,
    }
    _icm_post_portal("https://portal.microsofticm.com/imp/api/incident/Mitigate", body)


def _set_rootcause(iid: int, category: str, description: str = "", title: str = ""):
    """Set root cause for a single incident (pure Python). Raises on error."""
    body = {
        "Id": iid,
        "ImpactedEntities": [],
        "RootCause": {
            "Category": category,
            "Description": description or "",
            "Title": title or "",
            "IsCausedByChange": "false",
            "SubCategory": "",
            "AdditionalData": "{}",
        }
    }
    url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})'
    _icm_patch_portal(url, body)


def _resolve_incidents(ids: list, message: str = ""):
    """Resolve one or more incidents via Portal API (pure Python). Raises on error."""
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    body = {
        "HowFixed": "Other",
        "Description": message or "",
        "incidentIds": ids,
        "IsCustomerImpacting": False,
        "ImpactStartTime": now_str,
        "IsNoise": False,
        "CustomFields": [],
        "RootCauseOption": 5,
    }
    _icm_post_portal("https://portal.microsofticm.com/imp/api/incident/Resolve", body)


def _resolve_full(iid: int, message: str, rc_cat: str):
    """Full resolve flow: Mitigate → RootCause → Resolve (pure Python). Raises on error."""
    logger.info("Resolve full step1 (mitigate) for %d", iid)
    _mitigate_incidents([iid], message)

    logger.info("Resolve full step2 (rootcause) for %d", iid)
    _set_rootcause(iid, rc_cat, message, message)

    logger.info("Resolve full step3 (resolve) for %d", iid)
    _resolve_incidents([iid], message)


# ─── Incident Operations ──────────────────────────────────────

@icm_bp.route('/<int:incident_id>/ack', methods=['POST'])
@require_auth
def acknowledge(incident_id: int):
    """POST /api/icm/<id>/ack - Acknowledge an incident (pure Python)."""
    try:
        _ack_incident(incident_id)
        return jsonify({"ok": True, "id": incident_id})
    except urllib.error.HTTPError as e:
        if e.code == 400:
            logger.info("Ack skipped for %d: already acknowledged", incident_id)
            return jsonify({"ok": False, "id": incident_id, "error": "工单已被 Ack，无需重复操作"}), 400
        logger.error("Ack failed for %d: %s", incident_id, e)
        return jsonify({"ok": False, "id": incident_id, "error": f"Ack 失败: HTTP {e.code}"}), 500
    except Exception as e:
        logger.error("Ack failed for %d: %s", incident_id, e)
        return jsonify({"ok": False, "id": incident_id, "error": str(e)}), 500


@icm_bp.route('/<int:incident_id>/discussion', methods=['POST'])
@require_auth
def add_discussion(incident_id: int):
    """POST /api/icm/<id>/discussion - Add discussion/update description (pure Python).

    Body: {"description": "new description text"}
    """
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "description field required"}), 400

    try:
        _update_description(incident_id, data["description"])
        return jsonify({"ok": True, "id": incident_id})
    except Exception as e:
        logger.error("Discussion update failed for %d: %s", incident_id, e)
        return jsonify({"ok": False, "id": incident_id, "error": str(e)}), 500


@icm_bp.route('/<int:incident_id>/mitigate', methods=['POST'])
@require_auth
def mitigate(incident_id: int):
    """POST /api/icm/<id>/mitigate - Mitigate an incident (pure Python).

    Body: {"message": "mitigation message"}
    """
    data = request.get_json() or {}
    message = data.get("message", "Mitigated")

    try:
        _mitigate_incidents([incident_id], message)
        return jsonify({"ok": True, "id": incident_id})
    except urllib.error.HTTPError as e:
        if e.code == 400:
            logger.info("Mitigate skipped for %d: may already be mitigated", incident_id)
            return jsonify({"ok": False, "id": incident_id, "error": "工单可能已被 Mitigate，无需重复操作"}), 400
        logger.error("Mitigate failed for %d: HTTP %d", incident_id, e.code)
        return jsonify({"ok": False, "id": incident_id, "error": f"Mitigate 失败: HTTP {e.code}"}), 500
    except Exception as e:
        logger.error("Mitigate failed for %d: %s", incident_id, e)
        return jsonify({"ok": False, "id": incident_id, "error": str(e)}), 500


@icm_bp.route('/<int:incident_id>/resolve', methods=['POST'])
@require_auth
def resolve(incident_id: int):
    """POST /api/icm/<id>/resolve - Full resolve flow (Mitigate -> RootCause -> Resolve, pure Python).

    Body: {
        "message": "resolution message",
        "root_cause_category": "..."
    }
    """
    data = request.get_json() or {}
    message = data.get("message", "Resolved")
    rc_cat = data.get("root_cause_category", "Other")

    def _do_resolve():
        _resolve_full(incident_id, message, rc_cat)
        return json.dumps({"ok": True, "id": incident_id}), "", 0

    task_id = task_queue.submit(_do_resolve, name="ICM Resolve")
    return jsonify({"task_id": task_id, "status": "running"})


# ─── Batch Operations (Pure Python — fast, no PowerShell) ──────

def _icm_post_portal(url: str, body: dict, timeout: int = 60):
    """POST to Portal API with Origin/Referer headers. Handles empty response body."""
    token = _get_token()
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('Origin', 'https://portal.microsofticm.com')
    req.add_header('Referer', 'https://portal.microsofticm.com/')
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    return (json.loads(raw) if raw else {}), resp.status

def _icm_patch_portal(url: str, body: dict, timeout: int = 60):
    """PATCH to ICM API with Portal Origin/Referer headers. Handles empty response body."""
    token = _get_token()
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='PATCH')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('Origin', 'https://portal.microsofticm.com')
    req.add_header('Referer', 'https://portal.microsofticm.com/')
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    return (json.loads(raw) if raw else {}), resp.status

@icm_bp.route('/batch', methods=['POST'])
@require_auth
def batch_action():
    """POST /api/icm/batch - Batch operation on multiple incidents.

    Body: {
        "action": "ack" | "discussion" | "mitigate" | "resolve",
        "incident_ids": [123, 456, ...],
        "message": "...",          // optional, for discussion/mitigate/resolve
        "root_cause_category": "Other"  // optional, for resolve
    }
    """
    req_data = request.get_json()
    if not req_data:
        return jsonify({"error": "JSON body required"}), 400

    action = req_data.get("action", "")
    ids = req_data.get("incident_ids", [])
    message = req_data.get("message", "")
    rc_cat = req_data.get("root_cause_category", "Other")

    if action not in ("ack", "discussion", "mitigate", "resolve"):
        return jsonify({"error": f"Unknown action: {action}"}), 400
    if not ids:
        return jsonify({"error": "No incident IDs provided"}), 400

    results = []
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if action == "ack":
        for iid in ids:
            try:
                _ack_incident(iid)
                results.append({"id": iid, "ok": True})
            except Exception as e:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "discussion":
        for iid in ids:
            try:
                _update_description(iid, message)
                results.append({"id": iid, "ok": True})
            except Exception as e:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "mitigate":
        try:
            _mitigate_incidents(ids, message)
            for iid in ids:
                results.append({"id": iid, "ok": True})
        except Exception as e:
            for iid in ids:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "resolve":
        # Step 1: Mitigate (batch via Portal API)
        mitigate_failed = set()
        try:
            _mitigate_incidents(ids, message)
            logger.info("Batch resolve step1 (mitigate) OK for %d incidents", len(ids))
        except Exception as e:
            logger.error("Batch resolve step1 (mitigate) failed: %s", e)
            mitigate_failed.update(ids)

        # Step 2: RootCause (per-incident PATCH via api2)
        rootcause_failed = set()
        for iid in ids:
            try:
                _set_rootcause(iid, rc_cat, message, message)
            except Exception as e:
                logger.error("Batch resolve step2 (rootcause) failed for %d: %s", iid, e)
                rootcause_failed.add(iid)

        # Step 3: Resolve (batch via Portal API)
        resolve_failed = set()
        try:
            _resolve_incidents(ids, message)
            logger.info("Batch resolve step3 (resolve) OK for %d incidents", len(ids))
        except Exception as e:
            logger.error("Batch resolve step3 (resolve) failed: %s", e)
            resolve_failed.update(ids)

        # Combine results per-ID
        for iid in ids:
            errors = []
            if iid in mitigate_failed:
                errors.append("mitigate failed")
            if iid in rootcause_failed:
                errors.append("rootcause failed")
            if iid in resolve_failed:
                errors.append("resolve failed")
            if errors:
                results.append({"id": iid, "ok": False, "error": "; ".join(errors)})
            else:
                results.append({"id": iid, "ok": True})

    ok_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - ok_count

    return jsonify({
        "ok": True,
        "action": action,
        "total": len(results),
        "succeeded": ok_count,
        "failed": fail_count,
        "results": results,
    })


# ─── On-Call Query (Pure Python) ──────────────────────────────

@icm_bp.route('/oncall', methods=['GET'])
@require_auth
def oncall():
    """GET /api/icm/oncall - Query current on-call personnel (pure Python).

    Query params:
        team_ids: comma-separated team IDs (default: 37883)
    """
    team_ids_str = request.args.get('team_ids', '37883')
    team_ids = [int(x.strip()) for x in team_ids_str.split(',') if x.strip()]

    try:
        body = {"TeamIds": team_ids}
        url = "https://oncallapi.prod.microsofticm.com/Directory/GetCurrentOnCallForCurrentShiftForTeams"
        data, status = _icm_post(url, body)
        return jsonify({"ok": True, "data": data})
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors='replace') if e.fp else ''
        return jsonify({"ok": False, "error": f"HTTP {e.code}", "body": body_text}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
