"""Separately show each MIME layer's body to understand the structure."""
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

from edm_agent import EWSClient
from datetime import datetime, timedelta

client = EWSClient(
    url=config["ews"]["url"],
    domain_user=config["ews"]["domain_user"],
    password=config["ews"]["password"],
    mailbox=config["ews"]["mailbox"],
)
folder_id = client.find_folder(config["ews"].get("folder_name", "EDM"))
items = client.find_items_since(folder_id, datetime.now() - timedelta(hours=36), max_items=1)
item_id = items[0]["item_id"]

mime = client.download_mime_content(item_id)
import email as email_lib
import re

msg = email_lib.message_from_bytes(mime)

def extract_text_from_mime(m, label=""):
    """Extract text/plain body from a MIME message."""
    for part in m.walk():
        ct = part.get_content_type()
        if ct == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="ignore")
        elif ct == "text/html" and not part.get_filename():
            payload = part.get_payload(decode=True)
            if payload:
                html = payload.decode("utf-8", errors="ignore")
                plain = re.sub(r"<[^>]+>", " ", html)
                plain = re.sub(r"&nbsp;", " ", plain)
                plain = re.sub(r"&lt;", "<", plain)
                plain = re.sub(r"&gt;", ">", plain)
                plain = re.sub(r"&amp;", "&", plain)
                plain = re.sub(r"\s+", " ", plain).strip()
                return plain
    return ""

# ---- Layer 0: Top-level message ----
print("=" * 70)
print("LAYER 0: 最外层邮件 (Michael Ma 转发)")
print("=" * 70)
print(f"Subject: {msg.get('Subject', '')}")
print(f"From:    {msg.get('From', '')}")
print(f"To:      {msg.get('To', '')}")
print()

# Show top-level parts (depth 1 only)
print("Top-level MIME structure (depth 1):")
for i, part in enumerate(msg.walk()):
    ct = part.get_content_type()
    fn = part.get_filename()
    cd = part.get("Content-Disposition", "")
    maintype = ct.split("/")[0] if "/" in ct else ct

    if maintype == "multipart":
        print(f"  [{i:2d}] {ct}")
    elif maintype == "message":
        sub = part.get("Subject", "(no subject header)")
        print(f"  [{i:2d}] {ct}  (nested msg, subject: {sub[:60]})")
        print(f"         disposition: {cd[:60]}")
    elif fn:
        print(f"  [{i:2d}] {ct}  filename={fn}")
    else:
        payload = part.get_payload(decode=True)
        size = len(payload) if payload else 0
        preview = payload.decode("utf-8", errors="ignore")[:100].replace("\n", "\\n") if payload else ""
        print(f"  [{i:2d}] {ct}  ({size} bytes)")
        print(f"         preview: {preview}...")

print()

# ---- Extract top-level text/plain (part index 3) ----
print("-" * 70)
print("Layer 0: text/plain (顶层 text/plain，Michael Ma 写的)")
print("-" * 70)
top_text = ""
for part in msg.walk():
    ct = part.get_content_type()
    if ct == "text/plain" and not part.get_filename():
        payload = part.get_payload(decode=True)
        if payload:
            top_text = payload.decode("utf-8", errors="ignore")
            break

print(f"Length: {len(top_text)} chars")
print()
print(top_text)

# ---- Layer 1: First message/rfc822 ----
print()
print("=" * 70)
print("LAYER 1: 第一封嵌套邮件 (message/rfc822)")
print("=" * 70)

for part in msg.walk():
    if part.get_content_type() == "message/rfc822":
        nested = part.get_payload()
        if isinstance(nested, list):
            nested = nested[0]
        if isinstance(nested, email_lib.message.Message):
            print(f"Subject: {nested.get('Subject', '')}")
            print(f"From:    {nested.get('From', '')}")
            print(f"To:      {nested.get('To', '')}")
            print()
            print("-" * 70)
            print("Layer 1: text/plain 正文")
            print("-" * 70)
            nested_text = extract_text_from_mime(nested)
            print(f"Length: {len(nested_text)} chars")
            print()
            print(nested_text[:2000])
        break

# ---- Layer 2: Nested message/rfc822 inside Layer 1 ----
print()
print("=" * 70)
print("LAYER 2: 第二层嵌套 (如果 Layer 1 还有 message/rfc822)")
print("=" * 70)

# Find the first rfc822, then look for rfc822 inside it
for part in msg.walk():
    if part.get_content_type() == "message/rfc822":
        nested = part.get_payload()
        if isinstance(nested, list):
            nested = nested[0]
        if isinstance(nested, email_lib.message.Message):
            # Walk inside nested to find ANOTHER rfc822
            for inner_part in nested.walk():
                if inner_part.get_content_type() == "message/rfc822":
                    nested2 = inner_part.get_payload()
                    if isinstance(nested2, list):
                        nested2 = nested2[0]
                    if isinstance(nested2, email_lib.message.Message):
                        print(f"Subject: {nested2.get('Subject', '')}")
                        print(f"From:    {nested2.get('From', '')}")
                        print()
                        print("-" * 70)
                        print("Layer 2: text/plain 正文")
                        print("-" * 70)
                        nested2_text = extract_text_from_mime(nested2)
                        print(f"Length: {len(nested2_text)} chars")
                        print()
                        print(nested2_text[:2000])
                    break
            # Also show text/plain of layer 1 itself
            break
