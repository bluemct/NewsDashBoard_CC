"""ICM module - wrapper for IcMHelperPS PowerShell functions."""
import os
import json
import logging
from datetime import datetime
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
    """GET /api/icm/token/verify - Verify ICM token is valid."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Test-IcmToken",
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


@icm_bp.route('/token/refresh', methods=['POST'])
@require_auth
def token_refresh():
    """POST /api/icm/token/refresh - Refresh ICM access token."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Reset-IcmToken",
    )
    return jsonify({"stdout": stdout, "stderr": stderr, "returncode": rc})


# ─── Query Incidents ──────────────────────────────────────────

@icm_bp.route('/search', methods=['GET'])
@require_auth
def search():
    """GET /api/icm/search?filter=...&top=10 - Query incidents.

    Query params:
        filter: OData filter string (e.g., "Severity eq 3")
        top: Max results (default 10)
    """
    filter_str = request.args.get('filter', '')
    top = request.args.get('top', 10, type=int)

    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Get-IcmIncidents",
        {"Top": top, "Filter": filter_str} if filter_str else {"Top": top},
    )

    if rc != 0:
        return jsonify({"error": stderr, "stdout": stdout}), 500

    # Parse JSON output from PowerShell
    try:
        # PowerShell may output JSON with extra whitespace
        json_str = stdout.strip()
        data = json.loads(json_str)
        return jsonify({"ok": True, "data": data})
    except json.JSONDecodeError:
        return jsonify({"ok": True, "raw": stdout.strip()})


@icm_bp.route('/<int:incident_id>', methods=['GET'])
@require_auth
def get_incident(incident_id: int):
    """GET /api/icm/<id> - Get single incident."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Get-IcmIncident",
        {"Id": incident_id},
    )

    if rc != 0:
        return jsonify({"error": stderr, "stdout": stdout}), 500

    try:
        data = json.loads(stdout.strip())
        return jsonify({"ok": True, "data": data})
    except json.JSONDecodeError:
        return jsonify({"ok": True, "raw": stdout.strip()})


# ─── Create Incident ──────────────────────────────────────────

@icm_bp.route('/create', methods=['POST'])
@require_auth
def create():
    """POST /api/icm/create - Create a new ICM incident.

    Body: {
        "title": "...",
        "description": "...",
        "severity": 3,
        "type": "LiveSite",
        "impacted_services": [{"ServiceId": 20284}],
        "occuring_location": "All Production",
        "reported_source": "Customer Reported"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # Capture path before background thread
    ps_path = _icm_ps_path()

    def _do_create(pp):
        params = {
            "Title": data.get("title", ""),
            "Description": data.get("description", ""),
            "Severity": data.get("severity", 3),
            "Type": data.get("type", "LiveSite"),
            "OccuringLocation": data.get("occuring_location", "All Production"),
            "ReportedSource": data.get("reported_source", "Customer Reported"),
            "OwningServiceId": data.get("owning_service_id", 20284),
            "OwningTeamId": data.get("owning_team_id", 37883),
        }
        impacted = data.get("impacted_services")
        if impacted:
            params["ImpactedServices"] = json.dumps(impacted)

        stdout, stderr, rc = run_powershell_function(
            pp,
            "New-IcmIncident",
            params,
        )
        return stdout, stderr, rc

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
        {"Id": incident_id},
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
        {"Id": incident_id, "Description": data["description"]},
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
        {"Id": incident_id, "Message": message},
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
        params = {
            "Id": incident_id,
            "Message": data.get("message", "Resolved"),
            "RootCauseCategory": data.get("root_cause_category", "Other"),
            "RootCauseTitle": data.get("root_cause_title", "Resolved"),
        }
        stdout, stderr, rc = run_powershell_function(
            pp,
            "Resolve-IcmIncidentFull",
            params,
        )
        return stdout, stderr, rc

    task_id = task_queue.submit(_do_resolve, ps_path, name="ICM Resolve")
    return jsonify({"task_id": task_id, "status": "running"})


# ─── On-Call Query ────────────────────────────────────────────

@icm_bp.route('/oncall', methods=['GET'])
@require_auth
def oncall():
    """GET /api/icm/oncall - Query current on-call personnel."""
    stdout, stderr, rc = run_powershell_function(
        _icm_ps_path(),
        "Get-IcmOnCall",
    )

    if rc != 0:
        return jsonify({"error": stderr, "stdout": stdout}), 500

    try:
        data = json.loads(stdout.strip())
        return jsonify({"ok": True, "data": data})
    except json.JSONDecodeError:
        return jsonify({"ok": True, "raw": stdout.strip()})
