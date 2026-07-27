"""
EWS Streaming Notifications Monitor — Python 实现
等价于 ews_streaming.ps1，使用 EWS Managed API DLL (net40) 直接监听 Inbox + EDM 文件夹。

用法：
    python ews_streaming.py

依赖：
    pip install pythonnet

EWS DLL 路径：
    EWS/lib/40/Microsoft.Exchange.WebServices.dll
"""
import clr
import logging
import os
import sys
import threading
import time
from datetime import datetime
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EWS_DLL = os.path.join(BASE_DIR, "EWS", "lib", "40", "Microsoft.Exchange.WebServices.dll")

if not os.path.isfile(EWS_DLL):
    sys.exit(f"EWS DLL not found: {EWS_DLL}")

clr.AddReference(EWS_DLL)

from Microsoft.Exchange.WebServices.Data import (
    ExchangeService,
    WellKnownFolderName,
    FolderId,
    Folder,
    FolderView,
    EventType,
    StreamingSubscriptionConnection,
    WebCredentials,
    PropertySet,
    EmailMessageSchema,
    EmailMessage,
)
from System import Uri, Array

# ---------------------------------------------------------------------------
# EWS Trace — see the actual HTTP requests
# ---------------------------------------------------------------------------

def trace_callback(sender, event_args):
    """Print EWS request/response headers for debugging."""
    try:
        # event_args.Message is a string with the request info
        msg = str(event_args.Message) if hasattr(event_args, "Message") else ""
        if "url" in msg.lower() or "request" in msg.lower():
            logger.info("[EWS TRACE] %s", msg[:500])
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ews_streaming")

# ---------------------------------------------------------------------------
# HTML -> 纯文本（等价于 PowerShell 的 HTMLFile COM 对象 innerText）
# ---------------------------------------------------------------------------

class HtmlToText(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "tr", "blockquote", "pre", "hr"}

    def __init__(self):
        super().__init__()
        self._result = []
        self._inside_pre = False

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS and self._result:
            self._result.append("\n")
        if tag == "pre":
            self._inside_pre = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self._inside_pre = False

    def handle_data(self, data):
        if self._inside_pre:
            self._result.append(data)
        else:
            collapsed = " ".join(data.split())
            if collapsed:
                self._result.append(collapsed)

    def get_text(self):
        text = "".join(self._result)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip()


def html_to_text(html):
    if not html:
        return ""
    parser = HtmlToText()
    try:
        parser.feed(html)
    except Exception:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    return parser.get_text()

# ---------------------------------------------------------------------------
# 凭据配置
# ---------------------------------------------------------------------------

def load_ews_config():
    config_path = os.path.join(BASE_DIR, ".edm_agent_config.json")
    if os.path.isfile(config_path):
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        ews = cfg.get("ews", {})
        return {
            "url": ews.get("url", "https://mail.21vianet.com/EWS/Exchange.asmx"),
            "domain_user": ews.get("domain_user", "ps-tier2.support"),
            "password": ews.get("password", ""),
            "mailbox": ews.get("mailbox", ""),
        }
    else:
        return {
            "url": "https://mail.21vianet.com/EWS/Exchange.asmx",
            "domain_user": "ps-tier2.support",
            "password": "j1ux1@nM10/09/24",
            "mailbox": "ps-tier2.support@oe.21vianet.com",
        }

# ---------------------------------------------------------------------------
# 核心：EWS Streaming 监控器
# ---------------------------------------------------------------------------

