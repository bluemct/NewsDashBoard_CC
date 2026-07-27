"""Test: call get_item_body with entry_id to see if get_entry_id is the culprit."""
import json, os, sys, warnings, traceback
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
items = client.find_items_since(folder_id, datetime.now() - timedelta(hours=36), max_items=1)
item_id = items[0]["item_id"]

print("Test 1: get_entry_id()")
try:
    entry_id = client.get_entry_id(item_id)
    print(f"  OK: entry_id = '{entry_id}'")
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()

print("\nTest 2: download_mime_content()")
mime = client.download_mime_content(item_id)
print(f"  MIME size: {len(mime)} bytes")

print("\nTest 3: parse MIME + extract body")
import email as email_lib
import re
msg = email_lib.message_from_bytes(mime)
subject = msg["Subject"] or ""
body_text = ""

for part in msg.walk():
    ct = part.get_content_type()
    if ct == "text/plain" and not part.get_filename():
        payload = part.get_payload(decode=True)
        if payload:
            body_text = payload.decode("utf-8", errors="ignore")
            break
    elif ct == "text/html" and not body_text and not part.get_filename():
        payload = part.get_payload(decode=True)
        if payload:
            html = payload.decode("utf-8", errors="ignore")
            plain = re.sub(r"<[^>]+>", " ", html)
            plain = re.sub(r"&nbsp;", " ", plain)
            plain = re.sub(r"&lt;", "<", plain)
            plain = re.sub(r"&gt;", ">", plain)
            plain = re.sub(r"&amp;", "&", plain)
            plain = re.sub(r"\s+", " ", plain).strip()
            body_text = plain
            break

print(f"  Subject: '{subject}'")
print(f"  Body length: {len(body_text)}")
print(f"  Body preview: {body_text[:200]}...")

print("\nTest 4: Now try the full get_item_body() with traceback")
# Monkey-patch the except to print the traceback
orig = client.get_item_body
import edm_agent
old_exc = edm_agent.EWSClient.get_item_body

def debug_get_item_body(self, item_id, change_key=""):
    mime = self.download_mime_content(item_id)
    if not mime:
        return {"body": "", "subject": "", "body_type": "Text", "entry_id": ""}
    try:
        import email as email_lib
        import re
        msg = email_lib.message_from_bytes(mime)
        subject = msg["Subject"] or ""
        body_text = ""
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="ignore")
                    break
            elif ct == "text/html" and not body_text and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="ignore")
                    plain = re.sub(r"<[^>]+>", " ", html)
                    plain = re.sub(r"&nbsp;", " ", plain)
                    plain = re.sub(r"&lt;", "<", plain)
                    plain = re.sub(r"&gt;", ">", plain)
                    plain = re.sub(r"&amp;", "&", plain)
                    plain = re.sub(r"\s+", " ", plain).strip()
                    body_text = plain
                    break
        print("  MIME parse OK, now calling get_entry_id...")
        entry_id = self.get_entry_id(item_id) or ""
        print(f"  get_entry_id returned: '{entry_id}'")
        return {"body": body_text, "subject": subject, "body_type": "Text", "entry_id": entry_id}
    except Exception as e:
        print(f"  EXCEPTION in get_item_body: {e}")
        traceback.print_exc()
        return {"body": "", "subject": "", "body_type": "Text", "entry_id": ""}

result = debug_get_item_body(client, item_id)
print(f"\nResult: subject='{result.get('subject','')}', body_len={len(result.get('body',''))}")
