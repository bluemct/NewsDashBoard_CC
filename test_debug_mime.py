"""Debug: dump MIME content of the email to inspect subject and body structure."""
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

folder_name = ews_config.get("folder_name", "EDM")
folder_id = client.find_folder(folder_name)
if not folder_id:
    print(f"FAIL: 找不到文件夹 '{folder_name}'")
    sys.exit(1)

since = datetime.now() - timedelta(hours=36)
items = client.find_items_since(folder_id, since, max_items=50)
print(f"EWS 返回: {len(items)} 封邮件\n")

for item in items:
    item_id = item.get("item_id", "")
    sender = item.get("sender", "")
    subject = item.get("subject", "")
    received = item.get("received", "")

    print("=" * 70)
    print(f"From FindItem:")
    print(f"  item_id:  {item_id}")
    print(f"  sender:   {sender}")
    print(f"  subject:  {subject}")
    print(f"  received: {received}")

    # --- Get body via EWS get_item_body (MIME parse) ---
    print(f"\n  Calling get_item_body('{item_id}')...")
    body_info = client.get_item_body(item_id)
    print(f"  subject (from MIME): '{body_info.get('subject', '')}'")
    print(f"  body length:         {len(body_info.get('body', ''))}")
    print(f"  body_type:           {body_info.get('body_type', '')}")
    print(f"  entry_id:            {body_info.get('entry_id', '')}")
    if body_info.get("body"):
        print(f"  body preview:        {body_info['body'][:200]}")

    # --- Download raw MIME and inspect structure ---
    print(f"\n  Calling download_mime_content('{item_id}')...")
    mime = client.download_mime_content(item_id)
    print(f"  MIME size: {len(mime)} bytes")

    if mime:
        import email as email_lib
        msg = email_lib.message_from_bytes(mime)

        print(f"\n  MIME top-level headers:")
        print(f"    Subject:     {msg.get('Subject', '(None)')}")
        print(f"    From:        {msg.get('From', '(None)')}")
        print(f"    To:          {msg.get('To', '(None)')}")
        print(f"    Content-Type: {msg.get('Content-Type', '(None)')}")
        print(f"    Content-Transfer-Encoding: {msg.get('Content-Transfer-Encoding', '(None)')}")

        print(f"\n  MIME parts walk:")
        for i, part in enumerate(msg.walk()):
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            fn = part.get_filename()
            maintype = part.get_content_type().split("/")[0] if "/" in part.get_content_type() else ""

            if maintype in ("text", "message"):
                payload_b = part.get_payload(decode=True)
                payload_preview = payload_b.decode("utf-8", errors="ignore")[:200] if payload_b else "(empty)"
                print(f"    [{i}] content-type={ct}, filename={fn}, disposition={cd[:60]}")
                print(f"        preview: {payload_preview}")
            else:
                print(f"    [{i}] content-type={ct}, filename={fn}, disposition={cd[:60]}")
    else:
        print("  MIME content is EMPTY — EWS returned no MimeContent")

    # --- Try GetItem with BodyType=Text directly ---
    print(f"\n  Trying direct GetItem with BodyType=Text...")
    try:
        body_xml = f"""<m:GetItem>
          <m:ItemShape>
            <t:BaseShape>IdOnly</t:BaseShape>
            <t:AdditionalProperties>
              <t:FieldURI FieldURI="item:Subject"/>
              <t:FieldURI FieldURI="item:Body"/>
            </t:AdditionalProperties>
          </m:ItemShape>
          <m:ItemIds>
            <t:ItemId Id="{item_id}"/>
          </m:ItemIds>
        </m:GetItem>"""

        from lxml import etree
        NAMESPACE = {
            "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
            "t": "http://schemas.microsoft.com/exchange/services/2006/types",
        }

        env = {
            "Content-Type": "text/xml; charset=utf-8",
        }
        soap = f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
          <s:Body>
            {body_xml}
          </s:Body>
        </s:Envelope>"""

        import requests
        resp = requests.post(
            ews_config["url"],
            data=soap.encode("utf-8"),
            headers=env,
            auth=(ews_config["domain_user"], ews_config["password"]),
            timeout=15,
        )
        tree = etree.fromstring(resp.content)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
        M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

        messages = tree.findall(f".//{M}GetItemResponseMessage/{M}Items/{T}Message")
        if messages:
            m = messages[0]
            subj_el = m.find(f"{T}Subject")
            body_el = m.find(f"{T}Body")
            print(f"    Subject (GetItem): '{subj_el.text if subj_el is not None else '(None)'}'")
            print(f"    Body (GetItem):    '{(body_el.text if body_el is not None else '(None)')[:200]}'")
            print(f"    Body tag:          {body_el.tag if body_el is not None else '(None)'}")
    except Exception as e:
        print(f"    GetItem error: {e}")

    print()