class EWSStreamingMonitor:
    """Monitor Inbox + EDM folders for NewMail via EWS Streaming Notifications."""

    def __init__(self, ews_url, domain_user, password):
        self.ews_url = ews_url
        self.domain_user = domain_user
        self.password = password

        self._service = None
        self._connection = None
        self._running = False
        self._thread = None
        self._edm_folder_id = None

    def connect(self):
        """Create ExchangeService, find EDM folder."""
        logger.info("Connecting to EWS: %s", self.ews_url)

        try:
            self._service = ExchangeService()

            # Parse domain\user format from config
            raw_user = self.domain_user
            if "\\" in raw_user:
                domain, username = raw_user.split("\\", 1)
            else:
                domain = "21vianet.com"
                username = raw_user

            creds = WebCredentials(username, self.password, domain)
            self._service.Credentials = creds
            self._service.PreAuthenticate = True

            # Enable SCP lookup for streaming proxy auto-discovery
            try:
                self._service.EnableScpLookup = True
            except Exception:
                pass

            self._service.Url = Uri(self.ews_url)
            logger.info("Credentials: user=%s domain=%s", username, domain)
        except Exception as e:
            logger.error("Failed to create service: %s", e)
            return False

        # Find EDM folder
        try:
            view = FolderView(100)
            view.PropertySet = PropertySet.FirstClassProperties
            folders = self._service.FindFolders(
                WellKnownFolderName.MsgFolderRoot, view,
            )
            logger.info("Found %d root folder(s)", folders.TotalCount)
            for f in folders.Folders:
                logger.info("  - %s", f.DisplayName)
                if f.DisplayName == "EDM":
                    self._edm_folder_id = f.Id
                    break
            if self._edm_folder_id is None:
                logger.error("EDM folder not found")
                return False
            logger.info("EDM folder ID: %s", self._edm_folder_id)
        except Exception as e:
            logger.error("FindFolders failed: %s", e)
            return False

        return True

    def _on_notification_event(self, sender, event_args):
        """Handler for OnNotificationEvent."""
        try:
            for evt in event_args.Events:
                print("-" * 60)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("%s | Event: %s" % (now, evt.EventType))

                if evt.ItemId is None or not evt.ItemId.UniqueId:
                    logger.warning("Event without ItemId, skipping")
                    continue

                try:
                    prop_set = PropertySet(
                        EmailMessageSchema.Subject,
                        EmailMessageSchema.Body,
                    )
                    email = EmailMessage.Bind(self._service, evt.ItemId, prop_set)

                    html = email.Body.ToString() if email.Body else ""
                    text = html_to_text(html) if html else ""

                    print("Found New Mail!")
                    print("  Item ID : %s" % evt.ItemId.UniqueId)
                    print("  Subject : %s" % email.Subject)
                    print("  Body    : %s" % text[:500])
                except Exception as e:
                    logger.error("Failed to read mail details: %s", e)
        except Exception as e:
            logger.error("Error in notification handler: %s", e)

    def _streaming_loop(self):
        """Background thread: streaming connection with auto-reconnect.

        Creates the subscription ONCE outside the loop.
        On disconnect, only recreates the StreamingSubscriptionConnection,
        not the subscription (avoids "duplicate subscription" errors).
        """
        # Create subscription once — never recreate inside the loop
        inbox_folder_id = FolderId(WellKnownFolderName.Inbox)
        folder_ids = Array[FolderId]([inbox_folder_id, self._edm_folder_id])

        subscription = self._service.SubscribeToStreamingNotifications(
            folder_ids, EventType.NewMail,
        )
        logger.info("Subscription created: %s", subscription.Id)

        while self._running:
            try:
                logger.info("Creating connection and opening...")

                self._connection = StreamingSubscriptionConnection(
                    self._service, 30
                )
                self._connection.AddSubscription(subscription)
                self._connection.OnNotificationEvent += self._on_notification_event

                logger.info("Connection open, waiting for events...")
                self._connection.Open()
                # Open() returned — connection was closed or dropped
                logger.info("Open() returned, reconnecting in 5s...")
                time.sleep(5)

            except Exception as e:
                if self._running:
                    # Print raw error bytes to decode encoding
                    err_str = str(e)
                    logger.warning("Connection error: %s", err_str)
                    # Try to decode as GBK
                    try:
                        err_bytes = err_str.encode("utf-8")
                        err_gbk = err_bytes.decode("gbk", errors="replace")
                        logger.warning("GBK decode: %s", err_gbk[:300])
                    except Exception:
                        pass
                    time.sleep(5)
                else:
                    logger.info("Streaming monitor stopped")
            finally:
                if self._connection is not None:
                    try:
                        if self._connection.IsOpen:
                            self._connection.Close()
                    except Exception:
                        pass
                    self._connection = None

    def start(self):
        """Start streaming notifications in a background thread."""
        if not self._service:
            if not self.connect():
                logger.error("Failed to connect to EWS")
                return False

        logger.info("Starting EWS Streaming Notifications (Inbox + EDM)...")
        self._running = True
        self._thread = threading.Thread(target=self._streaming_loop, daemon=True)
        self._thread.start()
        logger.info("Streaming monitor started")
        return True

    def stop(self):
        """Stop the streaming connection."""
        logger.info("Stopping EWS Streaming Notifications...")
        self._running = False
        if self._connection is not None:
            try:
                self._connection.Close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("Streaming monitor stopped")

    def is_running(self):
        return self._running and self._thread is not None and self._thread.is_alive()


# =============================================================================
# 主入口
# =============================================================================

def main():
    config = load_ews_config()

    monitor = EWSStreamingMonitor(
        ews_url=config["url"],
        domain_user=config["domain_user"],
        password=config["password"],
    )

    if not monitor.connect():
        print("Error: Failed to connect to EWS")
        sys.exit(1)

    if not monitor.start():
        print("Error: Failed to start streaming")
        sys.exit(1)

    print("Streaming subscription started. Press Ctrl+C to stop.")

    try:
        while monitor.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        monitor.stop()


if __name__ == "__main__":
    main()
