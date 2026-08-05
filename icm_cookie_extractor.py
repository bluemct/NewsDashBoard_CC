"""ICM Cookie Browser Extractor — CDP WebSocket mode, no browser driver needed

Usage: python icm_cookie_extractor.py

What it does:
  1. Scans for an existing Edge debug port; if none, starts Edge fresh
  2. Connects via WebSocket CDP to a page target
  3. Navigates to ICM Portal login page
  4. Monitors URL + cookies until CloudESAuthCookie appears
  5. Prints result to console

No Selenium, no browser driver needed — pure Python + urllib + socket.
"""
import os
import sys
import time
import json
import struct
import socket
import subprocess
import tempfile
import urllib.request
import urllib.parse
import base64
from datetime import datetime, timezone
from urllib.parse import urlparse


# ─── WebSocket CDP Client (pure Python, zero deps) ───

class CdpWsClient:
    """Minimal WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url, timeout=10):
        self.sock = None
        self._id = 0
        parsed = urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 19880
        path = parsed.path
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.sock.settimeout(timeout)
        self._handshake(path, host, port)
        self._pending = {}  # id -> (key, data)

    def _handshake(self, path, host, port):
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self.sock.sendall(handshake.encode())
        hdr = b""
        while b"\r\n\r\n" not in hdr:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Handshake failed: no response")
            hdr += chunk
        status = hdr.decode().split("\r\n")[0]
        if "101" not in status:
            raise ConnectionError(f"WebSocket handshake failed: {status}")

    def _send_frame(self, data_bytes):
        frame = bytearray([0x81, 0x80 | len(data_bytes)])
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data_bytes)))
        self.sock.sendall(frame)

    def _recv_frame(self):
        h = b""
        while len(h) < 2:
            c = self.sock.recv(1)
            if not c:
                return None
            h += c
        length = h[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.sock.recv(8))[0]
        masked = h[1] & 0x80
        mask = self.sock.recv(4) if masked else b""
        data = b""
        while len(data) < length:
            data += self.sock.recv(length - len(data))
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return data.decode("utf-8")

    def call(self, method, params=None, timeout=15):
        """Send a CDP command and wait for its response.

        Returns the 'result' dict, or None on error.
        """
        self._id += 1
        msg = {"id": self._id, "method": method}
        if params:
            msg["params"] = params
        self._send_frame(json.dumps(msg).encode("utf-8"))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sock.settimeout(min(1.0, deadline - time.time()))
            try:
                raw = self._recv_frame()
                if raw is None:
                    return None
                obj = json.loads(raw)
                # Check if this is the response we want
                if obj.get("id") == self._id:
                    return obj.get("result")
                # Otherwise it's an event — ignore for now
            except socket.timeout:
                continue
        return None

    def read_events(self, timeout=0.5):
        """Read all pending WebSocket frames (events + responses) without blocking long.

        Returns list of parsed JSON objects.
        """
        events = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sock.settimeout(min(0.1, deadline - time.time()))
            try:
                raw = self._recv_frame()
                if raw is None:
                    break
                obj = json.loads(raw)
                events.append(obj)
            except socket.timeout:
                break
        return events

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


# ─── Helpers ───

def find_or_start_debug_port(port_range=range(19880, 19900), force_fresh=False):
    """Scan for an existing CDP port; if none, pick a free one.

    If force_fresh=True, skip reusing existing Edge — always start a new one.
    Returns (port, started_new) tuple.
    """
    if not force_fresh:
        for port in port_range:
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=2
                )
                if resp.status == 200:
                    print(f"[INFO] Found existing Edge on port {port} (reusing).")
                    return port, False
            except Exception:
                pass

    for port in port_range:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
        except OSError:
            continue
        return port, True
    return None, False


def find_edge_executable():
    """Find Microsoft Edge executable path."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft",
            "Edge",
            "Application",
            "msedge.exe",
        ),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def cdp_get_targets(base_url):
    """Return list of browser targets from /json/list."""
    resp = urllib.request.urlopen(f"{base_url}/json/list", timeout=5)
    return json.loads(resp.read())


def find_page_target(targets):
    """Return the first target with type == 'page', or None."""
    for t in targets:
        if t.get("type") == "page":
            return t
    return None


def find_icm_page_target(targets):
    """Return a page target whose URL contains 'portal.microsofticm.com', or None."""
    for t in targets:
        if t.get("type") == "page" and "portal.microsofticm.com" in t.get("url", ""):
            return t
    return None


# ─── Main Logic ───

