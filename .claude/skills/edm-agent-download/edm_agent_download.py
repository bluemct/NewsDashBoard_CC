"""
EDM Agent Download Skill — 从 EWS EDM 文件夹扫描并下载符合条件的邮件

匹配条件：
  - 发件人: ma.chuntao@oe.21vianet.com
  - 正文包含: "EDM Agent"
  - 有附件

输出：
  EDM/Temp/SN-xxxxx_email.eml
"""
import json
import os
import re
import base64
import email as email_lib
from xml.etree import ElementTree as ET

import requests
from requests_ntlm import HttpNtlmAuth

# ---------------------------------------------------------------------------
# EWS 命名空间
# ---------------------------------------------------------------------------
T = "http://schemas.microsoft.com/exchange/services/2006/types"
M = "http://schemas.microsoft.com/exchange/services/2006/messages"
S = "http://schemas.xmlsoap.org/soap/envelope/"

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_config.json")
TEMP_DIR = os.path.join(BASE_DIR, "EDM", "Temp")

TARGET_SENDER = "ma.chuntao"
KEYWORD = "EDM Agent"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["ews"]


def soap(cfg, body_xml: str) -> ET.Element:
    """Send EWS SOAP request, return parsed root."""
    envelope = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="{M}"
               xmlns:t="{T}"
               xmlns:soap="{S}">
  <soap:Header><t:RequestServerVersion Version="Exchange2013"/></soap:Header>
  <soap:Body>{body_xml}</soap:Body>
</soap:Envelope>'''
    sess = requests.Session()
    sess.auth = HttpNtlmAuth(cfg["domain_user"], cfg["password"])
    r = sess.post(
        cfg["url"],
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"},
        timeout=60,
    )
    r.raise_for_status()
    return ET.fromstring(r.text)


def find_folder(cfg, folder_name: str):
    body = f'''<m:FindFolder TruncatedOk="true">
      <m:FolderShape><t:BaseShape>IdOnly</t:BaseShape><t:AdditionalProperties>
        <t:FieldURI FieldURI="folder:DisplayName"/>
      </t:AdditionalProperties></m:FolderShape>
      <m:ParentFolderIds><t:DistinguishedFolderId Id="msgfolderroot"/></m:ParentFolderIds>
    </m:FindFolder>'''
    root = soap(cfg, body)
    for f in root.findall(f".//{{{T}}}Folders/{{{T}}}Folder"):
        name_el = f.find(f"{{{T}}}DisplayName")
        if name_el is not None and name_el.text == folder_name:
            fid_el = f.find(f"{{{T}}}FolderId")
            if fid_el is not None:
                return fid_el.attrib.get("Id")
    return None


def get_mime_content(cfg, item_id: str) -> bytes:
    """Download full MIME content for an email item."""
    body = f'''<m:GetItem>
      <m:ItemShape>
        <t:BaseShape>IdOnly</t:BaseShape>
        <t:AdditionalProperties>
          <t:FieldURI FieldURI="item:MimeContent"/>
        </t:AdditionalProperties>
      </m:ItemShape>
      <m:ItemIds><t:ItemId Id="{item_id}"/></m:ItemIds>
    </m:GetItem>'''
    root = soap(cfg, body)
    msgs = root.findall(f".//{{{M}}}GetItemResponseMessage/{{{M}}}Items/{{{T}}}Message")
    if not msgs:
        return b""
    mime_el = msgs[0].find(f"{{{T}}}MimeContent")
    if mime_el is not None and mime_el.text:
        return base64.b64decode(mime_el.text)
    return b""


def extract_text_body(mime_bytes: bytes) -> str:
    """Extract plain text body from MIME email."""
    msg = email_lib.message_from_bytes(mime_bytes)
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="ignore")
    return ""


def extract_sn_from_subject(subject: str):
    """Extract SN-xxxxx from subject line."""
    m = re.search(r"SN-?(\d+)", subject)
    return f"SN-{m.group(1)}" if m else None


def scan_and_download() -> dict:
    """Scan EDM folder, find matching emails, download to EDM/Temp/.

    Returns dict with found count, file list, and skipped info.
    """
    cfg = load_config()
    folder_name = cfg.get("folder_name", "EDM")
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Step 1: Find EDM folder
    folder_id = find_folder(cfg, folder_name)
    if not folder_id:
        return {"error": f"Folder '{folder_name}' not found", "count": 0, "files": []}

    # Step 2: List recent items (up to 10)
    body = f'''<m:FindItem TruncatedOk="true">
      <m:ItemShape>
        <t:BaseShape>IdOnly</t:BaseShape>
        <t:AdditionalProperties>
          <t:FieldURI FieldURI="item:Subject"/>
          <t:FieldURI FieldURI="item:DateTimeReceived"/>
          <t:FieldURI FieldURI="item:HasAttachments"/>
        </t:AdditionalProperties>
      </m:ItemShape>
      <m:ItemView MaxEntriesReturned="10" Offset="0"/>
      <m:ParentFolderIds><t:FolderId Id="{folder_id}"/></m:ParentFolderIds>
    </m:FindItem>'''
    root = soap(cfg, body)
    items = root.findall(f".//{{{T}}}Items/{{{T}}}Message")

    results = {"count": 0, "files": [], "scanned": len(items), "skipped": []}

    for item in items:
        item_id = item.find(f".//{{{T}}}ItemId")
        if item_id is None:
            continue
        item_id = item_id.attrib.get("Id")

        subj_el = item.find(f".//{{{T}}}Subject")
        subject = subj_el.text if subj_el is not None else ""

        has_att_el = item.find(f".//{{{T}}}HasAttachments")
        has_att = has_att_el.text if has_att_el is not None else "false"

        # Skip if no attachments
        if has_att.lower() != "true":
            results["skipped"].append({"subject": subject, "reason": "no attachments"})
            continue

        # Step 3: Download MIME to check sender + keyword
        mime_bytes = get_mime_content(cfg, item_id)
        if not mime_bytes:
            results["skipped"].append({"subject": subject, "reason": "no MIME content"})
            continue

        # Parse from address
        emsg = email_lib.message_from_bytes(mime_bytes)
        from_addr = emsg["From"] or ""

        # Check sender
        if TARGET_SENDER not in from_addr.lower():
            results["skipped"].append({"subject": subject, "reason": f"not from {TARGET_SENDER}"})
            continue

        # Check keyword in body
        text_body = extract_text_body(mime_bytes)
        if KEYWORD not in text_body:
            results["skipped"].append({"subject": subject, "reason": "no EDM Agent keyword"})
            continue

        # Matched! Save to EDM/Temp/
        sn = extract_sn_from_subject(subject)
        if sn:
            filename = f"{sn}_email.eml"
        else:
            filename = f"edm_agent_{item_id[:12]}.eml"

        filepath = os.path.join(TEMP_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(mime_bytes)

        results["count"] += 1
        results["files"].append({
            "path": filepath,
            "size_kb": len(mime_bytes) / 1024,
            "subject": subject,
            "from": from_addr,
            "sn": sn,
        })

        print(f"[OK] Saved: {filename} ({len(mime_bytes)/1024:.0f} KB)")
        print(f"      Subject: {subject}")
        print(f"      From: {from_addr}")

    return results


if __name__ == "__main__":
    result = scan_and_download()
    print(f"\nTotal scanned: {result['scanned']}")
    print(f"Matched: {result['count']}")
    print(f"Files: {result['files']}")
