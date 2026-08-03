"""PS Workspace - Flask application entry point."""
import os
import sys
import json
import logging

from flask import Flask, render_template, jsonify, g, request, redirect

# BASE_DIR = PSWorkspace/ directory (where this script lives)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# PROJECT_ROOT = parent directory (AgentProject/) - used for script paths
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

# Ensure Log directory exists
os.makedirs(os.path.join(PROJECT_ROOT, "Log"), exist_ok=True)

from routes.auth import auth_bp, require_auth, get_current_user
from routes.edm_eml import edm_eml_bp as edm_bp, _set_project_root
from routes.tfs import tfs_bp
from routes.icm import icm_bp, _set_project_root as _set_icm_project_root, _start_auto_refresh
from routes.task import task_bp
from routes.settings import settings_bp
from utils import task_queue

# ─── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(PROJECT_ROOT, "Log", "ps_workspace.log"),
                           encoding="utf-8", errors="replace"),
    ],
)
logger = logging.getLogger("ps_workspace")

# ─── Load Config ──────────────────────────────────────────────

_config_path = os.path.join(BASE_DIR, "ps_workspace_config.json")
with open(_config_path, "r", encoding="utf-8") as f:
    _config = json.load(f)

# ─── App Factory ──────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Config
    app.config["BASE_DIR"] = BASE_DIR
    app.config["PROJECT_ROOT"] = PROJECT_ROOT

    # Initialize module-level state for background threads
    _set_project_root(PROJECT_ROOT)
    _set_icm_project_root(PROJECT_ROOT)

    # Initialize task queue SQLite
    task_queue.init(os.path.join(PROJECT_ROOT, "Log", "ps_workspace_tasks.db"))

    # Start ICM Token auto-refresh daemon (checks every 15 min)
    _start_auto_refresh()

    # Template auto-reload for development
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # ─── Register Blueprints ──────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(edm_bp)
    app.register_blueprint(tfs_bp)
    app.register_blueprint(icm_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(settings_bp)

    # Disable browser cache for all pages and static files in development
    @app.after_request
    def no_cache_response(response):
        if request.path != "/health":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # ─── Page Routes ──────────────────────────────────────────

    @app.route("/")
    def index():
        """Home page - JS handles auth verification via token."""
        return render_template("index.html", user={})

    @app.route("/login")
    def login_page():
        """Login page."""
        return render_template("login.html")

    # ─── Health Check ─────────────────────────────────────────

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": "PS Workspace"})

    return app


# ─── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()

    server_config = _config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 9000)

    logger.info(f"PS Workspace starting on {host}:{port}")
    logger.info(f"Base dir: {BASE_DIR}")
    logger.info(f"Project root: {PROJECT_ROOT}")

    app.config["TEMPLATES_AUTO_RELOAD"] = True

    app.run(host=host, port=port, debug=False)