def start_edge_with_debug(port, force_fresh=False):
    """Start Edge with remote debugging port, using a temp profile."""
    edge_exe = find_edge_executable()
    if not edge_exe:
        print("[ERROR] Microsoft Edge not found on this system.")
        return False

    temp_profile = os.path.join(tempfile.gettempdir(), f"icm_cookie_edge_{port}")

    # Clean up stale profile if force_fresh — removes lock files that block startup
    if force_fresh and os.path.exists(temp_profile):
        import shutil
        print(f"[INFO] Removing stale temp profile: {temp_profile}")
        try:
            shutil.rmtree(temp_profile)
        except Exception as e:
            print(f"[WARN] Could not remove stale profile: {e}")

    os.makedirs(temp_profile, exist_ok=True)

    print(f"[INFO] Starting Edge on port {port}...")
    print(f"[INFO] Temp profile: {temp_profile}")

    creationflags = 0
    try:
        import sys as _sys
        if _sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    except Exception:
        pass

    try:
        subprocess.Popen(
            [
                edge_exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={temp_profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--disable-background-networking",
            ],
            creationflags=creationflags,
        )
    except Exception as e:
        print(f"[ERROR] Failed to start Edge: {e}")
        return False

    print("[WAIT] Waiting for Edge CDP to respond...")
    for i in range(30):
        time.sleep(1)
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=3
            )
            if resp.status == 200:
                version_info = json.loads(resp.read())
                print(f"[INFO] Edge started (pid={version_info.get('pid', '?')})")
                return True
        except Exception:
            pass
        if i % 10 == 0 and i > 0:
            print(f"[WAIT]   {i + 1}s / 30s...")

    print(f"[ERROR] Edge did not respond on port {port} within 30 seconds.")
    return False


