"""Settings module - manage EDM, ICM, and AI config files via REST API."""
import os
import json
import logging
from flask import Blueprint, jsonify, request
from routes.auth import require_auth
from utils import task_queue

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# ─── Helpers ──────────────────────────────────────────────────

def _project_root():
    """Get project root (parent of PSWorkspace/)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read_json(path: str) -> dict:
    """Read a JSON file, return dict."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(path: str, data: dict):
    """Write dict to JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _mask(value: str, visible: int = 6) -> str:
    """Mask sensitive value, showing first `visible` chars."""
    if not value or len(value) <= visible:
        return "****"
    return value[:visible] + "****"


def _merge(existing: dict, incoming: dict, skip_empty: bool = True):
    """Merge incoming dict into existing. If skip_empty, empty strings are ignored."""
    for key, val in incoming.items():
        if isinstance(val, dict) and key in existing and isinstance(existing[key], dict):
            _merge(existing[key], val, skip_empty)
        elif not (skip_empty and val == ""):
            existing[key] = val


# ─── EDM Config ────────────────────────────────────────────────

@settings_bp.route('/edm', methods=['GET'])
@require_auth
def settings_edm_get():
    """GET /api/settings/edm - Read EDM listener & processing config."""
    root = _project_root()
    cfg = _read_json(os.path.join(root, ".edm_agent_config.json"))
    xlsx_dir = _read_json(os.path.join(root, "xlsx_search_dir.json"))

    ews = cfg.get("ews", {})
    filter_rules = cfg.get("filter_rules", {})

    return jsonify({
        "ok": True,
        "ews": {
            "url": ews.get("url", ""),
            "domain_user": ews.get("domain_user", ""),
            "password": _mask(ews.get("password", "")),
            "mailbox": ews.get("mailbox", ""),
            "folder_name": ews.get("folder_name", ""),
        },
        "filter_rules": {
            "sender": ", ".join(filter_rules.get("sender", [])),
            "subject_keywords": ", ".join(filter_rules.get("subject_keywords", [])),
            "body_keywords": ", ".join(filter_rules.get("body_keywords", [])),
        },
        "output_base": cfg.get("output_base", ""),
        "xlsx_search_directory": xlsx_dir.get("search_directory", ""),
    })


@settings_bp.route('/edm', methods=['POST'])
@require_auth
def settings_edm_save():
    """POST /api/settings/edm - Save EDM config."""
    root = _project_root()
    data = request.get_json() or {}
    ews_data = data.get("ews", {})
    filter_data = data.get("filter_rules", {})

    # Read and merge ews config
    cfg = _read_json(os.path.join(root, ".edm_agent_config.json"))
    _merge(cfg.setdefault("ews", {}), ews_data)

    # Rebuild filter_rules from comma-separated strings
    cfg["filter_rules"] = {
        "sender": [s.strip() for s in filter_data.get("sender", "").split(",") if s.strip()],
        "subject_keywords": [s.strip() for s in filter_data.get("subject_keywords", "").split(",") if s.strip()],
        "body_keywords": [s.strip() for s in filter_data.get("body_keywords", "").split(",") if s.strip()],
    }
    # Handle output_base from top-level
    if data.get("output_base"):
        cfg["output_base"] = data["output_base"]

    _write_json(os.path.join(root, ".edm_agent_config.json"), cfg)

    # Save xlsx search directory
    if data.get("xlsx_search_directory"):
        xlsx_dir = _read_json(os.path.join(root, "xlsx_search_dir.json"))
        xlsx_dir["search_directory"] = data["xlsx_search_directory"]
        _write_json(os.path.join(root, "xlsx_search_dir.json"), xlsx_dir)

    logger.info("EDM settings saved")
    task_queue.save_activity("settings", "EDM 配置更新",
                             "监听邮箱 / 规则 / 路径配置已保存", "ok")
    return jsonify({"ok": True, "message": "EDM 配置已保存"})


# ─── ICM Config ────────────────────────────────────────────────

@settings_bp.route('/icm', methods=['GET'])
@require_auth
def settings_icm_get():
    """GET /api/settings/icm - Read ICM token & cookie config."""
    root = _project_root()
    cfg = _read_json(os.path.join(root, "IcMHelperPS", "icm_config.json"))
    return jsonify({
        "ok": True,
        "access_token": _mask(cfg.get("access_token", "")),
        "cookie_string": cfg.get("cookie_string", ""),
        "cookie_expires": cfg.get("cookie_expires", ""),
    })


@settings_bp.route('/icm', methods=['POST'])
@require_auth
def settings_icm_save():
    """POST /api/settings/icm - Save ICM cookie/token config."""
    root = _project_root()
    data = request.get_json() or {}

    # Read original configs
    orig_path = os.path.join(root, "IcMHelper", "icm_config.json")
    ps_path = os.path.join(root, "IcMHelperPS", "icm_config.json")
    orig_cfg = _read_json(orig_path)

    # Merge only non-empty fields
    if data.get("cookie_string"):
        orig_cfg["cookie_string"] = data["cookie_string"]
    if data.get("cookie_expires"):
        orig_cfg["cookie_expires"] = data["cookie_expires"]
    if data.get("access_token"):
        orig_cfg["access_token"] = data["access_token"]

    # Write to both locations
    _write_json(orig_path, orig_cfg)
    _write_json(ps_path, orig_cfg)

    logger.info("ICM settings saved")
    task_queue.save_activity("settings", "ICM Cookie/Token 配置更新",
                             "IcMHelper + IcMHelperPS 已同步", "ok")
    return jsonify({"ok": True, "message": "ICM 配置已保存"})


# ─── AI Model Config ───────────────────────────────────────────

@settings_bp.route('/ai', methods=['GET'])
@require_auth
def settings_ai_get():
    """GET /api/settings/ai - Read AI model config."""
    root = _project_root()
    cfg = _read_json(os.path.join(root, ".edm_agent_llm_config.json"))
    return jsonify({
        "ok": True,
        "model": cfg.get("model", ""),
        "api_base": cfg.get("api_base", ""),
        "api_key": _mask(cfg.get("api_key", "")),
        "timeout": cfg.get("timeout", 30),
    })


@settings_bp.route('/ai', methods=['POST'])
@require_auth
def settings_ai_save():
    """POST /api/settings/ai - Save AI model config."""
    root = _project_root()
    data = request.get_json() or {}
    cfg = _read_json(os.path.join(root, ".edm_agent_llm_config.json"))

    _merge(cfg, data)

    _write_json(os.path.join(root, ".edm_agent_llm_config.json"), cfg)

    logger.info("AI model settings saved")
    task_queue.save_activity("settings", "AI Model 配置更新",
                             f"Model: {data.get('model', '未变更')}", "ok")
    return jsonify({"ok": True, "message": "AI 配置已保存"})
