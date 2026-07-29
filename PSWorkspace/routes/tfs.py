"""TFS (Azure DevOps) module - REST API + webhook handler."""
import os
import json
import base64
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, g, current_app
from routes.auth import require_auth
from utils import task_queue

logger = logging.getLogger(__name__)

tfs_bp = Blueprint('tfs', __name__, url_prefix='/api/tfs')

# In-memory webhook log
_webhook_log = []
MAX_WEBHOOK_LOG = 100


def _get_project_root():
    return current_app.config.get('PROJECT_ROOT', os.getcwd())


def _load_config():
    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_tfs_headers():
    """Build Azure DevOps auth headers from config."""
    import base64
    config = _load_config()
    tfs = config.get("tfs", {})
    pat = tfs.get("pat", "")
    if pat:
        credentials = base64.b64encode(f":{pat}".encode()).decode()
        return {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def _tfs_base_url():
    config = _load_config()
    tfs = config.get("tfs", {})
    org = tfs.get("organization", "21vianet-azure")
    return f"https://dev.azure.com/{org}"


def _tfs_project():
    config = _load_config()
    return config.get("tfs", {}).get("project", "21ViaNet-Project")


# ─── Webhook Handler ──────────────────────────────────────────

@tfs_bp.route('/webhook', methods=['POST'])
def webhook():
    """POST /api/tfs/webhook - Receive Azure DevOps webhook events.

    This endpoint is NOT auth-protected - it's called by Azure DevOps.
    Optionally check webhook secret if configured.
    """
    # Optional secret check
    config = _load_config()
    secret = config.get("webhook", {}).get("secret", "")
    if secret:
        provided = request.headers.get('X-Webhook-Secret', '')
        if provided != secret:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = data.get("eventType", "")
    resource = data.get("resource", {})
    fields = resource.get("fields", {})

    # Extract work item info
    work_item = {
        "id": resource.get("id"),
        "rev": resource.get("rev"),
        "event_type": event_type,
        "work_item_type": fields.get("System.WorkItemType", ""),
        "title": fields.get("System.Title", ""),
        "description": fields.get("System.Description", ""),
        "assigned_to": fields.get("System.AssignedTo", {}).get("displayName", "") if isinstance(fields.get("System.AssignedTo"), dict) else str(fields.get("System.AssignedTo", "")),
        "team_project": fields.get("System.TeamProject", ""),
        "url": resource.get("url", ""),
        "state": fields.get("System.State", ""),
        "received_at": datetime.now().isoformat(),
    }

    # Add to log
    _webhook_log.append(work_item)
    if len(_webhook_log) > MAX_WEBHOOK_LOG:
        _webhook_log.pop(0)

    logger.info(f"TFS Webhook: {event_type} - WI#{work_item['id']} {work_item['title']}")

    # TODO: Add auto-processing logic here based on event_type
    # e.g., auto-create ICM incident for certain Request types

    return jsonify({"ok": True, "work_item_id": work_item.get("id")})


# ─── Query Work Item ──────────────────────────────────────────

@tfs_bp.route('/workitem/<int:work_item_id>', methods=['GET'])
@require_auth
def get_workitem(work_item_id: int):
    """GET /api/tfs/workitem/<id> - Get work item details via REST API."""
    import requests

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0&$expand=fields"

    try:
        resp = requests.get(url, headers=_get_tfs_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return jsonify({"ok": True, "data": data})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@tfs_bp.route('/workitem/<int:work_item_id>/update', methods=['POST'])
@require_auth
def update_workitem(work_item_id: int):
    """PATCH work item fields via REST API.

    Body: {"fields": {"System.Description": "new desc", ...}}
    """
    import requests

    data = request.get_json()
    if not data or "fields" not in data:
        return jsonify({"error": "Body must contain 'fields' object"}), 400

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0"

    # Azure DevOps PATCH uses application/json-patch+content-type
    fields = data["fields"]
    patches = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items()]

    try:
        resp = requests.patch(
            url,
            headers={"Authorization": _get_tfs_headers().get("Authorization", ""),
                      "Content-Type": "application/json-patch+json"},
            json=patches,
            timeout=30,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "data": resp.json()})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Update Labor Time ────────────────────────────────────────

@tfs_bp.route('/update-labor', methods=['POST'])
@require_auth
def update_labor():
    """POST /api/tfs/update-labor - Update Labor Time field on a work item.

    Body: {"work_item_id": 12345, "labor_time": 8.0}
    """
    import requests

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    work_item_id = data.get("work_item_id")
    labor_time = data.get("labor_time")

    if not work_item_id or labor_time is None:
        return jsonify({"error": "work_item_id and labor_time required"}), 400

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0"

    # Update both display and value fields
    patches = [
        {"op": "add", "path": "/fields/Hisoft.21ViaNet.TotalLaborTimeShow", "value": str(labor_time)},
        {"op": "add", "path": "/fields/Hisoft.21ViaNet.TotalLaborTime", "value": labor_time},
    ]

    try:
        resp = requests.patch(
            url,
            headers={"Authorization": _get_tfs_headers().get("Authorization", ""),
                      "Content-Type": "application/json-patch+json"},
            json=patches,
            timeout=30,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "message": f"Updated WI#{work_item_id} Labor Time to {labor_time}"})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Webhook Log ──────────────────────────────────────────────

@tfs_bp.route('/recent', methods=['GET'])
@require_auth
def recent():
    """GET /api/tfs/recent - Get recent webhook events."""
    max_items = request.args.get('max', 50, type=int)
    return jsonify({"webhooks": list(reversed(_webhook_log[:max_items]))})