def extract_cookie_from_edge(result_file=None, config_dir=None, force_fresh=False):
    port, started_new = find_or_start_debug_port(force_fresh=force_fresh)
    if port is None:
        print("[ERROR] Could not find a free port.")
        return

    print(f"[INFO] Debug port: {port}")

    # ── Phase 1: Ensure Edge is running ──
    if started_new:
        if not start_edge_with_debug(port, force_fresh=force_fresh):
            return

    base = f"http://127.0.0.1:{port}"
    icm_home_url = "https://portal.microsofticm.com/"
    icm_login_url = icm_home_url  # let ICM redirect to login automatically

    # ── Phase 2: Find or create an ICM page target ──
    print("\n[PHASE] Getting page target on ICM...")

    targets = cdp_get_targets(base)
    page = find_icm_page_target(targets)

    if page is not None:
        print(f"[INFO] Already on ICM page: {page.get('url', '?')[:80]}")
        ws_url = page.get("webSocketDebuggerUrl", "")
    else:
        # Use browser-level WS to createTarget
        try:
            resp = urllib.request.urlopen(f"{base}/json/version", timeout=5)
            ver = json.loads(resp.read())
            browser_ws = ver.get("webSocketDebuggerUrl", "")
        except Exception:
            browser_ws = ""

        if browser_ws:
            try:
                client = CdpWsClient(browser_ws)
                result = client.call("Target.createTarget", {"url": icm_login_url})
                client.close()
                if result and result.get("targetId"):
                    tid = result.get("targetId")
                    print(f"[INFO] Created new tab (targetId={tid[:16]})")
                    time.sleep(2)
                    # Find the new target in /json/list
                    new_targets = cdp_get_targets(base)
                    for t in new_targets:
                        if t.get("id") == tid:
                            page = t
                            ws_url = t.get("webSocketDebuggerUrl", "")
                            break
                    if page is None:
                        print("[WARN] Target created but not found in /json/list")
                        page = find_page_target(new_targets)
                        if page:
                            ws_url = page.get("webSocketDebuggerUrl", "")
                            print(f"[INFO] Fallback to first page: {page.get('url','?')[:60]}")
                else:
                    print(f"[WARN] createTarget returned: {result}")
            except Exception as e:
                print(f"[WARN] createTarget via browser WS failed: {e}")
        else:
            print("[WARN] No browser WS URL available")

        # Final fallback: use existing page
        if page is None:
            page = find_page_target(targets)
            if page is None:
                print("[ERROR] No page targets found at all.")
                return
            ws_url = page.get("webSocketDebuggerUrl", "")
            print(f"[INFO] Using existing tab: {page.get('title', '?')[:40]}")

    if not ws_url:
        print("[ERROR] No WebSocket URL for page interaction.")
        return

    # ── Phase 3: Connect WS + Navigate ──
    print(f"\n[PHASE] Connecting WebSocket CDP...")
    try:
        client = CdpWsClient(ws_url)
        # Enable domains we need
        client.call("Page.enable")
        client.call("Runtime.enable")
        client.call("Network.enable")
        print("[INFO] CDP domains enabled (Page, Runtime, Network).")
    except Exception as e:
        print(f"[ERROR] Failed to connect WebSocket: {e}")
        return

    # Navigate if not already on ICM
    current = client.call("Runtime.evaluate", {"expression": "document.URL"})
    current_url = current.get("value", "") if current else ""
    print(f"[INFO] Current page: {current_url[:80]}")

    if "portal.microsofticm.com" not in current_url or "/sso2/login" in current_url:
        print(f"\n[PHASE] Navigating to ICM Portal...")
        nav_result = client.call(
            "Runtime.evaluate",
            {"expression": f"window.location.href='{icm_home_url}'"},
            timeout=5,
        )
        print("[INFO] Navigation sent, waiting for load...")
        time.sleep(3)

    # ── Phase 4: Monitor cookies ──
    print(f"\n[PHASE] Monitoring for CloudESAuthCookie (timeout 180s)...\n")
    print("[INFO] Please complete AAD SSO + MFA login in the Edge window.\n")

    timeout = 180
    start_time = time.time()
    cookie_found = False
    cookie_value = None
    cookie_expires_str = None
    last_url = ""
    sso_done = False          # True once portal.microsofticm.com cookies appear
    home_navigated = False    # True once we've navigated to homepage

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)

        # Read any pending events (framed navigations, etc.)
        try:
            events = client.read_events(timeout=0.3)
        except Exception:
            events = []

        # Check current URL
        try:
            url_result = client.call("Runtime.evaluate", {
                "expression": "document.URL"
            }, timeout=5)
            if url_result and url_result.get("value"):
                curr = url_result["value"]
                if curr != last_url:
                    last_url = curr
                    tag = "icm" if "portal.microsofticm.com" in curr else "page"
                    print(f"[URL]  [{tag}] {curr[:100]}")
        except Exception:
            pass

        # Check cookies — look for SSO progress + CloudESAuthCookie
        try:
            cookies_result = client.call("Network.getAllCookies", timeout=5)
            if cookies_result:
                cookies = cookies_result.get("cookies", [])

                # Detect SSO completion: portal.microsofticm.com has cookies
                for ck in cookies:
                    if ck.get("name") == "CloudESAuthCookie":
                        cookie_found = True
                        cookie_value = ck.get("value", "")
                        cookie_expires_str = ck.get("expires")
                        break

                # If CloudESAuthCookie not found but SSO cookies exist, user may be
                # authenticated but on the /sso2/ intermediate page.
                # Navigate to homepage to trigger the final Cookie set.
                if not cookie_found and not home_navigated:
                    # Detect SSO completion via URL:
                    # /sso2/?identityProvider=... means SSO callback finished
                    try:
                        url_check = client.call("Runtime.evaluate", {
                            "expression": "document.URL"
                        }, timeout=5)
                        u = url_check.get("value", "") if url_check else ""
                    except Exception:
                        u = ""

                    sso_callback = (
                        "portal.microsofticm.com/sso2/" in u
                        and "/sso2/login" not in u
                        and ("identityProvider" in u or "/sso2/?" in u)
                    )
                    if sso_callback and not sso_done:
                        sso_done = True
                        print("[INFO] SSO authentication completed.")
                        print(f"[INFO] Navigating to ICM homepage ({icm_home_url}) to finalize session...")
                        client.call(
                            "Runtime.evaluate",
                            {"expression": f"window.location.href='{icm_home_url}'"},
                            timeout=5,
                        )
                        home_navigated = True
                        time.sleep(5)  # give homepage time to load and set cookies
        except Exception:
            pass

        if cookie_found:
            break

        if elapsed > 0 and elapsed % 15 == 0:
            print(f"[WAIT] {elapsed}s / {timeout}s — still waiting for login...")

        time.sleep(2)

    client.close()
    print()

    # ── Result ──
    if not cookie_found:
        print(f"[ERROR] Cookie not found within {timeout} seconds.")
        print("Possible reasons:")
        print("  - Login was not completed")
        print("  - ICM Portal session expired")
        print("  - Cookie domain differs from page domain")
        print()

        # Debug: dump last known cookies
        try:
            client2 = CdpWsClient(ws_url)
            cookies_result = client2.call("Network.getAllCookies")
            client2.close()
            if cookies_result:
                cookies = cookies_result.get("cookies", [])
                domains_seen = set()
                print(f"[DEBUG] Found {len(cookies)} cookies (no CloudESAuthCookie):")
                for c in cookies[:20]:
                    name = c.get("name", "")
                    domain = c.get("domain", "")
                    domains_seen.add(domain)
                    val_preview = str(c.get("value", ""))[:40]
                    print(f"  [{domain}] {name} = {val_preview}...")
                print(f"\n[DEBUG] Cookie domains: {', '.join(sorted(domains_seen))}")
        except Exception as e:
            print(f"[DEBUG] Could not read cookies: {e}")

        print("\n[INFO] The Edge window will stay open...")
        print("[INFO] Close it manually when done.")

        # In extract mode, write failure result
        if result_file:
            write_extract_failure(result_file, "Cookie not found within timeout")
            print(f"\n[EXTRACT] Failure written to: {result_file}")
        return

    # ── Parse expiry ──
    expires_dt = None
    expires_iso = ""
    expires_str = "Unknown"

    if cookie_expires_str is not None:
        try:
            exp_ts = float(cookie_expires_str)
            expires_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            expires_iso = expires_dt.isoformat()
            expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, TypeError, OSError):
            expires_str = str(cookie_expires_str)

    remaining_seconds = 0
    remaining_hours = 0
    if expires_dt:
        remaining_seconds = (expires_dt - datetime.now(tz=timezone.utc)).total_seconds()
        remaining_hours = remaining_seconds / 3600

    # ── Print results ──
    print("=" * 60)
    print(f"\nCookie Name: CloudESAuthCookie")
    print(f"Cookie Value (first 50 chars): {cookie_value[:50]}...")
    print(f"Cookie Length: {len(cookie_value)} chars")
    print(f"Expires: {expires_str}")
    if expires_iso:
        print(f"Expires (ISO): {expires_iso}")
    if remaining_hours > 0:
        print(
            f"Remaining: {remaining_hours:.1f} hours ({remaining_seconds / 60:.0f} minutes)"
        )
    else:
        print("WARNING: Cookie is already expired!")
    print("=" * 60)

    print("\nTo update IcMHelper/icm_config.json, set:")
    print(f'  "cookie_string": "CloudESAuthCookie={cookie_value}"')
    if expires_iso:
        print(f'  "cookie_expires": "{expires_iso}"')
    print("=" * 60)

    print("\n[INFO] The Edge window will stay open...")
    print("[INFO] Close it manually when done.")

    # ── In extract mode, write result to JSON file ──
    if result_file:
        write_extract_result(result_file, cookie_value, expires_iso)
        print(f"\n[EXTRACT] Result written to: {result_file}")
    if config_dir:
        import os
        config_path = os.path.join(config_dir, "icm_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["cookie_string"] = f"CloudESAuthCookie={cookie_value}"
            if expires_iso:
                cfg["cookie_expires"] = expires_iso
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            print(f"[EXTRACT] Cookie written to: {config_path}")
        except Exception as e:
            print(f"[WARN] Failed to update {config_path}: {e}")


def write_extract_result(result_path, cookie_value, expires_iso):
    """Write extraction result to a JSON file for caller to pick up."""
    result = {
        "ok": True,
        "cookie_value": cookie_value,
        "cookie_expires": expires_iso if expires_iso else None,
        "cookie_string": f"CloudESAuthCookie={cookie_value}",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


def write_extract_failure(result_path, error_message):
    """Write failure result to JSON file."""
    result = {
        "ok": False,
        "error": error_message,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ICM Cookie Browser Extractor")
    parser.add_argument(
        "--extract",
        metavar="RESULT_JSON",
        help=(
            "Extract mode: run and write result to RESULT_JSON instead of printing. "
            "Used by PS Workspace for automated cookie refresh."
        ),
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help=(
            "IcMHelper directory. If set, the extracted cookie is written "
            "directly to <config-dir>/icm_config.json after extraction."
        ),
    )
    parser.add_argument(
        "--force-fresh",
        action="store_true",
        help="Do not reuse existing Edge — always start a fresh browser instance.",
    )
    args = parser.parse_args()

    print("=" * 60)
    if args.extract:
        print("ICM Cookie Browser Extractor (extract mode)")
        print(f"Result will be written to: {args.extract}")
    else:
        print("ICM Cookie Browser Extractor (CDP WebSocket mode)")
    print("No Selenium / No browser driver needed")
    print("=" * 60)
    print()

    extract_cookie_from_edge(result_file=args.extract, config_dir=args.config_dir, force_fresh=args.force_fresh)
