"""Test Playwright login + cookie-based SharePoint download for 21Vianet.

Strategy: navigate directly to the SharePoint URL, let it redirect to the
correct login page (21Vianet login.chinacloudnets.cn), then fill in creds.
"""
import os
import sys
import urllib.parse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: playwright not installed", file=sys.stderr)
    sys.exit(1)

import requests


def convert_sharepoint_url(url):
    """Convert SharePoint preview URL to direct download URL."""
    if "/:x:/r/" in url:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        file_id = query.get("d", [""])[0]
        if file_id:
            path = parsed.path.replace("/:x:/r/", "/:x:/g/")
            url = f"{parsed.scheme}://{parsed.netloc}{path}?e={file_id}"
    return url


def screenshot_safe(page, name):
    """Take a screenshot without failing."""
    try:
        page.screenshot(path=f"debug_{name}.png", full_page=False)
        print(f"   截图: debug_{name}.png")
    except Exception:
        pass


def test_login_and_download(username, password, url):
    converted = convert_sharepoint_url(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go directly to the SharePoint URL - it will redirect to login
        print(f"[1] 访问 SharePoint URL (自动重定向到登录页)...")
        page.goto(url, wait_until="commit", timeout=30000)
        current = page.url
        print(f"   当前 URL: {current[:200]}")
        screenshot_safe(page, "sp_redirect")

        # Now find the login form - could be various Microsoft login pages
        login_input = None
        selectors_to_try = [
            'input[name="loginfmt"]',
            'input[type="email"]',
            'input[name="login"]',
            'input[name="username"]',
            'textarea[name="loginfmt"]',
        ]
        for sel in selectors_to_try:
            try:
                el = page.wait_for_selector(sel, timeout=5000)
                if el.is_visible():
                    login_input = el
                    print(f"   找到输入框: {sel}")
                    break
            except Exception:
                continue

        if login_input is None:
            # Maybe we're already past the email step
            print("   未找到邮箱输入框，检查页面状态...")
            screenshot_safe(page, "no_email_input")
            title = page.title()
            print(f"   页面标题: {title}")
            body = page.inner_text("body")[:500]
            print(f"   页面内容: {body[:300]}")
            return False

        # Enter username/email
        print(f"[2] 输入账号: {username}")
        login_input.fill(username)

        # Wait briefly for page to update, then find the submit button
        page.wait_for_timeout(1000)
        screenshot_safe(page, "after_email")

        # Find submit button - multiple strategies
        submit_btn = None
        btn_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'button[data-test-aid="login-primary-button"]',
            'button:has-text("Next"), button:has-text("下一步"), button:has-text("确定")',
            'input[type="button"]',
        ]
        for sel in btn_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    submit_btn = el
                    print(f"   找到提交按钮: {sel}")
                    break
            except Exception:
                continue

        if submit_btn is None:
            print("   未找到可用的提交按钮", file=sys.stderr)
            screenshot_safe(page, "no_submit_btn")
            browser.close()
            return False

        submit_btn.click()
        print("[3] 点击 Next...")
        page.wait_for_timeout(3000)
        current = page.url
        print(f"   当前 URL: {current[:200]}")
        screenshot_safe(page, "after_next")

        # Now look for password input
        print("[4] 查找密码输入框...")
        pw_input = None
        pw_selectors = [
            'input[type="password"]',
            'input[name="Passwd"]',
            'input[name="Password"]',
        ]
        for sel in pw_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=10000)
                if el.is_visible():
                    pw_input = el
                    print(f"   找到密码框: {sel}")
                    break
            except Exception:
                continue

        if pw_input is None:
            print("   未找到密码输入框", file=sys.stderr)
            screenshot_safe(page, "no_pw_input")
            # Check if maybe we need to select an account first
            title = page.title()
            body = page.inner_text("body")[:500]
            print(f"   页面标题: {title}")
            print(f"   页面内容: {body[:300]}")
            browser.close()
            return False

        pw_input.fill(password)
        page.wait_for_timeout(1000)
        screenshot_safe(page, "after_password")

        # Find sign-in button
        signin_btn = None
        signin_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'button[data-test-aid="login-primary-button"]',
            'button:has-text("Sign in"), button:has-text("登录"), button:has-text("signin")',
        ]
        for sel in signin_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    signin_btn = el
                    print(f"   找到登录按钮: {sel}")
                    break
            except Exception:
                continue

        if signin_btn is None:
            print("   未找到可用的登录按钮", file=sys.stderr)
            screenshot_safe(page, "no_signin_btn")
            browser.close()
            return False

        print("[5] 点击登录...")
        signin_btn.click()
        page.wait_for_timeout(5000)
        current = page.url
        print(f"   登录完成 URL: {current[:200]}")
        screenshot_safe(page, "after_login")

        # Handle "stay signed in" or MFA prompts
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # Check for "stay signed in" dialog
        try:
            skip = page.locator('a:has-text("Not now"), a:has-text("No, thanks"), a[data-test-aid="login-link-dontStay"]')
            if skip.count() > 0:
                print("[6] 跳过 'stay signed in'...")
                skip.first.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        current = page.url
        print(f"   最终 URL: {current[:200]}")
        screenshot_safe(page, "final")

        # Check if still on login
        if "login" in current.lower() and ("microsoft" in current or "cloudnets" in current):
            print("[ERROR] 仍在登录页面，登录可能失败", file=sys.stderr)
            browser.close()
            return False

        # Export cookies
        cookies = page.context.cookies()
        print(f"[7] 获取到 {len(cookies)} 个 cookies")
        for c in cookies[:8]:
            print(f"   {c['name']} (domain={c.get('domain', '')})")

        browser.close()

    # Use requests with cookies
    print(f"[8] 使用 requests + cookies 下载文件...")
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    try:
        resp = session.get(converted, timeout=120, stream=True, allow_redirects=True)
        print(f"   HTTP 状态: {resp.status_code}")
        print(f"   Final URL: {resp.url[:200]}")
        ct = resp.headers.get("Content-Type", "")
        print(f"   Content-Type: {ct}")
        cl = resp.headers.get("Content-Length", "N/A")
        print(f"   Content-Length: {cl}")

        if resp.status_code == 200 and len(resp.content) > 100:
            fname = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(converted).path)) or "download.xlsx"
            dest = os.path.join(os.getcwd(), fname)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            sz = os.path.getsize(dest) / 1024
            print(f"   文件已保存: {fname} ({sz:.1f} KB)")
            return True
        else:
            body_preview = resp.content[:500]
            print(f"   响应体 ({len(resp.content)} bytes): {body_preview}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"   下载失败: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    from cryptography.fernet import Fernet

    cred_dir = os.path.join(os.getcwd(), ".edm_auth")
    key = open(os.path.join(cred_dir, "key"), "rb").read()
    f = Fernet(key)
    username = f.decrypt(open(os.path.join(cred_dir, "credentials")).read()).decode()
    password = f.decrypt(open(os.path.join(cred_dir, "password")).read()).decode()

    print(f"用户: {username}")

    url = "https://microsoftapc.sharepoint.com/:x:/r/teams/AzureServiceNotificationsCollaboration/Shared Documents/2026/2026-06/811869714 - SN-56195/Token1-3 SN-56195.xlsx?d=w869c3cccb3f04c668616eedb1de70217&csf=1&web=1&e=jkt2sK"

    test_login_and_download(username, password, url)
