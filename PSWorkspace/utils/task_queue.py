"""Async task queue for long-running operations."""
import uuid
import threading
import time
import logging
from typing import Dict, Any, Callable, Iterator

logger = logging.getLogger(__name__)

# In-memory task store
_tasks: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def run_task(name: str, generator: Iterator[str]) -> str:
    """Submit a generator-based task that yields progress strings.
    Returns task_id.

    Usage: run_task("my-task", my_generator())
    """
    task_id = str(uuid.uuid4())[:8]

    with _lock:
        _tasks[task_id] = {
            "status": "running",
            "name": name,
            "stdout": "",
            "stderr": "",
            "result": None,
            "returncode": None,
            "created_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_generator_task,
        args=(task_id, generator),
        daemon=True,
    )
    thread.start()
    return task_id


def _run_generator_task(task_id: str, generator: Iterator[str]):
    """Consume a generator, accumulate yielded strings as stdout."""
    try:
        output_parts = []
        for chunk in generator:
            output_parts.append(str(chunk))
            with _lock:
                _tasks[task_id]["stdout"] = "\n".join(output_parts)

        with _lock:
            _tasks[task_id].update({
                "status": "completed",
                "returncode": 0,
            })
    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        logger.exception(f"Task {task_id} failed: {e}")
        with _lock:
            _tasks[task_id].update({
                "status": "failed",
                "stderr": error_msg,
                "returncode": -1,
            })


def submit(func: Callable, *args, name: str = "", **kwargs) -> str:
    """Submit a function to run in a background thread. Returns task_id.

    Usage: submit(my_func, arg1, arg2, name="Task Name", kwarg1=val1)
    """
    task_id = str(uuid.uuid4())[:8]
    task_name = name or func.__name__

    with _lock:
        _tasks[task_id] = {
            "status": "running",
            "name": task_name,
            "stdout": "",
            "stderr": "",
            "result": None,
            "returncode": None,
            "created_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_task,
        args=(task_id, func, args, kwargs),
        daemon=True,
    )
    thread.start()
    return task_id


def _run_task(task_id: str, func: Callable, args: tuple, kwargs: dict):
    """Execute a task function and update its status."""
    try:
        result = func(*args, **kwargs)
        returncode = 0
        stderr = ""
        if isinstance(result, tuple) and len(result) == 3:
            stdout, stderr, returncode = result
        else:
            stdout = str(result) if result is not None else ""

        with _lock:
            _tasks[task_id].update({
                "status": "completed" if returncode == 0 else "failed",
                "stdout": stdout,
                "stderr": stderr,
                "result": result,
                "returncode": returncode,
            })
    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        logger.exception(f"Task {task_id} failed: {e}")
        with _lock:
            _tasks[task_id].update({
                "status": "failed",
                "stderr": error_msg,
                "returncode": -1,
            })


def status(task_id: str) -> Dict[str, Any]:
    """Get task status. Returns empty dict if task_id not found."""
    with _lock:
        task = _tasks.get(task_id)
        if task is None:
            return {}
        elapsed = time.time() - task.get("created_at", time.time())
        return {**task, "elapsed": round(elapsed, 1)}


def list_tasks(max_items: int = 50) -> list:
    """List recent tasks, newest first."""
    with _lock:
        tasks = list(_tasks.values())
    tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
    return tasks[:max_items]
