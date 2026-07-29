"""Task status API - query async task results."""
import logging
from flask import Blueprint, jsonify, g, request
from utils.task_queue import status as task_status, list_tasks as list_tasks_fn
from routes.auth import require_auth

logger = logging.getLogger(__name__)

task_bp = Blueprint('task', __name__, url_prefix='/api/task')


@task_bp.route('/<task_id>', methods=['GET'])
@require_auth
def get_task(task_id: str):
    """GET /api/task/<task_id> - Get task status and result."""
    result = task_status(task_id)
    if not result:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(result)


@task_bp.route('/', methods=['GET'])
@require_auth
def list_tasks():
    """GET /api/task/ - List recent tasks."""
    max_items = request.args.get('max', 50, type=int)
    tasks = list_tasks_fn(max_items)
    return jsonify({"tasks": tasks})
