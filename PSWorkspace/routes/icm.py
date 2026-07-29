"""ICM module - wrapper for IcMHelperPS PowerShell functions."""
import os
import json
import logging
import subprocess
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g, current_app
from routes.auth import require_auth
from utils.script_runner import run_powershell, run_powershell_function
from utils import task_queue

logger = logging.getLogger(__name__)

icm_bp = Blueprint('icm', __name__, url_prefix='/api/icm')


def _get_project_root():
    return current_app.config.get('PROJECT_ROOT', os.getcwd())


def _load_config():
    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _icm_ps_path():
    config = _load_config()
    ps_file = config['paths']['icm_ps']
    if os.path.isabs(ps_file):
        return ps_file
    return os.path.join(_get_project_root(), ps_file)


# ─── Token Management ─────────────────────────────────────────

@icm_bp.route('/token/verify', methods=['GET'])
@require_auth
def token_verify():
    """GET /api/icm/token/verify - Verify ICM token is valid (Python-native, no PowerShell)."""
    try:
        # Load config
        config_path = os.path.join(_get_project_root(), 'IcMHelperPS', 'icm_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        token = cfg.get('access_token', '')
        if not token:
            return jsonify({"ok": False, "error": "No access_token in config"}), 400

        # Parse JWT expiry
        parts = token.split('.')
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4) if len(payload) % 4 else ''
        payload = payload.replace('-', '+').replace('_', '/')
        dec = json.loads(base64.b64decode(payload))
        exp = datetime.fromtimestamp(dec['exp'], tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        remaining_min = (exp - now).total_seconds() / 60

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

        return jsonify({
            "ok": is_valid,
            "expiring_at": exp.strftime('%Y-%m-%d %H:%M:%S UTC'),
            "remaining_minutes": round(remaining_min, 1),
            "incidents_returned": count,
        })
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return jsonify({"ok": False, "error": "Token expired or invalid (401)"})
        return jsonify({"ok": False, "error": f"HTTP {e.code}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@icm_bp.route('/token/refresh', methods=['POST'])
@require_auth
def token_refresh():
    """POST /api/icm/token/refresh - Refresh ICM access token."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Reset-IcmToken",
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


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
    return json.loads(resp.read()), resp.status

def _icm_post(url: str, body: dict, timeout: int = 60):
    """POST request to ICM API. Returns (data_dict, http_status)."""
    token = _get_token()
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json')
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read()), resp.status

def _icm_patch(url: str, body: dict, timeout: int = 60):
    """PATCH request to ICM API. Returns (data_dict, http_status)."""
    token = _get_token()
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='PATCH')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json')
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read()), resp.status

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
    """POST /api/icm/create - Create a new ICM incident.

    Build PowerShell command inline — mirror IcmApi.ps1 two-step flow:
      New-IcmIncident (construct object) → New-IcmIncidentApi (POST to API)
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # Capture path before background thread
    ps_path = _icm_ps_path()

    def _do_create(pp):
        title = data.get("title", "").replace("'", "''")
        desc = data.get("description", "").replace("'", "''")
        severity = data.get("severity", 3)
        inc_type = data.get("type", "LiveSite")
        owning_svc = data.get("owning_service_id", 20284)
        owning_team = data.get("owning_team_id", 37883)

        # Build PS hashtable array for impacted services
        impacted = data.get("impacted_services")
        svc_ps = ""
        if impacted:
            parts = []
            for svc in impacted:
                sid = svc.get("ServiceId", svc) if isinstance(svc, dict) else svc
                parts.append(f"@{{ ServiceId = {sid} }}")
            svc_ps = f" -ImpactedServices @({', '.join(parts)})"

        ps_cmd = (
            f". '{pp}'; "
            f"$inc = New-IcmIncident "
            f"-Title '{title}' "
            f"-Description '{desc}' "
            f"-Severity {severity} "
            f"-Type '{inc_type}' "
            f"-OwningServiceId {owning_svc} "
            f"-OwningTeamId {owning_team}"
            f"{svc_ps}; "
            f"New-IcmIncidentApi -Incident $inc | ConvertTo-Json -Depth 3"
        )

        full_cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", ps_cmd,
        ]

        logger.info(f"Running ICM Create: {ps_cmd[:200]}")
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return result.stdout, result.stderr, result.returncode

    task_id = task_queue.submit(_do_create, ps_path, name="ICM Create")
    return jsonify({"task_id": task_id, "status": "running"})


# ─── Incident Operations ──────────────────────────────────────

@icm_bp.route('/<int:incident_id>/ack', methods=['POST'])
@require_auth
def acknowledge(incident_id: int):
    """POST /api/icm/<id>/ack - Acknowledge an incident."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Ack-IcmIncident",
        {"IncidentId": incident_id},
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


@icm_bp.route('/<int:incident_id>/discussion', methods=['POST'])
@require_auth
def add_discussion(incident_id: int):
    """POST /api/icm/<id>/discussion - Add discussion/update description.

    Body: {"description": "new description text"}
    """
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "description field required"}), 400

    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Add-IcmDiscussion",
        {"IncidentId": incident_id, "Description": data["description"]},
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


@icm_bp.route('/<int:incident_id>/mitigate', methods=['POST'])
@require_auth
def mitigate(incident_id: int):
    """POST /api/icm/<id>/mitigate - Mitigate an incident.

    Body: {"message": "mitigation message"}
    """
    data = request.get_json() or {}
    message = data.get("message", "Mitigated")

    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Mitigate-IcmIncident",
        {"IncidentId": incident_id, "Message": message},
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


@icm_bp.route('/<int:incident_id>/resolve', methods=['POST'])
@require_auth
def resolve(incident_id: int):
    """POST /api/icm/<id>/resolve - Full resolve flow (Mitigate -> RootCause -> Resolve).

    Body: {
        "message": "resolution message",
        "root_cause_category": "...",
        "root_cause_title": "..."
    }
    """
    data = request.get_json() or {}

    # Capture path before background thread
    ps_path = _icm_ps_path()

    def _do_resolve(pp):
        msg = data.get("message", "Resolved").replace("'", "''")
        rc_cat = data.get("root_cause_category", "Other").replace("'", "''")

        ps_cmd = (
            f". '{pp}'; "
            f"Resolve-IcmIncidentFull "
            f"-IncidentId {incident_id} "
            f"-Message '{msg}' "
            f"-RootCauseCategory '{rc_cat}'"
        )

        full_cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", ps_cmd,
        ]

        logger.info(f"Running ICM Resolve: {ps_cmd[:200]}")
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return result.stdout, result.stderr, result.returncode

    task_id = task_queue.submit(_do_resolve, ps_path, name="ICM Resolve")
    return jsonify({"task_id": task_id, "status": "running"})


# ─── Batch Operations (Pure Python — fast, no PowerShell) ──────

def _icm_post_portal(url: str, body: dict, timeout: int = 60):
    """POST to Portal API with Origin/Referer headers."""
    token = _get_token()
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/json, text/plain, */*')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Origin', 'https://portal.microsofticm.com')
    req.add_header('Referer', 'https://portal.microsofticm.com/')
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read()), resp.status

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
                body = {"AcknowledgementParameters": {"AcknowledgeContactAlias": None}}
                url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})/AcknowledgeIncident'
                _icm_post(url, body)
                results.append({"id": iid, "ok": True})
            except Exception as e:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "discussion":
        for iid in ids:
            try:
                body = {"Id": iid, "Description": message}
                url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})'
                _icm_patch(url, body)
                results.append({"id": iid, "ok": True})
            except Exception as e:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "mitigate":
        # Portal Mitigate API supports multiple incidentIds in one call
        html_msg = ""
        if message:
            html_msg = f'<div style="font-family: Calibri, Arial, Helvetica, sans-serif; font-size: 11pt; color: rgb(0, 0, 0);">{message}<br></div>'
        try:
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
            for iid in ids:
                results.append({"id": iid, "ok": True})
        except Exception as e:
            for iid in ids:
                results.append({"id": iid, "ok": False, "error": str(e)})

    elif action == "resolve":
        # Step 1: Mitigate (batch)
        html_msg = ""
        if message:
            html_msg = f'<div style="font-family: Calibri, Arial, Helvetica, sans-serif; font-size: 11pt; color: rgb(0, 0, 0);">{message}<br></div>'
        try:
            mit_body = {
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
            _icm_post_portal("https://portal.microsofticm.com/imp/api/incident/Mitigate", mit_body)

            # Step 2: RootCause (per-incident PATCH)
            for iid in ids:
                rc_body = {
                    "Id": iid,
                    "ImpactedEntities": [],
                    "RootCause": {
                        "Category": rc_cat,
                        "Description": message or "",
                        "Title": message or "",
                        "IsCausedByChange": "false",
                        "SubCategory": "",
                        "AdditionalData": "{}",
                    }
                }
                url = f'https://prod.microsofticm.com/api2/incidentapi/incidents({iid})'
                _icm_patch(url, rc_body)

            # Step 3: Resolve (batch)
            res_body = {
                "HowFixed": "Other",
                "Description": message or "",
                "incidentIds": ids,
                "IsCustomerImpacting": False,
                "ImpactStartTime": now_str,
                "IsNoise": False,
                "CustomFields": [],
                "RootCauseOption": 5,
            }
            _icm_post_portal("https://portal.microsofticm.com/imp/api/incident/Resolve", res_body)

            for iid in ids:
                results.append({"id": iid, "ok": True})
        except Exception as e:
            for iid in ids:
                results.append({"id": iid, "ok": False, "error": str(e)})

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


# ─── On-Call Query ────────────────────────────────────────────

@icm_bp.route('/oncall', methods=['GET'])
@require_auth
def oncall():
    """GET /api/icm/oncall - Query current on-call personnel.

    Query params:
        team_ids: comma-separated team IDs (default: 37883)
    """
    team_ids_str = request.args.get('team_ids', '37883')
    team_ids = [int(x.strip()) for x in team_ids_str.split(',') if x.strip()]
    ids_str = ','.join(str(t) for t in team_ids)

    ps_cmd = (
        f". '{_icm_ps_path()}'; "
        f"Get-IcmOnCall -TeamIds {ids_str}"
    )

    full_cmd = [
        "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-Command", ps_cmd,
    ]

    result = subprocess.run(
        full_cmd,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )

    if result.returncode != 0:
        return jsonify({"error": result.stderr, "stdout": result.stdout}), 500

    try:
        data = json.loads(result.stdout.strip())
        return jsonify({"ok": True, "data": data})
    except json.JSONDecodeError:
        return jsonify({"ok": True, "raw": result.stdout.strip()})
