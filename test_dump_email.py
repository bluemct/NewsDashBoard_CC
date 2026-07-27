"""Debug: dump the first email's full MIME and parsed body from EDM folder."""
import json
import os
import sys
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

with open(os.path.join(BASE_DIR, ".edm_agent_config.json"), "r", encoding="utf-8") as f:
    config = json.load(f)

ews_config = config["ews"]
from edm_agent import EWSClient

client = EWSClient(
    url=ews_config["url"],
    domain_user=ews_config["domain_user"],
    password=ews_config["password"],
    mailbox=ews_config["mailbox"],
)

folder_id = client.find_folder(ews_config.get("folder_name", "EDM"))
if not folder_id:
    print("FAIL: folder not found")
    sys.exit(1)

from datetime import datetime, timedelta
since = datetime.now() - timedelta(hours=36)
items = client.find_items_since(folder_id, since, max_items=50)

print(f"Found {len(items)} item(s)\n")

for idx, item in enumerate(items):
    item_id = item["item_id"]
    subject = item["subject"]
    sender = item["sender"]
    received = item["received"]

    print(f"=== Email {idx+1} ===")
    print(f"  ItemID:   {item_id[:40]}...")
    print(f"  Subject:  {subject}")
    print(f"  Sender:   {sender}")
    print(f"  Received: {received}")

    # --- Full MIME ---
    mime = client.download_mime_content(item_id)
    if not mime:
        print("  [WARN] No MIME content from EWS\n")
        continue

    print(f"\n  --- Full MIME (first 3000 bytes) ---")
    print(mime[:3000].decode("utf-8", errors="replace"))
    print(f"\n  --- MIME total length: {len(mime)} bytes ---\n")

    # --- Parsed with Python email lib ---
    import email as email_lib
    msg = email_lib.message_from_bytes(mime)

    print(f"  --- Parsed Headers ---")
    print(f"  From:     {msg.get('From', '')}")
    print(f"  To:       {msg.get('To', '')}")
    print(f"  Subject:  {msg.get('Subject', '')}")
    print(f"  MimeType: {msg.get_content_type()}")
    payload_list = msg.get_payload()
    print(f"  Parts:    {len(payload_list) if isinstance(payload_list, list) else 1}")

    # Walk all parts
    print(f"\n  --- MIME Parts ---")
    for i, part in enumerate(msg.walk()):
        ct = part.get_content_type()
        fn = part.get_filename()
        charset = part.get_content_charset()
        size = len(part.as_string())
        print(f"  Part {i}: content_type={ct}, filename={fn}, charset={charset}, size={size}")

        if ct in ("text/plain", "text/html") and not fn:
            payload = part.get_payload(decode=True)
            if payload:
                text = payload.decode(charset or "utf-8", errors="replace")
                print(f"         Body length: {len(text)} chars")
                print(f"         Body preview: {text[:300]}")

        elif ct == "message/rfc822":
            payload = part.get_payload(decode=False)
            if isinstance(payload, list):
                sub = payload[0] if payload else None
            else:
                sub = payload
            if isinstance(sub, email_lib.message.Message):
                print(f"         RFC822 inner subject: {sub.get('Subject', '')}")
                print(f"         RFC822 inner from:    {sub.get('From', '')}")
                print(f"         RFC822 inner parts:   {len(sub.get_payload()) if sub.is_multipart() else 1}")

                # Walk inner parts
                for j, ipart in enumerate(sub.walk()):
                    ict = ipart.get_content_type()
                    ifn = ipart.get_filename()
                    if ict in ("text/plain", "text/html") and not ifn:
                        ipayload = ipart.get_payload(decode=True)
                        if ipayload:
                            icharset = ipart.get_content_charset()
                            itext = ipayload.decode(icharset or "utf-8", errors="replace")
                            print(f"         Inner Part {j}: {ict}, length={len(itext)}")
                            print(f"         Preview: {itext[:500]}")
                    elif ict == "application/octet-stream" and ifn:
                        print(f"         Inner Part {j}: {ict}, filename={ifn}")

    print(f"\n{'='*60}\n")
