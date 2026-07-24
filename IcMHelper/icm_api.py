"""
IcmClient - 统一 ICM API 封装
自动 Token 刷新，聚合读取 / 创建 / 更新操作
"""
import json
import base64
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://prod.microsofticm.com"
TOKEN_URL = "https://portal.microsofticm.com/sso2/token"
CONFIG_PATH = Path(__file__).parent / "icm_config.json"

DEFAULT_HEADERS = {
    "origin": "https://portal.microsofticm.com",
    "referer": "https://portal.microsofticm.com/imp/v3/",
    "content-type": "application/json;charset=UTF-8",
}


def _load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)


def _get_token_expiry(token):
    parts = token.split(".")
    payload = base64.urlsafe_b64decode(parts[1] + "=" * (4 - len(parts[1]) % 4))
    data = json.loads(payload)
    return datetime.fromtimestamp(data["exp"], tz=timezone.utc)


def _refresh_token():
    config = _load_config()
    cookie_string = config.get("cookie_string", "")
    auth_cookie = None
    for part in cookie_string.split(";"):
        part = part.strip()
        if part.startswith("CloudESAuthCookie="):
            auth_cookie = part.split("=", 1)[1]
            break
    if not auth_cookie:
        raise RuntimeError("CloudESAuthCookie not found in config")

    cookies = {"CloudESAuthCookie": auth_cookie}
    resp = requests.post(TOKEN_URL, data="grant_type=cookie", headers=DEFAULT_HEADERS, cookies=cookies, timeout=30)
    resp.raise_for_status()

    new_token = resp.json()["access_token"]

    # Try to get updated cookie from response
    new_cookie = resp.cookies.get("CloudESAuthCookie")
    if new_cookie:
        config["cookie_string"] = f"CloudESAuthCookie={new_cookie}"

    config["access_token"] = new_token
    _save_config(config)
    return new_token


class IcmClient:
    """ICM API 客户端，自动管理 Token 刷新"""

    def __init__(self, config_path=None):
        self._config_path = config_path or CONFIG_PATH
        self._config = None
        self._token = None

    def _ensure_token(self):
        if self._token is None:
            self._config = _load_config()
            self._token = self._config["access_token"]

        # Auto-refresh if token expires within 15 min
        exp = _get_token_expiry(self._token)
        remaining = (exp - datetime.now(timezone.utc)).total_seconds()
        if remaining < 900:
            self._token = _refresh_token()

    def _headers(self):
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

    # ---------- Read ----------

    def get_incidents(self, filter_str=None, top=10):
        params = {"top": top}
        if filter_str:
            params["$filter"] = filter_str
        resp = requests.get(f"{BASE_URL}/api2/incidentapi/incidents", headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", []) if isinstance(data, dict) else data

    def get_incident(self, incident_id):
        incidents = self.get_incidents(filter_str=f"Id eq {incident_id}", top=1)
        return incidents[0] if incidents else None

    # ---------- Write ----------

    def create_incident(self, incident_obj):
        """Create incident from a CreateIncident object"""
        resp = requests.post(
            f"{BASE_URL}/api2/incidentapi/incidents",
            json=incident_obj.to_dict(),
            headers=self._headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def ack_incident(self, incident_id, acknowledged=True):
        url = f"{BASE_URL}/api2/incidentapi/incidents/{incident_id}/ack"
        resp = requests.post(url, json={"IsAcknowledged": acknowledged}, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.status_code == 200

    def add_discussion(self, incident_id, description):
        url = f"{BASE_URL}/api2/incidentapi/incidents/{incident_id}/discussion"
        resp = requests.post(url, json={"Description": description}, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.status_code == 200

    def mitigate_and_resolve(self, incident_id, message=""):
        url = f"{BASE_URL}/api2/incidentapi/incidents/{incident_id}/mitigate"
        resp = requests.post(url, json={"Message": message}, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.status_code == 200

    # ---------- Token ----------

    def refresh_token(self):
        return _refresh_token()

    def verify_token(self):
        resp = requests.get(f"{BASE_URL}/api2/incidentapi/incidents?top=1", headers=self._headers(), timeout=30)
        return resp.status_code == 200
