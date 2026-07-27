"""Check all recent emails in EDM folder, regardless of attachments."""
import json, os, sys, warnings
warnings.filterwarnings("ignore", category=UserWarning)
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

with open(os.path.join(BASE_DIR, ".edm_agent_config.json")) as f:
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

# Use a wider window to see more emails
since = datetime.now() - timedelta(hours=72)
print(f"扫描窗口: {since.isoformat()} 以来的邮件 (72h)\n")

# Call find_items_since but let's also check WITHOUT attachment filter
body_xml = f"""<m:FindItem TruncatedOk="true">
  <m:ItemShape>
    <t:BaseShape>AllProperties</t:BaseShape>
  </m:ItemShape>
  <m:ItemView MaxEntriesReturned="20" Offset="0"/>
  <m:ParentFolderIds>
    <t:FolderId Id="{folder_id}"/>
  </m:ParentFolderIds>
</m:FindItem>"""

root = client._soap(body_xml)
T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

resp_msg = root.find(f".//{M}FindItemResponseMessage")
root_folder = resp_msg.find(f".//{M}RootFolder")
items = root_folder.findall(f"{T}Items/{T}Message")

print(f"EWS 返回: {len(items)} 封邮件\n")
print(f"{'序号':<4} {'有附件':<6} {'发件人':<30} {'时间':<20} {'主题'}")
print("-" * 120)

for i, item in enumerate(items):
    item_id_el = item.find(f".//{T}ItemId")
    item_id = item_id_el.attrib.get("Id", "") if item_id_el is not None else ""

    subject_el = item.find(f".//{T}Subject")
    subject = subject_el.text if subject_el is not None else ""

    received_el = item.find(f".//{T}DateTimeReceived")
    received = received_el.text if received_el is not None else ""

    has_att_el = item.find(f".//{T}HasAttachments")
    has_att = has_att_el.text if has_att_el is not None else "false"

    sender_el = item.find(f".//{T}Sender/{T}Mailbox/{T}EmailAddress")
    sender = sender_el.text if sender_el is not None else ""

    # Check if this would be found by find_items_since
    in_window = "YES"
    if received:
        try:
            dt = datetime.fromisoformat(received)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            if dt <= since:
                in_window = "OLD"
        except ValueError:
            pass

    att_marker = "✓" if has_att.lower() == "true" else "✗"
    print(f"{i+1:<4} {att_marker:<6} {sender[:28]:<30} {received[:19]:<20} {subject[:60]}")

# Also check the SeenTracker
print()
seen_file = os.path.join(BASE_DIR, ".edm_agent_seen.json")
if os.path.isfile(seen_file):
    with open(seen_file, "r", encoding="utf-8") as f:
        seen = json.load(f)
    print(f"SeenTracker 已记录: {len(seen)} 封邮件")
    for item_id, info in list(seen.items())[:5]:
        print(f"  {item_id[:30]}... action={info.get('action')} at={info.get('processed_at')}")
else:
    print("SeenTracker 文件不存在")
