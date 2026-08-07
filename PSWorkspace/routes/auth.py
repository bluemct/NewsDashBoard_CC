"""Authentication module - AD domain login via win32security.LogonUser.

Auth flow: BJ-OE domain first, then local Windows SAM as fallback.
"""
import hashlib
import logging
import os
import time
from functools import wraps
from threading import Lock

from flask import Blueprint, request, jsonify, g, redirect, url_for

logger = logging.getLogger(__name__)

DOMAIN_NAME = "BJ-OE"

# Auth storage: token_hash -> (username, expiry_time, password)
_auth_tokens = {}
_auth_lock = Lock()

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def validate_domain_login(username: str, password: str) -> bool:
    """Validate credentials against BJ-OE domain via win32security.LogonUser."""
    try:
        import win32security
        win32security.LogonUser(
            username,
            DOMAIN_NAME,
            password,
            win32security.LOGON32_LOGON_NETWORK,
            win32security.LOGON32_PROVIDER_DEFAULT,
        )
        return True
    except Exception as e:
        logger.info(f"[auth] Domain login failed for {username}: {e}")
        return False


def validate_local_login(username: str, password: str) -> bool:
    """Validate credentials against local Windows SAM."""
    try:
        import win32security
        local_domain = os.environ.get("COMPUTERNAME", ".")
        win32security.LogonUser(
            username,
            local_domain,
            password,
            win32security.LOGON32_LOGON_NETWORK,
            win32security.LOGON32_PROVIDER_DEFAULT,
        )
        return True
    except Exception as e:
        logger.info(f"[auth] Local login failed for {username}: {e}")
        return False


def validate_login(username: str, password: str) -> bool:
    """Try domain first, then fall back to local SAM."""
    if validate_domain_login(username, password):
        return True
    if validate_local_login(username, password):
        return True
    return False


def generate_auth_token(username: str, password: str = None) -> str:
    """Generate a 1-hour auth token."""
    token = f"{username}:{int(time.time())}:{hashlib.md5(username.encode()).hexdigest()[:8]}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _auth_lock:
        _auth_tokens[token_hash] = (username, time.time() + 3600, password)
    return token


def check_auth_token(bearer_value: str):
    """Validate a Bearer token. Returns (username, password) or None."""
    token_hash = hashlib.sha256(bearer_value.encode()).hexdigest()
    with _auth_lock:
        entry = _auth_tokens.get(token_hash)
    if entry and entry[1] > time.time():
        return (entry[0], entry[2])
    return None


def _get_user_from_token():
    """Extract username and password from Authorization: Bearer header.
    Returns (username, password) or None."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return check_auth_token(auth_header[7:])
    return None


def require_auth(f):
    """Decorator to require authentication on a route.
    Validates Bearer token from Authorization header.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user_data = _get_user_from_token()
        if not user_data:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized", "message": "Login required"}), 401
            return redirect(url_for('login_page'))
        username, password = user_data
        g.current_user = {'username': username, 'domain': DOMAIN_NAME, 'password': password}
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Get current user from Bearer token in request, or None."""
    user_data = _get_user_from_token()
    if user_data:
        username, password = user_data
        return {'username': username, 'domain': DOMAIN_NAME, 'password': password}
    return None


@auth_bp.route('/login', methods=['POST'])
def login():
    """POST /api/auth/login - Authenticate user against BJ-OE domain.

    Body: {"username": "...", "password": "..."}
    Returns Bearer token on success.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Bad Request", "message": "JSON body required"}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({"error": "Bad Request", "message": "username and password required"}), 400

    if validate_login(username, password):
        token = generate_auth_token(username, password)
        logger.info(f"[auth] User {username} logged in")
        return jsonify({
            "ok": True,
            "token": token,
            "user": username,
        })
    else:
        return jsonify({"error": "Invalid credentials", "message": "账号或密码错误"}), 401


@auth_bp.route('/verify', methods=['GET'])
@require_auth
def verify():
    """GET /api/auth/verify - Verify current token is valid."""
    return jsonify({
        "ok": True,
        "user": {
            "username": g.current_user['username'],
            "domain": g.current_user['domain'],
        }
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """POST /api/auth/logout - Client-side logout (clear localStorage)."""
    return jsonify({"ok": True, "message": "Logged out"})
