"""Debug: step through email download."""
import sys, warnings, os, io
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, ".")

from edm_agent import EWSClient, EmailDownloader, EWS_FOLDER_NAME
from datetime import datetime, timedelta

ews = EWSClient()
folder_id = ews.find_folder(EWS_FOLDER_NAME)

items = ews.find_items_since(folder_id, datetime.now() - timedelta(hours=48), max_items=10)
print(f"Found {len(items)} items with attachments\n")

# Try all items, show attachment details
for item in items:
    print(f"=== [{item['subject'][:60]}] ===")

    # Get attachments directly
    attachments = ews.get_attachments_list(item["item_id"])
    msg_count = 0
    xlsx_count = 0
    other = []
    for a in attachments:
        ext = os.path.splitext(a["name"])[1].lower()
        if ext == ".msg":
            msg_count += 1
            print(f"  MSG: {a['name']} (is_item={a['is_item']})")
        elif ext == ".xlsx":
            xlsx_count += 1
            print(f"  XLSX: {a['name']} (is_item={a['is_item']})")
        else:
            other.append(a)
            print(f"  OTHER: {a['name']} ({ext}, is_item={a['is_item']})")

    print(f"  Summary: {msg_count} .msg, {xlsx_count} .xlsx, {len(other)} other")
    print()

    # If found, stop
    if msg_count > 0 or xlsx_count > 0:
        break
else:
    print("No items with .msg or .xlsx found in recent 48h")
    print("\nThis is expected — the EDM emails have ItemAttachments (nested emails),")
    print("not FileAttachments with .msg extension.")
    print("\nFor EDM processing, item attachments need special handling:")
    print("  EWS returns them as MIME content, not .msg files.")
    print("  Need to save as .msg or use MIME parsing instead.")
