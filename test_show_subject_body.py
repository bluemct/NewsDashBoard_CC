"""Show the full subject and body of the matched email."""
import json, os, sys, warnings
warnings.filterwarnings("ignore", category=UserWarning)
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_config.json")
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)
ews_config = config["ews"]

from edm_agent import EWSClient
from datetime import datetime, timedelta

client = EWSClient(
    url=ews_config["url"],
    domain_user=ews_config["domain_user"],
    password=ews_config["password"],
    mailbox=ews_config["mailbox"],
)
folder_id = client.find_folder(ews_config.get("folder_name", "EDM"))
items = client.find_items_since(folder_id, datetime.now() - timedelta(hours=36), max_items=50)

for item in items:
    item_id = item.get("item_id", "")
    sender = item.get("sender", "")
    find_subject = item.get("subject", "")
    received = item.get("received", "")

    body_info = client.get_item_body(item_id)
    mime_subject = body_info.get("subject", "")
    body_text = body_info.get("body", "")

    print("=" * 70)
    print(f"From (FindItem):  {sender}")
    print(f"Received:         {received}")
    print()
    print("─" * 70)
    print("Subject (from FindItem):")
    print("─" * 70)
    print(find_subject)
    print()
    print("─" * 70)
    print("Subject (from MIME):")
    print("─" * 70)
    print(mime_subject)
    print()
    print("─" * 70)
    print("Body (plain text, {} chars):".format(len(body_text)))
    print("─" * 70)
    print(body_text)
    print("=" * 70)
    print()
