"""Debug get_item_body: add print() at each step to find where it fails."""
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
print(f"Testing get_item_body for: {item_id[:40]}...\n")

# ---- Step 1: download_mime_content ----
print("Step 1: download_mime_content()")
mime = client.download_mime_content(item_id)
print(f"  MIME size: {len(mime)} bytes")
if not mime:
    print("  MIME is empty -> returning early")
    sys.exit(0)

# ---- Step 2: parse MIME ----
print("\nStep 2: email.message_from_bytes(mime)")
import email as email_lib
try:
    msg = email_lib.message_from_bytes(mime)
    print(f"  OK, msg type: {type(msg)}")
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    sys.exit(0)

# ---- Step 3: extract subject ----
print("\nStep 3: extract Subject header")
subject = msg["Subject"] or ""
print(f"  Subject: '{subject}' (len={len(subject)})")

# ---- Step 4: walk parts ----
print("\nStep 4: walk parts looking for text/plain")
import re
body_text = ""
for i, part in enumerate(msg.walk()):
    ct = part.get_content_type()
    fn = part.get_filename()
    print(f"  [{i:2d}] content-type={ct!r:30s} filename={fn!r}")

    if ct == "text\\plain" and not fn:
        payload = part.get_payload(decode=True)
        print(f"         -> payload decoded: {len(payload) if payload else 0} bytes")
        if payload:
            decoded = payload.decode("utf-8", errors="ignore")
            print(f"         -> decoded text: {len(decoded)} chars")
            print(f"         -> preview: {decoded[:150]!r}")
            body_text = decoded
            break
    elif ct == "text\\html" and not body_text and not fn:
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
            print(f"         -> HTML fallback: {len(body_text)} chars")
            break

print(f"\nFinal body_text length: {len(body_text)}")
if body_text:
    print(f"Body preview: {body_text[:200]}")
else:
    print("Body is EMPTY - checking if it's a content-type matching issue...")

    # Check if the content-type has slashes vs backslashes
    for i, part in enumerate(msg.walk()):
        ct = part.get_content_type()
        raw_ct = part.get_raw_content_type() if hasattr(part, 'get_raw_content_type') else "(N/A)"
        raw_param = part.get_param("Content-Type") if hasattr(part, 'get_param') else "(N/A)"
        print(f"  [{i:2d}] get_content_type()={ct!r}, raw={raw_param}")
        if "text" in (ct or "").lower():
            print(f"         -> This is a text part! ct={ct!r}")
            payload = part.get_payload(decode=True)
            if payload:
                print(f"         -> payload={len(payload)} bytes")

# ---- Step 5: also check the get_item_body method ----
print("\n\nStep 5: Calling actual client.get_item_body()")
result = client.get_item_body(item_id)
print(f"  result: subject='{result.get('subject','')}', body_len={len(result.get('body',''))}")
