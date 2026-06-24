"""
EDM Conversation Status Dashboard

Usage: python -X utf8 edm_dashboard.py [--port 8765] [--json-file edmmailanalyzer.json]

Auto-refresh: pulls latest data from GitHub every 30 minutes.
Page auto-refreshes from /api/data endpoint every 30 minutes.
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

# Shared data store
_convs_json = "[]"
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

    noisy = {"21v-waphynet@oe.21vianet.com"}
    convs = {
        cid: emails for cid, emails in convs.items()
        if not any(e["sender"].lower() in noisy for e in emails)
    }

    result = []
    for cid, emails in convs.items():
        emails.sort(key=lambda x: x.get("conversation_step", 0))
        subject = emails[0]["subject"]
        sn = re.search(r"SN-(\d+)", subject)
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

        result.append({
            "conversation_id": cid,
            "sn": sn.group(0) if sn else "",
            "incident": inc.group(1) if inc else "",
            "subject": subject,
            "total_steps": len(ordered),
            "current_step": len(ordered),
            "emails": ordered,
        })

    result.sort(key=lambda x: x["emails"][0]["date"])
    return result


def fetch_from_github(github_url, proxy_url=None):
    """Fetch data from GitHub via git clone, fall back to HTTP. Returns list or None."""
    import os
    repo_ssh = "git@github.com:bluemct/docs.git"
    repo_https = "https://github.com/bluemct/docs.git"
    tmp_dir = None
    # Try SSH first (no credential prompt), then HTTPS
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
                break  # clone succeeded
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

    # HTTP fallback
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
                print(f"  [refresh] GitHub failed ({e})")
            else:
                print(f"  [fetch] HTTP direct failed, trying proxy...")
    return None


def do_refresh(json_file, github_url, proxy_url=None):
    """Refresh data from GitHub, fall back to local file. Returns dict with details."""
    result = {"ok": True, "githubOk": False, "saved": False, "count": 0, "source": "", "conversations": 0}

    raw = fetch_from_github(github_url, proxy_url)
    if raw is not None:
        result["githubOk"] = True
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
    result["source"] = "GitHub" if result["githubOk"] else "local"
    convs = build_conversations(raw)
    result["conversations"] = len(convs)
    with _data_lock:
        global _convs_json
        _convs_json = json.dumps(convs, ensure_ascii=False)
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
    html_page = None
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
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.html_page.encode("utf-8"))
        elif self.path == "/api/data":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            with _data_lock:
                data = _convs_json
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
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


# HTML template stored separately to avoid encoding issues
def build_html(step_labels_js):
    html = RAW_HTML.replace("__STEP_LABELS__", step_labels_js)
    return html


RAW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDM Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;padding:24px}
h1{text-align:center;margin-bottom:6px;color:#1a1a2e}
.subtitle{text-align:center;color:#666;margin-bottom:24px;font-size:13px}
.refresh-info{text-align:center;font-size:12px;color:#aaa;margin-top:-20px;margin-bottom:20px}
.summary{display:flex;justify-content:center;gap:32px;margin-bottom:24px}
.summary .card{background:#fff;padding:16px 32px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.1);text-align:center;cursor:pointer;transition:box-shadow .2s}
.summary .card:hover{box-shadow:0 2px 8px rgba(0,0,0,.18)}
.summary .card.active{box-shadow:0 0 0 2px #1890ff}
.summary .card .num{font-size:28px;font-weight:bold}
.summary .card .label{font-size:13px;color:#888;margin-top:4px}
.conv-card{background:#fff;border-radius:8px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.1);overflow:hidden}
.conv-header{padding:16px 20px;cursor:pointer;display:flex;align-items:center;gap:16px;user-select:none}
.conv-header:hover{background:#f5f7fa}
.conv-header .toggle{font-size:12px;color:#999;transition:transform .2s;min-width:16px}
.conv-header .toggle.open{transform:rotate(90deg)}
.conv-header .info{flex:1}
.conv-header .subject{font-size:14px;color:#333;font-weight:500}
.conv-header .meta{font-size:12px;color:#999;margin-top:4px}
.badge{font-size:12px;padding:3px 10px;border-radius:10px;color:#fff;white-space:nowrap;font-weight:500}
.badge.done{background:#52c41a}
.badge.progress{background:#faad14}
.progress-bar{display:flex;padding:0 20px 10px;gap:2px}
.progress-bar .seg{flex:1;height:4px;border-radius:2px;background:#e8e8e8}
.progress-bar .seg.done{background:#52c41a}
.progress-bar .seg.current{background:#faad14}
.conv-detail{display:none;border-top:1px solid #f0f0f0;padding:16px 20px}
.conv-detail.open{display:block}
.step-row{display:flex;align-items:flex-start;gap:12px;padding:10px 0;position:relative}
.step-row:not(:last-child)::after{content:'';position:absolute;left:15px;top:36px;bottom:-10px;width:2px;background:#e8e8e8}
.step-row.done:not(:last-child)::after{background:#52c41a}
.step-dot{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:bold;color:#fff;flex-shrink:0}
.step-dot.done{background:#52c41a}
.step-dot.current{background:#faad14}
.step-dot.pending{background:#d9d9d9;color:#999}
.step-content{flex:1}
.step-label{font-size:14px;font-weight:500;color:#333}
.step-info{font-size:12px;color:#888;margin-top:2px}
.step-info .sender{color:#1890ff}
.num-green{color:#52c41a}
.num-yellow{color:#faad14}
.num-blue{color:#1890ff}
.filter-active{font-size:13px;color:#1890ff;text-align:center;margin-bottom:12px}
</style>
</head>
<body>
<h1>EDM Dashboard</h1>
<p class="subtitle">Data source: bluemct/docs (GitHub)</p>
<p class="refresh-info" id="refresh-info"></p>
<div id="user-display" style="text-align:center;font-size:13px;color:#1890ff;margin-bottom:8px;cursor:pointer;" onclick="doLogout()"></div>
<button id="refresh-btn" onclick="manualRefresh()" style="display:block;margin:0 auto 8px;padding:8px 24px;background:#1890ff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:500;">Refresh</button>
<div id="refresh-status" style="text-align:center;font-size:12px;color:#999;margin-bottom:20px;min-height:18px;"></div>
<div id="login-overlay" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.45);z-index:999;justify-content:center;align-items:center;">
  <div style="background:#fff;padding:32px 40px;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.15);text-align:center;min-width:320px;">
    <h2 style="margin-bottom:20px;color:#1a1a2e;font-size:18px;">Login Required</h2>
    <p style="font-size:13px;color:#888;margin-bottom:16px;">Use bj-oe.21vianet.com domain account</p>
    <input id="login-user" type="text" placeholder="Username" style="width:100%;padding:10px 14px;border:1px solid #d9d9d9;border-radius:6px;font-size:14px;margin-bottom:12px;outline:none;"/>
    <input id="login-pass" type="password" placeholder="Password" style="width:100%;padding:10px 14px;border:1px solid #d9d9d9;border-radius:6px;font-size:14px;margin-bottom:8px;outline:none;"/>
    <div id="login-error" style="color:#ff4d4f;font-size:13px;margin-bottom:12px;min-height:18px;"></div>
    <button id="login-btn" onclick="doLogin()" style="width:100%;padding:10px;background:#1890ff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:500;">Login</button>
  </div>
</div>
<div class="summary" id="summary"></div>
<div id="container"></div>
<script>
var STEP_LABELS = __STEP_LABELS__;
var convData = [];
var filterMode = 'all';
var lastRefresh = 0;
var authToken = null;
var authUser = null;

// Simple XHR helper - no Promise, works in all browsers
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
  setTimeout(function() {
    var el = document.getElementById('login-user');
    if (el) el.focus();
  }, 100);
  document.getElementById('login-error').textContent = '';
  document.getElementById('login-pass').value = '';
}

function hideLogin() {
  document.getElementById('login-overlay').style.display = 'none';
}

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
      authToken = r.json.token; authUser = r.json.user;
      hideLogin();
      document.getElementById('user-display').textContent = 'User: ' + r.json.user + ' (click to logout)';
      fetchAndRender('all');
    },
    function() { errEl.textContent = 'Invalid credentials, please retry'; btn.textContent = 'Login'; btn.disabled = false; }
  );
}

function doLogout() {
  authToken = null; authUser = null;
  document.getElementById('user-display').textContent = '';
  showLogin();
}

document.onkeydown = function(e) {
  if (!e) e = window.event;
  var key = e.key || e.keyCode;
  if ((key === 'Enter' || key === 13) && document.getElementById('login-overlay').style.display === 'flex') doLogin();
};

function fetchAndRender(fMode) {
  var authHeaders = {};
  if (authToken) authHeaders['Authorization'] = 'Bearer ' + authToken;
  xhrGet('/api/data', authHeaders,
    function(r) {
      if (r.status === 401) { showLogin(); return; }
      convData = r.json; lastRefresh = Date.now(); render(fMode);
    },
    function() { showLogin(); }
  );
}

function render(fMode) {
  filterMode = fMode || 'all';
  var totalConvs = convData.length;
  var completed = 0;
  for (var i = 0; i < convData.length; i++) {
    convData[i]._isComplete = convData[i].emails.length >= 7;
    if (convData[i]._isComplete) completed++;
  }
  var inProgress = totalConvs - completed;
  var ts = new Date(lastRefresh);
  document.getElementById('refresh-info').textContent = 'Updated: ' + ts.toLocaleTimeString() + ' | Auto-refresh every 30min';
  var summaryEl = document.getElementById('summary');
  summaryEl.innerHTML = '';
  var cardData = [
    { label: 'Total', num: totalConvs, color: 'num-blue', mode: 'all' },
    { label: 'In Progress', num: inProgress, color: 'num-yellow', mode: 'progress' },
    { label: 'Completed', num: completed, color: 'num-green', mode: 'done' },
  ];
  cardData.forEach(function(cd) {
    var card = document.createElement('div');
    card.className = 'card';
    card.onclick = function() { render(cd.mode); };
    card.innerHTML = '<div class="num ' + cd.color + '">' + cd.num + '</div><div class="label">' + cd.label + '</div>';
    summaryEl.appendChild(card);
  });
  var cards = summaryEl.querySelectorAll('.card');
  for (var ci = 0; ci < cards.length; ci++) {
    cards[ci].classList.toggle('active', (filterMode === cardData[ci].mode));
  }
  var filtered = convData;
  if (filterMode === 'progress') filtered = convData.filter(function(c) { return !c._isComplete; });
  if (filterMode === 'done') filtered = convData.filter(function(c) { return c._isComplete; });
  var container = document.getElementById('container');
  container.innerHTML = '';
  if (filterMode !== 'all') {
    var hint = document.createElement('div');
    hint.className = 'filter-active';
    var label = filterMode === 'progress' ? 'In Progress' : 'Completed';
    hint.innerHTML = 'Filter: <strong>' + label + '</strong> (' + filtered.length + ' conversations) - <span style="cursor:pointer;text-decoration:underline" onclick="render(\'all\')">Show All</span>';
    container.appendChild(hint);
  }
  for (var fi = 0; fi < filtered.length; fi++) {
    var conv = filtered[fi];
    var cardId = 'c' + fi;
    var card = document.createElement('div');
    card.className = 'conv-card';
    var header = document.createElement('div');
    header.className = 'conv-header';
    var dateStr = conv.emails[0].date.substring(0, 10);
    var snTag = conv.sn ? '<strong>' + conv.sn + '</strong> - ' : '';
    var subjShort = conv.subject.substring(0, 90) + (conv.subject.length > 90 ? '...' : '');
    var isComplete = conv._isComplete;
    header.innerHTML = '<span class="toggle" id="t-' + cardId + '">></span>' +
      '<div class="info"><div class="subject">' + snTag + subjShort + '</div>' +
      '<div class="meta">' + dateStr + ' - ' + conv.emails.length + ' emails</div></div>' +
      '<span class="badge ' + (isComplete ? 'done' : 'progress') + '">' +
      (isComplete ? 'Completed' : 'Step ' + conv.emails.length) + '</span>';
    var bar = document.createElement('div');
    bar.className = 'progress-bar';
    for (var s = 1; s <= 7; s++) {
      var seg = document.createElement('div');
      seg.className = 'seg';
      if (isComplete || s < conv.emails.length) seg.classList.add('done');
      else if (s === conv.emails.length) seg.classList.add('current');
      bar.appendChild(seg);
    }
    var detail = document.createElement('div');
    detail.className = 'conv-detail';
    detail.id = 'd-' + cardId;
    for (var s = 1; s <= 7; s++) {
      var email = null;
      for (var e = 0; e < conv.emails.length; e++) {
        if (conv.emails[e].conversation_step === s) { email = conv.emails[e]; break; }
      }
      var row = document.createElement('div');
      var isD = isComplete || s < conv.emails.length;
      var isC = !isComplete && s === conv.emails.length;
      row.className = 'step-row' + (isD ? ' done' : '');
      var dotClass = 'step-dot';
      if (isD) dotClass += ' done';
      else if (isC) dotClass += ' current';
      else dotClass += ' pending';
      var dotText = isD ? 'v' : s;
      var infoHTML = email ? '<span class="sender">' + email.sender.split('@')[0] + '</span> - ' + email.date.substring(0, 16) : '<span style="color:#ccc">Pending</span>';
      row.innerHTML = '<div class="' + dotClass + '">' + dotText + '</div>' +
        '<div class="step-content"><div class="step-label">' + STEP_LABELS[s] + '</div>' +
        '<div class="step-info">' + infoHTML + '</div></div>';
      detail.appendChild(row);
    }
    card.appendChild(header);
    card.appendChild(bar);
    card.appendChild(detail);
    container.appendChild(card);
    header.addEventListener('click', (function(cid) {
      return function() {
        var t = document.getElementById('t-' + cid);
        var d = document.getElementById('d-' + cid);
        if (t) t.classList.toggle('open');
        if (d) d.classList.toggle('open');
      };
    })(cardId));
  }
}

function manualRefresh() {
  var btn = document.getElementById('refresh-btn');
  var status = document.getElementById('refresh-status');
  btn.textContent = 'Refreshing...'; btn.style.background = '#91d5ff'; btn.disabled = true;
  status.style.color = '#1890ff'; status.textContent = 'Fetching from GitHub...';
  var authHeaders = {};
  if (authToken) authHeaders['Authorization'] = 'Bearer ' + authToken;
  xhrGet('/api/refresh', authHeaders,
    function(r) {
      if (r.status === 401) { showLogin(); return; }
      var res = r.json;
      if (res.ok) {
        var msgs = [];
        if (res.githubOk) { msgs.push('GitHub OK (' + res.count + ' records)'); if (res.saved) msgs.push('Saved locally'); }
        else { msgs.push('GitHub failed, using local (' + res.count + ' records)'); status.style.color = '#faad14'; }
        msgs.push(res.conversations + ' conversations loaded');
        status.textContent = msgs.join(', ');
        if (res.githubOk && res.saved) { status.style.color = '#52c41a'; btn.textContent = 'OK'; btn.style.background = '#52c41a'; }
        else { btn.textContent = 'Warning'; btn.style.background = '#faad14'; }
        lastRefresh = Date.now(); fetchAndRender(filterMode);
      } else { status.textContent = 'Refresh failed'; status.style.color = '#ff4d4f'; btn.textContent = 'Error'; btn.style.background = '#ff4d4f'; }
    },
    function() { status.textContent = 'Refresh error'; status.style.color = '#ff4d4f'; btn.textContent = 'Error'; btn.style.background = '#ff4d4f'; }
  );
  setTimeout(function() { btn.textContent = 'Refresh'; btn.style.background = '#1890ff'; btn.disabled = false; status.textContent = ''; }, 4000);
}

showLogin();
setInterval(function() { if (authToken) fetchAndRender(filterMode); }, 1800000);
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
    global _convs_json
    _convs_json = json.dumps(convs, ensure_ascii=False)
    print(f"Loaded {len(convs)} conversations from {args.json_file}")

    # Background thread: refresh from GitHub every 30 minutes
    t = threading.Thread(
        target=refresh_data_loop,
        args=(args.json_file, GITHUB_RAW_URL, GITHUB_PROXY_URL, REFRESH_INTERVAL),
        daemon=True,
    )
    t.start()
    print(f"Background refresh: every {REFRESH_INTERVAL // 60} min from GitHub")

    # Build HTML with step labels injected
    step_labels_js = json.dumps(STEP_LABELS, ensure_ascii=False)
    html = build_html(step_labels_js)

    DashboardHandler.html_page = html
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
