"""
ICM Token 自动刷新 — 用 cookie 换取新的 access_token
每次刷新记录完整日志到 refresh_log.jsonl
"""
import json
import requests
import sys
import os
from datetime import datetime, timezone, timedelta

API_URL = "https://prod.microsofticm.com/api2/incidentapi/incidents"
TOKEN_URL = "https://portal.microsofticm.com/sso2/token"

CONFIG_PATH = "icm_config.json"
LOG_PATH = "refresh_log.jsonl"

# 北京时间偏移
BEIJING = timezone(timedelta(hours=8))


def log_entry(entry):
    """追加一条日志到 refresh_log.jsonl"""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def refresh_token():
    """从 cookie 换取新的 access_token，写入 icm_config.json"""
    log = {"action": "refresh"}
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    now_bj = datetime.now(BEIJING).strftime("%H:%M:%S CST")
    print(f"[{now}] [{now_bj}] 开始刷新 Token...")

    # --- Step 1: 读取 config ---
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        msg = f"[FAIL] 读取配置失败: {e}"
        print(msg)
        log["status"] = "fail"
        log["error"] = msg
        log_entry(log)
        return

    log["config_has_access_token"] = "access_token" in config
    log["config_has_cookie_string"] = "cookie_string" in config

    # --- Step 2: 提取 CloudESAuthCookie ---
    cookie_string = config.get("cookie_string", "")
    auth_cookie = None
    for part in cookie_string.split(";"):
        part = part.strip()
        if part.startswith("CloudESAuthCookie="):
            auth_cookie = part.split("=", 1)[1]
            break

    if not auth_cookie:
        msg = "[FAIL] 未找到 CloudESAuthCookie"
        print(msg)
        log["status"] = "fail"
        log["error"] = msg
        log_entry(log)
        return

    log["old_cookie_prefix"] = auth_cookie[:40]
    log["old_cookie_length"] = len(auth_cookie)
    print(f"[{now}] [{now_bj}] Cookie: {auth_cookie[:40]}... (len={len(auth_cookie)})")

    # --- Step 3: 发送换 Token 请求 ---
    headers = {
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://portal.microsofticm.com",
        "referer": "https://portal.microsofticm.com/imp/v3/",
    }

    log["request_url"] = TOKEN_URL
    log["request_body"] = "grant_type=cookie"
    log["request_headers"] = {k: v for k, v in headers.items()}
    log["request_cookie_prefix"] = auth_cookie[:40]

    try:
        resp = requests.post(
            TOKEN_URL,
            data="grant_type=cookie",
            headers=headers,
            cookies={"CloudESAuthCookie": auth_cookie},
            timeout=30,
        )
    except Exception as e:
        msg = f"[FAIL] 请求异常: {e}"
        print(msg)
        log["status"] = "fail"
        log["error"] = msg
        log_entry(log)
        return

    # --- Step 4: 记录响应 ---
    log["response_status"] = resp.status_code
    log["response_headers"] = {k: v for k, v in resp.headers.items()}
    log["response_length"] = len(resp.text)

    # 提取 Set-Cookie
    set_cookie_header = resp.headers.get("Set-Cookie", "")
    new_cookie_from_header = None
    if set_cookie_header:
        for segment in set_cookie_header.split(";"):
            segment = segment.strip()
            if segment.startswith("CloudESAuthCookie="):
                new_cookie_from_header = segment.split("=", 1)[1]
                break

    log["set_cookie_present"] = bool(set_cookie_header)
    log["new_cookie_from_header_prefix"] = new_cookie_from_header[:40] if new_cookie_from_header else None
    log["new_cookie_from_header_length"] = len(new_cookie_from_header) if new_cookie_from_header else None

    # 检查 requests 解析的 cookies
    new_cookie_requests = resp.cookies.get("CloudESAuthCookie")
    log["new_cookie_requests_prefix"] = new_cookie_requests[:40] if new_cookie_requests else None
    log["new_cookie_requests_match_header"] = (
        new_cookie_requests == new_cookie_from_header
        if (new_cookie_requests and new_cookie_from_header) else None
    )

    # --- Step 5: 检查结果 ---
    if resp.status_code != 200:
        msg = f"[FAIL] 请求失败: {resp.status_code}"
        print(msg)
        log["status"] = "fail"
        log["response_body_preview"] = resp.text[:500]
        log_entry(log)
        return

    try:
        resp_json = resp.json()
    except Exception:
        msg = "[FAIL] 响应不是 JSON"
        print(msg)
        log["status"] = "fail"
        log["response_body_preview"] = resp.text[:500]
        log_entry(log)
        return

    new_token = resp_json.get("access_token")
    if not new_token:
        msg = "[FAIL] 返回中未找到 access_token"
        print(msg)
        log["status"] = "fail"
        log["response_keys"] = list(resp_json.keys())
        log_entry(log)
        return

    # --- Step 6: 更新 config ---
    cookie_exp_dt = None
    if new_cookie_requests:
        config["access_token"] = new_token
        config["cookie_string"] = f"CloudESAuthCookie={new_cookie_requests}"
        log["cookie_updated"] = True
        log["new_cookie_length"] = len(new_cookie_requests)
        log["cookie_changed"] = (new_cookie_requests != auth_cookie)
    elif new_cookie_from_header:
        config["access_token"] = new_token
        config["cookie_string"] = f"CloudESAuthCookie={new_cookie_from_header}"
        log["cookie_updated"] = True
        log["cookie_source"] = "from_header"
        log["new_cookie_length"] = len(new_cookie_from_header)
        log["cookie_changed"] = (new_cookie_from_header != auth_cookie)
    else:
        config["access_token"] = new_token
        log["cookie_updated"] = False
        log["warning"] = "无新 Cookie 返回，Cookie 未更新"

    # 从 Set-Cookie 提取 Cookie 过期时间，写入 config
    if set_cookie_header:
        for part in set_cookie_header.split(";"):
            part = part.strip()
            if part.startswith("expires="):
                exp_raw = part[8:]
                cookie_exp_dt = datetime.strptime(exp_raw, "%a, %d-%b-%Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
                config["cookie_expires"] = cookie_exp_dt.isoformat()
                break

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)

    # --- Step 7: 解析 Token 有效期 ---
    import base64
    parts = new_token.split(".")
    payload = base64.urlsafe_b64decode(parts[1] + "=" * (4 - len(parts[1]) % 4))
    token_data = json.loads(payload)
    exp = token_data["exp"]
    iat = token_data["iat"]
    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc)
    remaining = (exp_dt - datetime.now(timezone.utc)).total_seconds() / 3600

    log["status"] = "ok"
    log["token_prefix"] = new_token[:40]
    log["token_length"] = len(new_token)
    log["token_iat"] = iat_dt.isoformat()
    log["token_exp"] = exp_dt.isoformat()
    log["token_remaining_hours"] = round(remaining, 2)

    exp_bj = exp_dt.astimezone(BEIJING)
    print(f"[{now}] [OK] Token 刷新成功，有效期 {remaining:.1f} 小时 (至 {exp_dt.strftime('%Y-%m-%d %H:%M')} UTC / {exp_bj.strftime('%Y-%m-%d %H:%M')} CST)")

    if log.get("cookie_updated"):
        cookie_change = "已变化" if log.get("cookie_changed") else "未变化"
        print(f"[{now}] [OK] Cookie 已更新 ({cookie_change}, len={log.get('new_cookie_length', '?')})")

    # 始终显示 Cookie 过期时间
    cookie_exp_info = None
    if cookie_exp_dt:
        cookie_exp_bj = cookie_exp_dt.astimezone(BEIJING)
        cookie_remaining = (cookie_exp_dt - datetime.now(timezone.utc)).total_seconds() / 3600
        cookie_exp_info = f"[{cookie_exp_dt.strftime('%Y-%m-%d %H:%M')} UTC / {cookie_exp_bj.strftime('%Y-%m-%d %H:%M')} CST, 剩余 {cookie_remaining:.1f}h]"
    else:
        # 从 config 读取上次的过期时间
        cookie_expires_str = config.get("cookie_expires")
        if cookie_expires_str:
            ce_dt = datetime.fromisoformat(cookie_expires_str).replace(tzinfo=timezone.utc)
            ce_bj = ce_dt.astimezone(BEIJING)
            cookie_remaining = (ce_dt - datetime.now(timezone.utc)).total_seconds() / 3600
            cookie_exp_info = f"[{ce_dt.strftime('%Y-%m-%d %H:%M')} UTC / {ce_bj.strftime('%Y-%m-%d %H:%M')} CST, 剩余 {cookie_remaining:.1f}h] (上次记录)"

    if cookie_exp_info:
        if log.get("cookie_updated"):
            print(f"[{now}] [OK] Cookie 过期时间: {cookie_exp_info}")
        else:
            print(f"[{now}] [{now_bj}] [WARN] Cookie 未更新，过期时间: {cookie_exp_info}")
    else:
        print(f"[{now}] [{now_bj}] [WARN] Cookie 未更新（无过期时间记录）")

    log_entry(log)


