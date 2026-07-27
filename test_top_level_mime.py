"""Show only top-level text parts (skip into message/rfc822)."""
import json, os, sys, warnings, email as email_lib
warnings.filterwarnings("ignore", category=UserWarning)
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

with open(os.path.join(BASE_DIR, ".edm_agent_config.json")) as f:
    config = json.load(f)

from edm_agent import EWSClient
from datetime import datetime, timedelta

client = EWSClient(
    url=config["ews"]["url"],
    domain_user=config["ews"]["domain_user"],
    password=config["ews"]["password"],
    mailbox=config["ews"]["mailbox"],
)
folder_id = client.find_folder("EDM")
items = client.find_items_since(folder_id, datetime.now() - timedelta(hours=36), max_items=1)
mime = client.download_mime_content(items[0]["item_id"])
msg = email_lib.message_from_bytes(mime)

def walk_top_level(m, depth=0):
    """Walk MIME but do NOT descend into message/rfc822."""
    results = []
    payload = m.get_payload()
    if isinstance(payload, list):
        for p in payload:
            if isinstance(p, email_lib.message.Message):
                if p.get_content_type() == "message/rfc822":
                    sub = p.get("Subject", "(no subject)")
                    print(f"  {'  ' * depth}[skip rfc822] Subject: {sub[:80]}")
                    continue
                if p.is_multipart():
                    results.extend(walk_top_level(p, depth + 1))
                else:
                    ct = p.get_content_type()
                    fn = p.get_filename()
                    pl = p.get_payload(decode=True)
                    size = len(pl) if pl else 0
                    preview = ""
                    if pl and "text" in ct:
                        preview = pl.decode("utf-8", errors="ignore")[:150].replace("\n", "\\n")
                    marker = "" if not fn else f" fn={fn!r}"
                    print(f"  {'  ' * depth}[part] {ct} size={size}{marker}")
                    if preview:
                        print(f"  {'  ' * depth}     {preview}...")
                    results.append({"part": p, "size": size, "ct": ct})
    return results

print("=" * 70)
print("Top-level walk (NOT descending into message/rfc822):")
print("=" * 70)
results = walk_top_level(msg)

print()
print("=" * 70)
print("对比: 外层 text/plain vs 嵌套 text/plain")
print("=" * 70)

# The current get_item_body gets the first text/plain from walk()
# which IS part [3] — the outer text/plain
# Let's check if the 1300 chars includes the inner content or not

for part in msg.walk():
    ct = part.get_content_type()
    if ct == "text/plain" and not part.get_filename():
        payload = part.get_payload(decode=True)
        if payload:
            text = payload.decode("utf-8", errors="ignore")
            has_fwd_marker = "From: " in text and "Sent: " in text
            label = "OUTER (has forwarded text)" if has_fwd_marker and len(text) < 5000 else "NESTED"
            if len(text) < 2000:
                print(f"\n{label} — {len(text)} chars")
                print("-" * 50)
                print(text)
            else:
                print(f"\n{label} — {len(text)} chars (too long, showing first 300)")
                print("-" * 50)
                print(text[:300])
            break  # only show first one
