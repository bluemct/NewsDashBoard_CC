"""
EDM Conversation Status Dashboard

Usage: python -X utf8 edm_dashboard.py [--port 8765] [--json-file edmmailanalyzer.json]

Auto-refresh: pulls latest data every 30 minutes.
Auth: Basic Auth validated against bj-oe.21vianet.com domain.
"""
import argparse
import base64
import hashlib
import http.server
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import webbrowser
import win32security

DOMAIN_NAME = "bj-oe.21vianet.com"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/bluemct/docs/master/edmmailanalyzer.json"
GITHUB_PROXY_URL = "https://ghproxy.com/https://raw.githubusercontent.com/bluemct/docs/master/edmmailanalyzer.json"
REFRESH_INTERVAL = 1800  # 30 minutes

STEP_LABELS = {
    1: "EDM Request",
    2: "Test Sent, Awaiting Approval",
    3: "Peer Reviewed, Awaiting Nanbo Approval",
    4: "Approved",
    5: "Result Notified to PS",
    6: "Formal EDM Sent",
    7: "Confirmed, Closed",
}

STEP_EXPLANATIONS = {
    1: "Initial EDM request received and logged",
    2: "Test EDM sent to PS team, awaiting internal approval",
    3: "Peer review completed, awaiting Nanbo's final approval",
    4: "EDM approved by all reviewers",
    5: "Approval result notified to PS team",
    6: "Formal EDM email sent to end customers",
    7: "Customer confirmed receipt, ticket closed",
}

# Shared data store
_convs_json = "[]"
_raw_data = []
_weekly_stats = []
_data_lock = threading.Lock()