def verify_token():
    """验证 Token 是否有效（调 /api2/incidents 试读）"""
    log = {"action": "verify"}
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    now_bj = datetime.now(BEIJING).strftime("%H:%M:%S CST")

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        token = config["access_token"]
    except Exception as e:
        msg = f"[FAIL] 读取配置失败: {e}"
        print(msg)
        log["status"] = "fail"
        log["error"] = msg
        log_entry(log)
        return

    log["token_prefix"] = token[:40]

    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    }

    try:
        resp = requests.get(API_URL, headers=headers, timeout=30)
    except Exception as e:
        msg = f"[FAIL] 请求异常: {e}"
        print(msg)
        log["status"] = "fail"
        log["error"] = msg
        log_entry(log)
        return

    log["response_status"] = resp.status_code

    if resp.status_code == 200:
        data = resp.json()
        count = len(data.get("value", []))
        msg = f"[OK] Token 有效，当前 {count} 个工单"
        print(f"[{now}] [{now_bj}] {msg}")
        log["status"] = "ok"
        log["incident_count"] = count
    else:
        msg = f"[FAIL] Token 失效 ({resp.status_code})"
        print(f"[{now}] [{now_bj}] {msg}")
        log["status"] = "fail"
        log["response_body_preview"] = resp.text[:500]

    log_entry(log)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "refresh"

    if action == "refresh":
        refresh_token()
    elif action == "verify":
        verify_token()
    elif action == "both":
        refresh_token()
        verify_token()
    else:
        print("Usage: python icm_token_refresh.py [refresh|verify|both]")
