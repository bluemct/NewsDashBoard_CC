"""
Unimarketing web UI — Capture the contact edit/save API request

Open the web UI, navigate to a contact, edit lists, save, and capture the HTTP request.
"""
import asyncio
import json
import time
from playwright.async_api import async_playwright

UNIMARKETING_URL = "https://www.unimarketing.com.cn"
# Credentials from memory — same account as API
# The web UI likely uses the same credentials but different format

async def main():
    captured_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Route all requests to capture
        async def handle_route(route):
            req = route.request
            method = req.method
            url = req.url
            resource_type = req.resource_type

            # Capture all POST requests
            if method == "POST":
                body = req.post_data
                post_data = req.post_data_buffer if hasattr(req, 'post_data_buffer') else None
                headers = dict(req.headers)

                captured = {
                    "method": method,
                    "url": url,
                    "content_type": headers.get("content-type", ""),
                    "post_data": body[:2000] if body else None,
                    "headers": {k: v for k, v in headers.items() if k in ["content-type", "authorization", "cookie", "x-requested-with"]},
                }
                print(f"\n{'='*80}")
                print(f"CAPTURED {method} {url}")
                print(f"Content-Type: {captured['content_type']}")
                print(f"Body: {captured['post_data'][:1000] if captured['post_data'] else '(binary)'}")
                captured_requests.append(captured)

            await route.continue_()

        await page.route("**/*", handle_route)

        print(f"Opening Unimarketing web UI...")
        print(f"Please log in and then navigate to a contact to edit.")
        print(f"Press Ctrl+C to stop when done.")

        await page.goto(UNIMARKETING_URL)

        # Wait for user interaction
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        # Save captured requests
        with open("web_api_capture.json", "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(captured_requests)} captured requests to web_api_capture.json")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
