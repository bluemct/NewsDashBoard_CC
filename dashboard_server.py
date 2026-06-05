"""
新闻简报任务监控面板服务器
启动后在浏览器访问 http://localhost:8899 查看任务状态。
"""

import json
import os
import webbrowser
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_status.json")
DASHBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
NEWS_PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_list.html")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve dashboard and status data."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_html(DASHBOARD_FILE)
            return

        if path == "/news":
            self._serve_html(NEWS_PAGE_FILE)
            return

        if path == "/api/status":
            self._send_json()
            return

        if path == "/api/news":
            self._send_news()
            return

        super().do_GET()

    def _serve_html(self, filepath):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        with open(filepath, "r", encoding="utf-8") as f:
            self.wfile.write(f.read().encode("utf-8"))

    def _send_json(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"task_name": "每日新闻简报", "runs": [], "error": "No data yet"}
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _send_news(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                status = json.load(f)
        except FileNotFoundError:
            self.wfile.write(json.dumps({"ai": [], "auto": [], "top": [], "timestamp": ""}, ensure_ascii=False).encode("utf-8"))
            return

        # Get the latest successful run
        latest = None
        for run in reversed(status.get("runs", [])):
            if run.get("status") == "success":
                latest = run
                break

        if latest:
            self.wfile.write(json.dumps({
                "timestamp": latest.get("timestamp", ""),
                "ai": latest.get("ai_items", []),
                "auto": latest.get("auto_items", []),
                "top": latest.get("top_items", []),
            }, ensure_ascii=False, indent=2).encode("utf-8"))
        else:
            self.wfile.write(json.dumps({"ai": [], "auto": [], "top": [], "timestamp": ""}, ensure_ascii=False).encode("utf-8"))


def main():
    port = 8899
    # Change to the script directory so static files resolve correctly
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
