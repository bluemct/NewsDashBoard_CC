"""Check charset of each text/plain part in the MIME."""
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

print("=" * 70)
print("每个 text/plain part 的 charset 和不同解码结果:")
print("=" * 70)

for i, part in enumerate(msg.walk()):
    ct = part.get_content_type()
    if ct == "text/plain" and not part.get_filename():
        payload = part.get_payload(decode=True)
        if not payload:
            continue

        # Check charset parameter
        charset = part.get_content_charset()
        cte = part.get("Content-Transfer-Encoding", "")

        print(f"\n[part {i}] size={len(payload)} charset={charset!r} encoding={cte}")

        # Try decode with declared charset
        if charset:
            try:
                decoded = payload.decode(charset, errors="strict")
                print(f"  decode({charset!r}) OK: {len(decoded)} chars")
                print(f"  preview: {decoded[:200]!r}")
            except UnicodeDecodeError as e:
                print(f"  decode({charset!r}) FAIL: {e}")

        # Try UTF-8 (current code behavior)
        utf8_text = payload.decode("utf-8", errors="ignore")
        print(f"  decode(utf-8, ignore):   {len(utf8_text)} chars  preview: {utf8_text[:80]!r}")

        # Try GBK
        gbk_text = payload.decode("gbk", errors="ignore")
        print(f"  decode(gbk, ignore):     {len(gbk_text)} chars  preview: {gbk_text[:80]!r}")

        # Try GB2312
        gb2312_text = payload.decode("gb2312", errors="ignore")
        print(f"  decode(gb2312, ignore):  {len(gb2312_text)} chars  preview: {gb2312_text[:80]!r}")

        # Try GB18030
        gb18030_text = payload.decode("gb18030", errors="ignore")
        print(f"  decode(gb18030, ignore): {len(gb18030_text)} chars  preview: {gb18030_text[:80]!r}")

        # First 30 raw bytes
        raw = payload[:60]
        print(f"  raw bytes (hex): {raw.hex()}")