def load_data(path):
    for enc in ["utf-8-sig", "utf-8", "gbk"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return []


def build_conversations(raw):
    raw = [r for r in raw if "[EDM test and distribution]" in r.get("subject", "")]
    convs = {}
    for r in raw:
        cid = r["conversation_id"]
        convs.setdefault(cid, []).append(r)

    result = []
    for cid, emails in convs.items():
        emails.sort(key=lambda x: x.get("conversation_step", 0))
        subject = emails[0]["subject"]
        first_date = emails[0].get("date", "")[:10]
        # Skip conversations before 2026-05-26 (early test entries)
        if first_date < "2026-05-26":
            continue
        sn_match = re.search(r"SN\s*-\s*(\d+)", subject)
        inc = re.search(r"Incident\s+(\d+)", subject)

        capped = []
        for e in emails:
            rec = dict(e)
            rec["conversation_step"] = min(e.get("conversation_step", 1), 7)
            capped.append(rec)
        seen = {}
        ordered = []
        for e in capped:
            s = e["conversation_step"]
            if s in seen:
                seen[s] = e
            else:
                seen[s] = e
                ordered.append(e)

        firstSender = emails[0].get("sender", "").split("@")[0] if emails[0].get("sender") else ""

        result.append({
            "conversation_id": cid,
            "sn": f"SN-{sn_match.group(1)}" if sn_match else "",
            "incident": inc.group(1) if inc else "",
            "subject": subject,
            "total_steps": len(ordered),
            "current_step": len(ordered),
            "firstSender": firstSender,
            "emails": ordered,
        })

    result.sort(key=lambda x: x["emails"][0]["date"])
    return result


def compute_weekly_stats(raw):
    """Count all conversations by Step 7 (Confirmed, Closed) date per week. Show all weeks with data."""
    try:
        from datetime import datetime, timedelta

        # Group into conversations and find Step 7 date
        edm_raw = [r for r in raw if "[EDM test and distribution]" in r.get("subject", "")]
        convs = {}
        for r in edm_raw:
            convs.setdefault(r["conversation_id"], []).append(r)

        step7_dates = []
        for cid, emails in convs.items():
            step7 = [e for e in emails if min(e.get("conversation_step", 1), 7) == 7]
            if step7:
                d_str = step7[0].get("date", "")[:10]
                try:
                    d = datetime.strptime(d_str, "%Y-%m-%d")
                except ValueError:
                    continue
                step7_dates.append(d)

        if not step7_dates:
            return []

        # Find only weeks that have data
        min_d = min(step7_dates)
        max_d = max(step7_dates)
        # Start from the Monday of the earliest week
        start = min_d - timedelta(days=min_d.weekday())

        weeks = []
        w = start
        while w <= max_d:
            weeks.append(w.strftime("%Y-%m-%d"))
            w += timedelta(days=7)

        counts = [0] * len(weeks)
        for d in step7_dates:
            for i, ws in enumerate(weeks):
                wd = datetime.strptime(ws, "%Y-%m-%d")
                if d >= wd and d < wd + timedelta(days=7):
                    counts[i] += 1
                    break

        # Only return weeks with data
        result = []
        for i, ws in enumerate(weeks):
            if counts[i] > 0:
                result.append((ws, counts[i]))
        return result
    except Exception:
        return []


def export_csv(data_json):
    """Generate CSV string from conv JSON data."""
    import io
    convs = json.loads(data_json)
    out = io.StringIO()
    out.write("SN,Subject,Date,Status,Step,Sender\r\n")
    for c in convs:
        sn = c.get("sn", "")
        subject = c.get("subject", "").replace('"', '""')
        date = c["emails"][0]["date"][:10] if c["emails"] else ""
        is_complete = c["emails"] and len(c["emails"]) >= 7
        status = "Completed" if is_complete else "In Progress"
        step = len(c["emails"])
        out.write(f'{sn},"{subject}",{date},{status},Step {step}/7,{c.get("firstSender", "")}\r\n')
    return out.getvalue()


def fetch_from_github(github_url, proxy_url=None):
    """Fetch data from GitHub via git clone, fall back to HTTP. Returns list or None."""
    import os
    repo_ssh = "git@github.com:bluemct/docs.git"
    repo_https = "https://github.com/bluemct/docs.git"
    tmp_dir = None
    for repo_url in [repo_ssh, repo_https]:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            tmp_dir = tempfile.mkdtemp()
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GCM_INTERACTIVE"] = "never"
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--filter=blob:none", repo_url, tmp_dir],
                capture_output=True, text=True, timeout=30, env=env
            )
            if result.returncode == 0:
                break
            print(f"  [fetch] git clone ({'ssh' if repo_url == repo_ssh else 'https'}) failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"  [fetch] git clone ({'ssh' if repo_url == repo_ssh else 'https'}) failed: {e}")
        finally:
            if tmp_dir and not os.path.exists(os.path.join(tmp_dir, "edmmailanalyzer.json")):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                tmp_dir = None

    if tmp_dir:
        json_path = pathlib.Path(tmp_dir) / "edmmailanalyzer.json"
        if json_path.exists():
            for enc in ["utf-8-sig", "utf-8", "gbk"]:
                try:
                    raw = json.loads(json_path.read_text(encoding=enc))
                    print(f"  [fetch] git clone OK, {len(raw)} records")
                    return raw
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            print("  [fetch] git clone OK but JSON parse failed")
        else:
            print("  [fetch] git clone OK but edmmailanalyzer.json not found")
    else:
        print("  [fetch] git clone failed (both ssh and https)")

    urls_to_try = [github_url]
    if proxy_url:
        urls_to_try.append(proxy_url)
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8-sig")
                raw = json.loads(text)
            label = "proxy" if proxy_url and url == proxy_url else "direct"
            print(f"  [fetch] {label} HTTP OK, {len(raw)} records")
            return raw
        except Exception as e:
            if url == urls_to_try[-1]:
                print(f"  [refresh] fetch failed ({e})")
            else:
                print(f"  [fetch] HTTP direct failed, trying proxy...")
    return None


def do_refresh(json_file, github_url, proxy_url=None):
    """Refresh data from remote, fall back to local file. Returns dict with details."""
    result = {"ok": True, "remoteOk": False, "saved": False, "count": 0, "source": "", "conversations": 0}

    raw = fetch_from_github(github_url, proxy_url)
    if raw is not None:
        result["remoteOk"] = True
        try:
            p = pathlib.Path(json_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(str(p), "w", encoding="utf-8-sig") as f:
                json.dump(raw, f, ensure_ascii=False)
            result["saved"] = True
            print(f"  [refresh] Saved {len(raw)} records to {json_file}")
        except Exception as e:
            print(f"  [refresh] Failed to save: {e}")
    else:
        raw = load_data(json_file)
        if raw:
            print(f"  [refresh] Local fallback OK, {len(raw)} records")
        else:
            result["ok"] = False
            result["source"] = "none"
            return result

    result["count"] = len(raw)
    result["source"] = "remote" if result["remoteOk"] else "local"
    convs = build_conversations(raw)
    weekly = compute_weekly_stats(raw)
    result["conversations"] = len(convs)
    with _data_lock:
        global _convs_json, _raw_data, _weekly_stats
        _convs_json = json.dumps(convs, ensure_ascii=False)
        _raw_data = raw
        _weekly_stats = weekly
    return result


def refresh_data_loop(json_file, github_url, proxy_url, interval):
    while True:
        time.sleep(interval)
        result = do_refresh(json_file, github_url, proxy_url)
        if result.get("ok"):
            print(f"  [auto-refresh] {result['source']}, {result['count']} records")


# Auth storage: token_hash -> (username, expiry_time)
_auth_tokens = {}


def validate_domain_login(username, password):
    """Validate credentials against bj-oe.21vianet.com domain."""
    try:
        win32security.LogonUser(
            username,
            "BJ-OE",
            password,
            win32security.LOGON32_LOGON_NETWORK,
            win32security.LOGON32_PROVIDER_DEFAULT,
        )
        return True
    except Exception as e:
        print(f"  [auth] Login failed for {username}: {e}")
        return False


def generate_auth_token(username):
    """Generate a 1-hour auth token."""
    token = f"{username}:{int(time.time())}:{hashlib.md5(username.encode()).hexdigest()[:8]}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _data_lock:
        _auth_tokens[token_hash] = (username, time.time() + 3600)
    return token


def check_auth_token(bearer_value):
    """Validate a Bearer token. Returns username or None."""
    token_hash = hashlib.sha256(bearer_value.encode()).hexdigest()
    with _data_lock:
        entry = _auth_tokens.get(token_hash)
    if entry and entry[1] > time.time():
        return entry[0]
    return None


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    home_html = None
    detail_html = None
    json_file = "edmmailanalyzer.json"
    github_url = GITHUB_RAW_URL
    proxy_url = GITHUB_PROXY_URL

    def _check_auth(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return check_auth_token(auth_header[7:])
        return None

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Parse path without query string
        path_only = self.path.split("?")[0]

        if path_only == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.__class__.home_html.encode("utf-8"))
        elif path_only == "/detail":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.__class__.detail_html.encode("utf-8"))
        elif path_only == "/api/data":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            with _data_lock:
                data = _convs_json
                weekly = list(_weekly_stats)
            payload = {"conversations": json.loads(data), "weeklyStats": weekly}
            self._send_json(200, payload)
        elif self.path.startswith("/api/export"):
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            with _data_lock:
                data = _convs_json
            csv_content = export_csv(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="edm_dashboard_export.csv"')
            self.end_headers()
            self.wfile.write(csv_content.encode("utf-8"))
        elif self.path == "/api/refresh":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            result = do_refresh(self.__class__.json_file, self.__class__.github_url, self.__class__.proxy_url)
            self._send_json(200, result)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/auth":
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Basic "):
                self._send_json(401, {"error": "authorization header required"})
                return
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, _, password = decoded.partition(":")
            except Exception:
                self._send_json(401, {"error": "invalid basic auth"})
                return

            if username and password and validate_domain_login(username, password):
                token = generate_auth_token(username)
                print(f"  [auth] User {username} logged in")
                self._send_json(200, {"ok": True, "token": token, "user": username})
            else:
                self._send_json(401, {"error": "invalid credentials"})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ---------------------------------------------------------------------------
# Home page HTML
# ---------------------------------------------------------------------------
RAW_HOME_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDM Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;padding:12px 16px;height:100vh;overflow:hidden;display:flex;flex-direction:column}
h1{text-align:center;margin-bottom:2px;color:#1a1a2e;font-size:18px}
.refresh-bar{text-align:center;margin-bottom:8px}
.refresh-bar span{font-size:11px;color:#aaa}
.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.user-info{font-size:12px;color:#1890ff;cursor:pointer}
.refresh-btn{padding:4px 16px;background:#1890ff;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:500}
.refresh-btn:disabled{background:#91d5ff}
.refresh-status{font-size:11px;color:#999;text-align:center;min-height:14px;margin-bottom:6px}

/* Section 1: Summary Cards */
.summary-section{background:#fff;border-radius:8px;padding:12px 24px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:12px;flex:1;overflow:hidden}
.summary-section h2{font-size:13px;color:#1a1a2e;margin-bottom:8px;font-weight:600}
.summary-cards{display:flex;gap:12px}
.summary-card{flex:1;background:#f8fafc;border-radius:6px;padding:10px 16px;text-align:center;cursor:pointer;transition:all .2s;border:2px solid transparent}
.summary-card:hover{border-color:#1890ff;box-shadow:0 2px 8px rgba(24,144,255,.15)}
.summary-card .num{font-size:28px;font-weight:700}
.summary-card .label{font-size:11px;color:#888;margin-top:2px}
.num-blue{color:#1890ff}
.num-yellow{color:#faad14}
.num-green{color:#52c41a}

/* Section 2: In Progress */
.progress-section{background:#fff;border-radius:8px;padding:12px 24px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:12px;flex:2;display:flex;flex-direction:column;overflow:hidden}
.progress-section h2{font-size:13px;color:#1a1a2e;margin-bottom:8px;font-weight:600}
.progress-row{display:flex;align-items:center;padding:10px 0;border-bottom:1px solid #f0f0f0;gap:12px}
#progress-list{flex:1;overflow-y:auto;margin-top:4px}
.progress-row:last-child{border-bottom:none}
.progress-row .sn{font-weight:600;color:#1890ff;min-width:80px;font-size:14px}
.progress-row .subject{flex:1;font-size:13px;color:#333;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.progress-row .bar-wrap{flex:2;display:flex;align-items:center;gap:6px}
.progress-bar{flex:1;display:flex;gap:2px;height:6px}
.progress-bar .seg{flex:1;border-radius:2px;background:#e8e8e8}
.progress-bar .seg.done{background:#52c41a}
.progress-bar .seg.current{background:#faad14}
.progress-row .pct{font-size:13px;font-weight:600;color:#faad14;min-width:60px;text-align:right}
.no-data{text-align:center;color:#ccc;padding:16px;font-size:12px}

/* Section 3: Bottom two columns */
.bottom-section{display:flex;gap:16px;flex:3;min-height:0}
.step-table-box{flex:1;background:#fff;border-radius:8px;padding:12px 20px;box-shadow:0 1px 4px rgba(0,0,0,.08);display:flex;flex-direction:column}
.chart-box{flex:1;background:#fff;border-radius:8px;padding:12px 20px;box-shadow:0 1px 4px rgba(0,0,0,.08);display:flex;flex-direction:column}
.step-table-box h2,.chart-box h2{font-size:13px;color:#1a1a2e;margin-bottom:8px;font-weight:600}
.step-list-box{flex:1;display:flex;flex-direction:column;overflow:hidden}
.step-row{flex:1;display:flex;align-items:center;padding:4px 0;border-bottom:1px solid #f5f5f5;gap:8px}
.step-row:last-child{border-bottom:none}
.step-row .step-num{font-weight:600;color:#1890ff;font-size:11px;min-width:40px}
.step-row .step-name{color:#333;font-size:12px;min-width:160px}
.step-row .step-desc{color:#888;font-size:11px}
.chart-container{display:flex;align-items:flex-end;justify-content:space-around;flex:1;padding:8px 0}
.chart-bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1;max-width:80px}
.chart-bar{width:36px;background:linear-gradient(180deg,#1890ff,#69c0ff);border-radius:3px 3px 0 0;min-height:2px;transition:height .3s}
.chart-bar-label{font-size:10px;color:#888;margin-top:4px;text-align:center}
.chart-bar-value{font-size:11px;font-weight:600;color:#1890ff;margin-bottom:3px}

/* Login overlay */
.login-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.45);z-index:999;justify-content:center;align-items:center}
.login-box{background:#fff;padding:28px 36px;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.15);text-align:center;min-width:300px}
.login-box h2{margin-bottom:16px;color:#1a1a2e;font-size:16px}
.login-box input{width:100%;padding:8px 12px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;margin-bottom:8px;outline:none}
.login-box button{width:100%;padding:8px;background:#1890ff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500}
.login-error{color:#ff4d4f;font-size:12px;margin-bottom:8px;min-height:14px}
</style>
</head>
<body>
<h1>EDM Dashboard</h1>

<div id="login-overlay" class="login-overlay">
  <div class="login-box">
    <h2>Login Required</h2>
    <p style="font-size:13px;color:#888;margin-bottom:16px">Use bj-oe.21vianet.com domain account</p>
    <input id="login-user" type="text" placeholder="Username"/>
    <input id="login-pass" type="password" placeholder="Password"/>
    <div id="login-error" class="login-error"></div>
    <button id="login-btn" onclick="doLogin()">Login</button>
  </div>
</div>

<div class="top-bar">
  <div id="user-display" class="user-info" onclick="doLogout()"></div>
  <div>
    <span id="refresh-status" class="refresh-status"></span>
    <button id="refresh-btn" class="refresh-btn" onclick="manualRefresh()">Refresh</button>
  </div>
</div>
<div class="refresh-bar"><span id="refresh-info"></span></div>

<!-- Section 1: Summary Cards -->
<div class="summary-section">
  <h2>Overview</h2>
  <div class="summary-cards" id="summary"></div>
</div>

<!-- Section 2: In Progress -->
<div class="progress-section">
  <h2>In Progress</h2>
  <div id="progress-list"></div>
</div>

<!-- Section 3: Step Table + Weekly Chart -->
<div class="bottom-section">
  <div class="step-table-box">
    <h2>Process Steps</h2>
    <div id="step-list" class="step-list-box"></div>
  </div>
  <div class="chart-box">
    <h2>Monthly Closed by Week (Step 7)</h2>
    <div class="chart-container" id="chart"></div>
  </div>
</div>

<script>
var STEP_LABELS = __STEP_LABELS__;
var STEP_EXPLANATIONS = __STEP_EXPLANATIONS__;
var convData = [];
var weeklyStats = [];
var lastRefresh = 0;
var authToken = null;
var authUser = null;

function xhrGet(url, headers, onSuccess, onFail) {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', url, true);
  if (headers) { for (var k in headers) { if (headers.hasOwnProperty(k)) xhr.setRequestHeader(k, headers[k]); } }
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) return;
    var resp = { status: xhr.status };
    if (xhr.responseText) { try { resp.json = JSON.parse(xhr.responseText); } catch(e) { resp.json = {}; } }
    if (xhr.status >= 200 && xhr.status < 300) onSuccess(resp);
    else onFail ? onFail(resp) : onSuccess(resp);
  };
  xhr.send();
}

function xhrPost(url, headers, onSuccess, onFail) {
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  if (headers) { for (var k in headers) { if (headers.hasOwnProperty(k)) xhr.setRequestHeader(k, headers[k]); } }
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) return;
    var resp = { status: xhr.status };
    if (xhr.responseText) { try { resp.json = JSON.parse(xhr.responseText); } catch(e) { resp.json = {}; } }
    if (xhr.status >= 200 && xhr.status < 300) onSuccess(resp);
    else onFail ? onFail(resp) : onSuccess(resp);
  };
  xhr.send();
}

function showLogin() {
  document.getElementById('login-overlay').style.display = 'flex';
  document.getElementById('login-error').textContent = '';
  document.getElementById('login-pass').value = '';
  var btn = document.getElementById('login-btn');
  btn.textContent = 'Login'; btn.disabled = false;
  setTimeout(function(){ var el=document.getElementById('login-user'); if(el) el.focus(); }, 100);
}

function hideLogin() { document.getElementById('login-overlay').style.display = 'none'; }

function doLogin() {
  var user = document.getElementById('login-user').value.trim();
  var pass = document.getElementById('login-pass').value;
  var errEl = document.getElementById('login-error');
  var btn = document.getElementById('login-btn');
  if (!user || !pass) { errEl.textContent = 'Please enter username and password'; return; }
  btn.textContent = 'Verifying...'; btn.disabled = true; errEl.textContent = '';
  var credentials = btoa(user + ':' + pass);
  xhrPost('/api/auth', { 'Authorization': 'Basic ' + credentials },
    function(r) {
      if (r.status === 401) { errEl.textContent = 'Invalid credentials, please retry'; btn.textContent = 'Login'; btn.disabled = false; return; }
      localStorage.setItem('edm_token', r.json.token);
      localStorage.setItem('edm_user', r.json.user);
      authToken = r.json.token; authUser = r.json.user;
      hideLogin();
      document.getElementById('user-display').textContent = 'User: ' + r.json.user + ' (click to logout)';
      fetchAndRender();
    },
    function() { errEl.textContent = 'Invalid credentials, please retry'; btn.textContent = 'Login'; btn.disabled = false; }
  );
}

function doLogout() {
  localStorage.removeItem('edm_token');
  localStorage.removeItem('edm_user');
  authToken = null; authUser = null;
  document.getElementById('user-display').textContent = '';
  document.getElementById('summary').innerHTML = '';
  document.getElementById('progress-list').innerHTML = '';
  document.getElementById('step-list').innerHTML = '';
  document.getElementById('chart').innerHTML = '';
  document.getElementById('refresh-info').textContent = '';
  showLogin();
}

// Restore session from localStorage
if (localStorage.getItem('edm_token')) {
  authToken = localStorage.getItem('edm_token');
  authUser = localStorage.getItem('edm_user');
  document.getElementById('user-display').textContent = 'User: ' + authUser + ' (click to logout)';
  fetchAndRender();
} else {
  showLogin();
}

document.onkeydown = function(e) {
  if (!e) e = window.event;
  var key = e.key || e.keyCode;
  if ((key === 'Enter' || key === 13) && document.getElementById('login-overlay').style.display === 'flex') doLogin();
};

function fetchAndRender() {
  var authHeaders = {};
  if (authToken) authHeaders['Authorization'] = 'Bearer ' + authToken;
  xhrGet('/api/data', authHeaders,
    function(r) {
      if (r.status === 401) { showLogin(); return; }
      convData = r.json.conversations;
      weeklyStats = r.json.weeklyStats || [];
      lastRefresh = Date.now();
      render();
    },
    function() { showLogin(); }
  );
}

function render() {
  var totalConvs = convData.length;
  var completed = 0;
  var inProgressList = [];
  for (var i = 0; i < convData.length; i++) {
    var isComplete = convData[i].emails.length >= 7;
    if (isComplete) completed++;
    else inProgressList.push(convData[i]);
  }
  var inProgress = totalConvs - completed;

  var ts = new Date(lastRefresh);
  document.getElementById('refresh-info').textContent = 'Updated: ' + ts.toLocaleTimeString() + ' | Auto-refresh every 30min';

  // Section 1: Summary cards
  var summaryEl = document.getElementById('summary');
  summaryEl.innerHTML = '';
  var cards = [
    { label: 'Total', num: totalConvs, color: 'num-blue', filter: 'all' },
    { label: 'In Progress', num: inProgress, color: 'num-yellow', filter: 'progress' },
    { label: 'Completed', num: completed, color: 'num-green', filter: 'done' },
  ];
  for (var ci = 0; ci < cards.length; ci++) {
    var cd = cards[ci];
    var div = document.createElement('div');
    div.className = 'summary-card';
    div.onclick = (function(f){ return function(){ window.location.href = '/detail?filter=' + f; }; })(cd.filter);
    div.innerHTML = '<div class="num ' + cd.color + '">' + cd.num + '</div><div class="label">' + cd.label + '</div>';
    summaryEl.appendChild(div);
  }

  // Section 2: In Progress list
  var pList = document.getElementById('progress-list');
  pList.innerHTML = '';
  if (inProgressList.length === 0) {
    pList.innerHTML = '<div class="no-data">No in-progress items</div>';
  } else {
    for (var pi = 0; pi < inProgressList.length; pi++) {
      var conv = inProgressList[pi];
      var row = document.createElement('div');
      row.className = 'progress-row';
      var sn = conv.sn || '-';
      var subj = conv.subject.substring(0, 100);
      var stepCount = conv.emails.length;
      var pctText = 'Step ' + stepCount + '/7';
      var barSegs = '';
      for (var s = 1; s <= 7; s++) {
        var cls = 'seg';
        if (s < stepCount) cls += ' done';
        else if (s === stepCount) cls += ' current';
        barSegs += '<div class="' + cls + '"></div>';
      }
      row.innerHTML = '<span class="sn">' + sn + '</span>' +
        '<span class="subject" title="' + subj + '">' + subj + '</span>' +
        '<div class="bar-wrap"><div class="progress-bar">' + barSegs + '</div></div>' +
        '<span class="pct">' + pctText + '</span>';
      pList.appendChild(row);
    }
  }

  // Section 3A: Step list
  var stepList = document.getElementById('step-list');
  stepList.innerHTML = '';
  for (var s = 1; s <= 7; s++) {
    var div = document.createElement('div');
    div.className = 'step-row';
    div.innerHTML = '<span class="step-num">' + s + '</span>' +
      '<span class="step-name">' + STEP_LABELS[s] + '</span>' +
      '<span class="step-desc">' + STEP_EXPLANATIONS[s] + '</span>';
    stepList.appendChild(div);
  }

  // Section 3B: Weekly chart
  var chartEl = document.getElementById('chart');
  chartEl.innerHTML = '';
  if (weeklyStats.length === 0) {
    chartEl.innerHTML = '<div class="no-data">No data this month</div>';
  } else {
    var maxVal = 0;
    for (var wi = 0; wi < weeklyStats.length; wi++) {
      if (weeklyStats[wi][1] > maxVal) maxVal = weeklyStats[wi][1];
    }
    var chartH = 170;
    for (var wi = 0; wi < weeklyStats.length; wi++) {
      var ws = weeklyStats[wi];
      var wrap = document.createElement('div');
      wrap.className = 'chart-bar-wrap';
      var val = ws[1];
      var barH = maxVal > 0 ? Math.max(2, Math.round((val / maxVal) * chartH)) : 2;
      var dateLabel = ws[0].substring(5);
      var valueDiv = document.createElement('div');
      valueDiv.className = 'chart-bar-value';
      valueDiv.textContent = val;
      var barDiv = document.createElement('div');
      barDiv.className = 'chart-bar';
      barDiv.style.height = barH + 'px';
      var labelDiv = document.createElement('div');
      labelDiv.className = 'chart-bar-label';
      labelDiv.textContent = dateLabel;
      wrap.appendChild(valueDiv);
      wrap.appendChild(barDiv);
      wrap.appendChild(labelDiv);
      chartEl.appendChild(wrap);
    }
  }
}

function manualRefresh() {
  var btn = document.getElementById('refresh-btn');
  var status = document.getElementById('refresh-status');
  btn.textContent = 'Refreshing...'; btn.style.background = '#91d5ff'; btn.disabled = true;
  status.style.color = '#1890ff'; status.textContent = 'Refreshing...';
  var authHeaders = {};
  if (authToken) authHeaders['Authorization'] = 'Bearer ' + authToken;
  xhrGet('/api/refresh', authHeaders,
    function(r) {
      if (r.status === 401) { showLogin(); return; }
      var res = r.json;
      if (res.ok) {
        var msgs = [];
        if (res.remoteOk) { msgs.push('Refreshed (' + res.count + ' records)'); if (res.saved) msgs.push('Saved locally'); }
        else { msgs.push('Using local (' + res.count + ' records)'); status.style.color = '#faad14'; }
        msgs.push(res.conversations + ' conversations loaded');
        status.textContent = msgs.join(', ');
        if (res.remoteOk && res.saved) { status.style.color = '#52c41a'; btn.textContent = 'OK'; btn.style.background = '#52c41a'; }
        else { btn.textContent = 'Warning'; btn.style.background = '#faad14'; }
        lastRefresh = Date.now(); fetchAndRender();
      } else { status.textContent = 'Refresh failed'; status.style.color = '#ff4d4f'; btn.textContent = 'Error'; btn.style.background = '#ff4d4f'; }
    },
    function() { status.textContent = 'Refresh error'; status.style.color = '#ff4d4f'; btn.textContent = 'Error'; btn.style.background = '#ff4d4f'; }
  );
  setTimeout(function() { btn.textContent = 'Refresh'; btn.style.background = '#1890ff'; btn.disabled = false; status.textContent = ''; }, 4000);
}

setInterval(function() { if (authToken) fetchAndRender(); }, 1800000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Detail page HTML
# ---------------------------------------------------------------------------
RAW_DETAIL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDM Detail</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;padding:24px}
h1{font-size:20px;color:#1a1a2e;margin-bottom:16px}
.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.back-link{font-size:13px;color:#1890ff;cursor:pointer;text-decoration:underline}
.export-btn{padding:6px 16px;background:#52c41a;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500}
.filter-info{font-size:13px;color:#1890ff;margin-bottom:12px}
table{width:100%;background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-collapse:collapse}
th{background:#fafafa;text-align:left;padding:12px 16px;font-size:12px;color:#888;font-weight:600;border-bottom:2px solid #f0f0f0}
td{padding:12px 16px;font-size:13px;border-bottom:1px solid #f5f5f5;color:#333}
tr:hover td{background:#f5f7fa}
.badge{font-size:11px;padding:2px 8px;border-radius:8px;color:#fff;font-weight:500}
.badge.done{background:#52c41a}
.badge.progress{background:#faad14}
.sn-link{color:#1890ff;font-weight:600}
.subject-cell{max-width:400px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.login-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.45);z-index:999;justify-content:center;align-items:center}
.login-box{background:#fff;padding:32px 40px;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.15);text-align:center;min-width:320px}
.login-box h2{margin-bottom:20px;color:#1a1a2e;font-size:18px}
.login-box input{width:100%;padding:10px 14px;border:1px solid #d9d9d9;border-radius:6px;font-size:14px;margin-bottom:10px;outline:none}
.login-box button{width:100%;padding:10px;background:#1890ff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:500}
.login-error{color:#ff4d4f;font-size:13px;margin-bottom:10px;min-height:18px}
</style>
</head>
<body>
<div id="login-overlay" class="login-overlay">
  <div class="login-box">
    <h2>Login Required</h2>
    <p style="font-size:13px;color:#888;margin-bottom:16px">Use bj-oe.21vianet.com domain account</p>
    <input id="login-user" type="text" placeholder="Username"/>
    <input id="login-pass" type="password" placeholder="Password"/>
    <div id="login-error" class="login-error"></div>
    <button id="login-btn" onclick="doLogin()">Login</button>
  </div>
</div>

<div class="top-bar">
  <span class="back-link" onclick="window.location.href='/'">&#8592; Back to Dashboard</span>
  <button class="export-btn" onclick="doExport()">Export CSV</button>
</div>

<h1 id="page-title">EDM Detail</h1>
<div id="filter-info" class="filter-info"></div>

<table>
  <thead>
    <tr>
      <th>SN</th>
      <th>Subject</th>
      <th>Date</th>
      <th>Status</th>
      <th>Handler</th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>

<script>
var authToken = null;
var allData = [];

function getQueryParam(name) {
  var params = {};
  var parts = window.location.search.substring(1).split('&');
  for (var i = 0; i < parts.length; i++) {
    var kv = parts[i].split('=');
    if (kv.length === 2) params[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]);
  }
  return params[name];
}

function xhrGet(url, headers, onSuccess, onFail) {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', url, true);
  if (headers) { for (var k in headers) { if (headers.hasOwnProperty(k)) xhr.setRequestHeader(k, headers[k]); } }
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) return;
    var resp = { status: xhr.status };
    if (xhr.responseText) { try { resp.json = JSON.parse(xhr.responseText); } catch(e) { resp.json = {}; } }
    if (xhr.status >= 200 && xhr.status < 300) onSuccess(resp);
    else onFail ? onFail(resp) : onSuccess(resp);
  };
  xhr.send();
}

function xhrPost(url, headers, onSuccess, onFail) {
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  if (headers) { for (var k in headers) { if (headers.hasOwnProperty(k)) xhr.setRequestHeader(k, headers[k]); } }
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) return;
    var resp = { status: xhr.status };
    if (xhr.responseText) { try { resp.json = JSON.parse(xhr.responseText); } catch(e) { resp.json = {}; } }
    if (xhr.status >= 200 && xhr.status < 300) onSuccess(resp);
    else onFail ? onFail(resp) : onSuccess(resp);
  };
  xhr.send();
}

function showLogin() {
  document.getElementById('login-overlay').style.display = 'flex';
  document.getElementById('login-error').textContent = '';
  document.getElementById('login-pass').value = '';
  var btn = document.getElementById('login-btn');
  btn.textContent = 'Login'; btn.disabled = false;
  setTimeout(function(){ var el=document.getElementById('login-user'); if(el) el.focus(); }, 100);
}

function hideLogin() { document.getElementById('login-overlay').style.display = 'none'; }

function doLogin() {
  var user = document.getElementById('login-user').value.trim();
  var pass = document.getElementById('login-pass').value;
  var errEl = document.getElementById('login-error');
  var btn = document.getElementById('login-btn');
  if (!user || !pass) { errEl.textContent = 'Please enter username and password'; return; }
  btn.textContent = 'Verifying...'; btn.disabled = true; errEl.textContent = '';
  var credentials = btoa(user + ':' + pass);
  xhrPost('/api/auth', { 'Authorization': 'Basic ' + credentials },
    function(r) {
      if (r.status === 401) { errEl.textContent = 'Invalid credentials, please retry'; btn.textContent = 'Login'; btn.disabled = false; return; }
      localStorage.setItem('edm_token', r.json.token);
      localStorage.setItem('edm_user', r.json.user);
      authToken = r.json.token; authUser = r.json.user;
      hideLogin();
      fetchData();
    },
    function() { errEl.textContent = 'Invalid credentials, please retry'; btn.textContent = 'Login'; btn.disabled = false; }
  );
}

document.onkeydown = function(e) {
  if (!e) e = window.event;
  var key = e.key || e.keyCode;
  if ((key === 'Enter' || key === 13) && document.getElementById('login-overlay').style.display === 'flex') doLogin();
};

function fetchData() {
  var authHeaders = {};
  if (authToken) authHeaders['Authorization'] = 'Bearer ' + authToken;
  xhrGet('/api/data', authHeaders,
    function(r) {
      if (r.status === 401) { showLogin(); return; }
      allData = r.json.conversations;
      render();
    },
    function() { showLogin(); }
  );
}

function render() {
  var filter = getQueryParam('filter') || 'all';
  var filtered = allData;
  var filterLabel = 'All';
  if (filter === 'progress') {
    filtered = [];
    for (var i = 0; i < allData.length; i++) {
      if (allData[i].emails.length < 7) filtered.push(allData[i]);
    }
    filterLabel = 'In Progress';
  } else if (filter === 'done') {
    filtered = [];
    for (var i = 0; i < allData.length; i++) {
      if (allData[i].emails.length >= 7) filtered.push(allData[i]);
    }
    filterLabel = 'Completed';
  }

  document.getElementById('filter-info').textContent = 'Filter: ' + filterLabel + ' (' + filtered.length + ' items)';

  var tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  for (var i = 0; i < filtered.length; i++) {
    var c = filtered[i];
    var tr = document.createElement('tr');
    var isDone = c.emails.length >= 7;
    var statusBadge = isDone ? '<span class="badge done">Completed</span>' : '<span class="badge progress">Step ' + c.emails.length + '/7</span>';
    var dateStr = c.emails[0].date.substring(0, 10);
    var snText = c.sn ? '<span class="sn-link">' + c.sn + '</span>' : '-';
    var subj = c.subject;
    var handler = c.firstSender || '-';
    tr.innerHTML = '<td>' + snText + '</td>' +
      '<td class="subject-cell" title="' + subj + '">' + subj + '</td>' +
      '<td>' + dateStr + '</td>' +
      '<td>' + statusBadge + '</td>' +
      '<td>' + handler + '</td>';
    tbody.appendChild(tr);
  }
}

function doExport() {
  var filter = getQueryParam('filter') || 'all';
  var filtered = allData;
  if (filter === 'progress') {
    filtered = [];
    for (var i = 0; i < allData.length; i++) {
      if (allData[i].emails.length < 7) filtered.push(allData[i]);
    }
  } else if (filter === 'done') {
    filtered = [];
    for (var i = 0; i < allData.length; i++) {
      if (allData[i].emails.length >= 7) filtered.push(allData[i]);
    }
  }
  var header = 'SN,Subject,Date,Status,Step,Handler\r\n';
  var rows = '';
  for (var i = 0; i < filtered.length; i++) {
    var c = filtered[i];
    var isDone = c.emails.length >= 7;
    var subject = '"' + c.subject.replace(/"/g, '""') + '"';
    var dateStr = c.emails[0].date.substring(0, 10);
    rows += c.sn + ',' + subject + ',' + dateStr + ',' + (isDone ? 'Completed' : 'In Progress') + ',Step ' + c.emails.length + '/7,' + (c.firstSender || '') + '\r\n';
  }
  var blob = new Blob([header + rows], { type: 'text/csv' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'edm_export_' + filter + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// Restore session from localStorage
if (localStorage.getItem('edm_token')) {
  authToken = localStorage.getItem('edm_token');
  authUser = localStorage.getItem('edm_user');
  fetchData();
} else {
  showLogin();
}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="EDM Dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--json-file", default="edmmailanalyzer.json")
    args = parser.parse_args()

    raw = load_data(args.json_file)
    if not raw:
        print("No data found.")
        return

    convs = build_conversations(raw)
    weekly = compute_weekly_stats(raw)

    global _convs_json, _raw_data, _weekly_stats
    _convs_json = json.dumps(convs, ensure_ascii=False)
    _raw_data = raw
    _weekly_stats = weekly
    print(f"Loaded {len(convs)} conversations from {args.json_file}")
    print(f"Weekly stats: {weekly}")

    # Background refresh thread
    t = threading.Thread(
        target=refresh_data_loop,
        args=(args.json_file, GITHUB_RAW_URL, GITHUB_PROXY_URL, REFRESH_INTERVAL),
        daemon=True,
    )
    t.start()
    print(f"Background refresh: every {REFRESH_INTERVAL // 60} min")

    # Build HTML templates
    step_labels_js = json.dumps(STEP_LABELS, ensure_ascii=False)
    step_explanations_js = json.dumps(STEP_EXPLANATIONS, ensure_ascii=False)

    home_html = RAW_HOME_HTML.replace("__STEP_LABELS__", step_labels_js)
    home_html = home_html.replace("__STEP_EXPLANATIONS__", step_explanations_js)

    detail_html = RAW_DETAIL_HTML

    DashboardHandler.home_html = home_html
    DashboardHandler.detail_html = detail_html
    DashboardHandler.json_file = args.json_file
    DashboardHandler.github_url = GITHUB_RAW_URL
    DashboardHandler.proxy_url = GITHUB_PROXY_URL

    server = http.server.HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}")

    try:
        webbrowser.open(f"http://localhost:{args.port}")
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
