"""
EDM Auto Agent — EWS 邮件监听 + LLM 分析 + 人工确认 + Skill 自动执行

功能：
  1. EWS 轮询 EDM 文件夹，发现新邮件
  2. 读取邮件正文，LLM 分析判断是否为 EDM 处理需求
  3. 人工审核确认后，将邮件保存为 .msg 到 EDM/Temp/
  4. 自动执行 EDM Process（从 .msg 提取嵌套 EDM 模板）→ Discover XLSX → Import Test List
  5. 结果输出到 results/ 和 Log/ 目录

用法：
    python edm_agent.py

配置：
    .edm_agent_config.json  — EWS 凭据 + 参数

依赖：
    pip install requests litellm extract-msg olefile openpyxl
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import base64
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from requests_ntlm import HttpNtlmAuth
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# EWS 命名空间
# ---------------------------------------------------------------------------
EWS_T_NS = "http://schemas.microsoft.com/exchange/services/2006/types"
EWS_M_NS = "http://schemas.microsoft.com/exchange/services/2006/messages"

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Log")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_config.json")
LLM_CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_llm_config.json")

# ---------------------------------------------------------------------------
# 加载配置文件
# ---------------------------------------------------------------------------
def load_config():
    """Load .edm_agent_config.json. Raises on missing/invalid."""
    if not os.path.isfile(CONFIG_FILE):
        raise FileNotFoundError(f"Config not found: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_llm_config():
    """Load .edm_agent_llm_config.json. Returns defaults if missing."""
    defaults = {
        "model": "openai/WanWu/MiniMax-M3",
        "api_base": "http://61.49.53.5:30001/v1",
        "api_key": "deepSeek-v3.1",
        "timeout": 30,
    }
    if not os.path.isfile(LLM_CONFIG_FILE):
        return defaults
    try:
        with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
        return defaults
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load LLM config: {e}")
        return defaults


config = load_config()
ews_config = config["ews"]

EWS_URL = ews_config["url"]
EWS_DOMAIN_USER = ews_config["domain_user"]
EWS_PASSWORD = ews_config["password"]
EWS_MAILBOX = ews_config["mailbox"]
EWS_FOLDER_NAME = ews_config.get("folder_name", "EDM")
POLL_INTERVAL = config.get("poll_interval", 30)

# Directories — from config with defaults
EDM_OUTPUT_DIR = config.get("output_base", os.path.join(BASE_DIR, "EDM"))
TEMP_DIR = config.get("temp_dir", os.path.join(BASE_DIR, "Temp"))

# Filter rules — from config with defaults
FILTER_RULES = config.get("filter_rules", {
    "sender": ["ma.chuntao@oe.21vianet.com"],
    "subject_keywords": ["edm"],
    "body_keywords": ["EDM Agent"],
})

# Ensure directories exist
os.makedirs(TEMP_DIR, exist_ok=True)

# LLM 配置 — 从 JSON 加载
llm_config = load_llm_config()

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("edm_agent")


# =========================================================================
# 1. EWS 通信层 — 纯 Python requests 调用 SOAP
#    参考 edm_mail_analyzer.ps1 的 EWS 调用方式
# =========================================================================

class EWSClient:
    """EWS SOAP client — Basic Auth with domain user, impersonates mailbox."""

    def __init__(self, url=EWS_URL, domain_user=EWS_DOMAIN_USER, password=EWS_PASSWORD, mailbox=EWS_MAILBOX):
        self.url = url
        self.mailbox = mailbox
        self.session = requests.Session()
        # NTLM auth with domain user
        self.session.auth = HttpNtlmAuth(domain_user, password)

    def _soap(self, body_xml: str) -> ET.Element:
        """Send a SOAP request and return parsed XML root."""
        soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="{EWS_M_NS}"
               xmlns:t="{EWS_T_NS}"
               xmlns:soap="{SOAP_NS}">
  <soap:Header>
    <t:RequestServerVersion Version="Exchange2013"/>
  </soap:Header>
  <soap:Body>{body_xml}</soap:Body>
</soap:Envelope>"""

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
        }

        resp = self.session.post(self.url, data=soap_envelope.encode("utf-8"), headers=headers, timeout=30)
        resp.raise_for_status()

        raw = resp.text
        root = ET.fromstring(raw)

        # Check for SOAP fault
        body_el = root.find(f"{{{SOAP_NS}}}Body")
        if body_el is not None:
            fault = body_el.find(f"{{{SOAP_NS}}}Fault")
            if fault is not None:
                reason = fault.find(".//{%s}Reason" % SOAP_NS)
                text = (reason.find(f"{{{SOAP_NS}}}Text") if reason is not None else None)
                msg = text.text if text is not None else "Unknown SOAP fault"
                raise RuntimeError(f"EWS SOAP fault: {msg}")

        return root

    def find_folder(self, folder_name: str) -> str | None:
        """Find folder by display name under msgfolderroot. Returns folder ID or None.

        Lists all root folders and matches by name in Python (no server-side Restriction).
        """
        body = f"""<m:FindFolder TruncatedOk="true">
          <m:FolderShape>
            <t:BaseShape>IdOnly</t:BaseShape>
            <t:AdditionalProperties>
              <t:FieldURI FieldURI="folder:DisplayName"/>
            </t:AdditionalProperties>
          </m:FolderShape>
          <m:ParentFolderIds>
            <t:DistinguishedFolderId Id="msgfolderroot"/>
          </m:ParentFolderIds>
        </m:FindFolder>"""

        root = self._soap(body)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
        M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

        resp_msg = root.find(f".//{M}FindFolderResponseMessage")
        if resp_msg is None:
            return None

        root_folder = resp_msg.find(f".//{M}RootFolder")
        if root_folder is None:
            return None

        folders = root_folder.findall(f"{T}Folders/{T}Folder")
        for f in folders:
            name_el = f.find(f"{T}DisplayName")
            if name_el is not None and name_el.text == folder_name:
                fid_el = f.find(f"{T}FolderId")
                if fid_el is not None:
                    return fid_el.attrib.get("Id")
        return None

    def find_items_since(self, folder_id: str, since: datetime, max_items: int = 50) -> list[dict]:
        """Find items received after *since* that have attachments.

        Lists recent items from the folder and filters in Python.
        """
        body = f"""<m:FindItem TruncatedOk="true">
          <m:ItemShape>
            <t:BaseShape>AllProperties</t:BaseShape>
          </m:ItemShape>
          <m:ItemView MaxEntriesReturned="{max_items}" Offset="0"/>
          <m:ParentFolderIds>
            <t:FolderId Id="{folder_id}"/>
          </m:ParentFolderIds>
        </m:FindItem>"""

        root = self._soap(body)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
        M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

        resp_msg = root.find(f".//{M}FindItemResponseMessage")
        if resp_msg is None:
            return []

        root_folder = resp_msg.find(f".//{M}RootFolder")
        if root_folder is None:
            return []

        items = root_folder.findall(f"{T}Items/{T}Message")
        results = []
        for item in items:
            item_id_el = item.find(f".//{T}ItemId")
            item_id = item_id_el.attrib.get("Id") if item_id_el is not None else None

            subject_el = item.find(f".//{T}Subject")
            subject = subject_el.text if subject_el is not None else ""

            received_el = item.find(f".//{T}DateTimeReceived")
            received_str = received_el.text if received_el is not None else ""

            # Filter by date in Python
            if received_str:
                try:
                    received_dt = datetime.fromisoformat(received_str)
                    # Convert UTC to local time for comparison with `since` (local)
                    if received_dt.tzinfo is not None:
                        received_dt = received_dt.astimezone().replace(tzinfo=None)
                    if received_dt <= since:
                        continue  # too old, skip
                except ValueError:
                    pass

            has_att_el = item.find(f".//{T}HasAttachments")
            has_att = has_att_el.text if has_att_el is not None else "false"

            # Only return items with attachments
            if has_att.lower() != "true":
                continue

            sender_address = ""
            sender_el = item.find(f".//{T}Sender/{T}Mailbox/{T}EmailAddress")
            if sender_el is not None:
                sender_address = sender_el.text or ""

            results.append({
                "item_id": item_id,
                "subject": subject,
                "received": received_str,
                "has_attachments": True,
                "sender": sender_address,
            })

        return results

    def get_item_body(self, item_id: str, change_key: str = "") -> dict:
        """Get body text, subject, and EntryID for an item.

        Uses download_mime_content (the only reliable EWS call on 21Vianet)
        and parses the MIME to extract subject and plain text body.
        Also fetches EntryID via a separate GetItem call.
        """
        mime = self.download_mime_content(item_id)
        if not mime:
            return {"body": "", "subject": "", "body_type": "Text", "entry_id": ""}

        try:
            import email as email_lib
            msg = email_lib.message_from_bytes(mime)
            subject = msg["Subject"] or ""
            body_text = ""

            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                        break
                elif ct == "text/html" and not body_text and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        # Rough HTML-to-text
                        plain = re.sub(r"<[^>]+>", " ", html)
                        plain = re.sub(r"&nbsp;", " ", plain)
                        plain = re.sub(r"&lt;", "<", plain)
                        plain = re.sub(r"&gt;", ">", plain)
                        plain = re.sub(r"&amp;", "&", plain)
                        plain = re.sub(r"\s+", " ", plain).strip()
                        body_text = plain
                        break

            # Fetch EntryID separately (best-effort, not critical)
            entry_id = ""
            try:
                entry_id = self.get_entry_id(item_id) or ""
            except Exception:
                logger.warning(f"get_entry_id failed for {item_id}, skipping (21Vianet EWS limitation)")

            return {
                "body": body_text,
                "subject": subject,
                "body_type": "Text",
                "entry_id": entry_id,
            }
        except Exception:
            return {"body": "", "subject": "", "body_type": "Text", "entry_id": ""}

    def get_attachments_list(self, item_id: str) -> list[dict]:
        """Get attachment info for an item. Returns list of {id, change_key, name, is_item}."""
        body = f"""<m:GetItem>
          <m:ItemShape>
            <t:BaseShape>AllProperties</t:BaseShape>
          </m:ItemShape>
          <m:ItemIds>
            <t:ItemId Id="{item_id}"/>
          </m:ItemIds>
        </m:GetItem>"""

        root = self._soap(body)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"

        attachments = []
        for att in root.findall(f".//{T}FileAttachment"):
            att_id_el = att.find(f"{T}AttachmentId")
            if att_id_el is not None:
                name_el = att.find(f"{T}Name")
                attachments.append({
                    "id": att_id_el.attrib.get("Id"),
                    "change_key": att_id_el.attrib.get("ChangeKey", ""),
                    "name": name_el.text if name_el is not None else "unknown",
                    "is_item": False,
                })

        for att in root.findall(f".//{T}ItemAttachment"):
            att_id_el = att.find(f"{T}AttachmentId")
            if att_id_el is not None:
                name_el = att.find(f"{T}Name")
                attachments.append({
                    "id": att_id_el.attrib.get("Id"),
                    "change_key": att_id_el.attrib.get("ChangeKey", ""),
                    "name": name_el.text if name_el is not None else "unknown",
                    "is_item": True,
                })

        return attachments

    def download_attachment(self, attachment_id: str, change_key: str = "") -> bytes:
        """Download attachment content (base64 decoded)."""
        body = f"""<m:GetAttachment>
          <m:AttachmentIds>
            <t:AttachmentId Id="{attachment_id}" ChangeKey="{change_key}"/>
          </m:AttachmentIds>
        </m:GetAttachment>"""

        root = self._soap(body)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"

        # File attachment
        content_el = root.find(f".//{T}FileAttachment/{T}Content")
        if content_el is not None and content_el.text:
            return base64.b64decode(content_el.text)

        # Item attachment — get MIME content
        mime_el = root.find(f".//{T}ItemAttachment/{T}Item/{T}MimeContent")
        if mime_el is not None and mime_el.text:
            return base64.b64decode(mime_el.text)

        return b""

    def download_mime_content(self, item_id: str) -> bytes:
        """Get the full MIME content of an email item (base64 decoded)."""
        body_xml = f"""<m:GetItem>
          <m:ItemShape>
            <t:BaseShape>IdOnly</t:BaseShape>
            <t:AdditionalProperties>
              <t:FieldURI FieldURI="item:MimeContent"/>
            </t:AdditionalProperties>
          </m:ItemShape>
          <m:ItemIds>
            <t:ItemId Id="{item_id}"/>
          </m:ItemIds>
        </m:GetItem>"""

        root = self._soap(body_xml)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
        M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

        messages = root.findall(f".//{M}GetItemResponseMessage/{M}Items/{T}Message")
        if not messages:
            return b""

        mime_el = messages[0].find(f"{T}MimeContent")
        if mime_el is not None and mime_el.text:
            return base64.b64decode(mime_el.text)
        return b""

    def get_entry_id(self, item_id: str) -> str | None:
        """Get the EntryID of an item from its ItemId.

        EntryID is needed for win32com namespace.GetItemFromID().
        """
        body_xml = f"""<m:GetItem>
          <m:ItemShape>
            <t:BaseShape>IdOnly</t:BaseShape>
            <t:AdditionalProperties>
              <t:FieldURI FieldURI="item:EntryId"/>
            </t:AdditionalProperties>
          </m:ItemShape>
          <m:ItemIds>
            <t:ItemId Id="{item_id}"/>
          </m:ItemIds>
        </m:GetItem>"""

        root = self._soap(body_xml)
        T = "{http://schemas.microsoft.com/exchange/services/2006/types}"
        M = "{http://schemas.microsoft.com/exchange/services/2006/messages}"

        messages = root.findall(f".//{M}GetItemResponseMessage/{M}Items/{T}Message")
        if not messages:
            return None

        entry_el = messages[0].find(f"{T}EntryId")
        if entry_el is not None and entry_el.text:
            return entry_el.text.strip()
        return None

    def test_connection(self):
        """Test EWS connection by calling GetFolder. Returns True on success."""
        # Simple test: try to find the folder
        folder_id = self.find_folder(EWS_FOLDER_NAME)
        return folder_id is not None


# =========================================================================
# 2. 邮件获取 — 读取正文分析 + 保存 .msg 到 Temp
# =========================================================================

class EmailFetcher:
    """Fetch email body for analysis, and save the email as .msg for edm_process.

    Pipeline:
      1. EWS polls EDM folder → finds new email
      2. Read email body (via GetItem) → LLM analyzes intent
      3. Human confirms in GUI
      4. Download MIME as .eml → convert with eml-to-msg skill → .msg in Temp/
      5. edm_process.py reads .msg from Temp/, extracts nested EDM template .msg
    """

    def __init__(self, ews: EWSClient):
        self.ews = ews
        self.eml2msg_script = os.path.join(
            BASE_DIR, ".claude", "skills", "eml-to-msg", "eml_to_msg.py"
        )

    def fetch_info(self, item_id: str) -> dict:
        """Get email body + subject + EntryID from EWS (no file saved yet)."""
        body_info = self.ews.get_item_body(item_id)
        return {
            "body": body_info.get("body", ""),
            "subject": body_info.get("subject", ""),
            "entry_id": body_info.get("entry_id", ""),
            "item_id": item_id,
        }

    def save_as_msg(self, item_id: str, subject: str, entry_id: str = "") -> str | None:
        """Save email as .msg to TEMP_DIR.

        Pipeline:
          1. Download MIME from EWS → save as .eml in Temp/
          2. Call eml-to-msg skill to convert .eml → .msg (same directory)

        Returns the .msg path or None.
        """
        logger.info(f"Saving email {item_id} as .msg to {TEMP_DIR}/")

        # Step 1: Download MIME as .eml
        mime = self.ews.download_mime_content(item_id)
        if not mime:
            logger.error("No MIME content from EWS")
            return None

        safe_subject = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '_', subject[:80])
        safe_subject = safe_subject.rstrip('.').strip() or "EDM_email"
        eml_path = os.path.join(TEMP_DIR, safe_subject + ".eml")

        try:
            with open(eml_path, "wb") as f:
                f.write(mime)
            logger.info(f"  Saved .eml: {os.path.basename(eml_path)}")
        except IOError as e:
            logger.error(f"Failed to save .eml: {e}")
            return None

        # Step 2: Convert .eml → .msg using eml-to-msg skill
        if not os.path.isfile(self.eml2msg_script):
            logger.error(f"eml-to-msg script not found: {self.eml2msg_script}")
            return None

        try:
            result = subprocess.run(
                [sys.executable, self.eml2msg_script, eml_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=BASE_DIR,
            )

            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    logger.info(f"  [EML2MSG] {line}")

            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    logger.warning(f"  [EML2MSG-ERR] {line}")

            # eml_to_msg writes .msg beside the .eml (same directory, same name)
            msg_path = eml_path.rsplit(".", 1)[0] + ".msg"
            if os.path.isfile(msg_path):
                size_kb = os.path.getsize(msg_path) / 1024
                logger.info(f"  Saved: {os.path.basename(msg_path)} ({size_kb:.1f} KB)")
                # Clean up .eml
                os.remove(eml_path)
                return msg_path
            else:
                logger.error(f"eml-to-msg did not produce .msg file: {msg_path}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("eml-to-msg timed out (>30s)")
            return None
        except Exception as e:
            logger.error(f"eml-to-msg failed: {e}")
            return None


# =========================================================================
# 3. LLM 分析器 — 判断邮件需求
# =========================================================================

class EmailAnalyzer:
    """Use LLM to analyze email intent.

    Reads model config from .edm_agent_llm_config.json so users can switch
    to any litellm-compatible model without modifying code.
    """

    SYSTEM_PROMPT = """你是一个 EDM 邮件分析助手。
你的任务是分析邮件内容，判断这封邮件是否需要执行 EDM 邮件营销处理流程。

判断标准：
- 邮件包含 SN 号码（如 SN-12345）→ 需要 EDM 处理
- 邮件提到 EDM、邮件营销、Email Marketing、Token、模板 → 需要 EDM 处理
- 邮件是关于发送 EDM 邮件的请求 → 需要 EDM 处理
- 其他类型的邮件 → 不需要处理

请只返回 JSON 格式的结果：
{
  "action": "edm_process" 或 "ignore",
  "confidence": 0-100 的置信度,
  "reason": "简短判断理由",
  "sn": "提取的 SN 号码，如果没有则为 null"
}
不要输出其他任何内容，只返回 JSON。"""

    def analyze(self, subject: str, body: str) -> dict:
        """Analyze email and return action decision.

        Uses llm_config global for model, api_base, api_key, timeout.
        Falls back to keyword matching on any error.
        """
        import time
        start = time.time()
        user_content = f"""请分析以下邮件：

主题：{subject}

正文：
{body[:3000]}
"""
        cfg = llm_config
        try:
            from litellm import completion

            resp = completion(
                model=cfg["model"],
                api_base=cfg["api_base"],
                api_key=cfg["api_key"],
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                timeout=cfg.get("timeout", 30),
            )

            elapsed = time.time() - start
            text = resp.choices[0].message.content.strip()

            # Handle markdown code blocks
            if "```" in text:
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
                if match:
                    text = match.group(1).strip()

            result = json.loads(text)

            if "action" not in result:
                result["action"] = "ignore"
                result["reason"] = "LLM 返回格式不正确"

            result["_model"] = cfg["model"]
            result["_fallback"] = False
            result["_elapsed"] = round(elapsed, 1)
            logger.info(
                f"LLM 分析结果 ({result['_model']}): "
                f"action={result['action']}, confidence={result.get('confidence', 0)}"
            )
            return result

        except Exception as e:
            logger.warning(f"LLM 分析失败 ({cfg['model']}): {e}，降级为规则匹配")
            elapsed = time.time() - start
            result = self._fallback_analyze(subject, body)
            result["_model"] = cfg["model"]
            result["_fallback"] = True
            result["_elapsed"] = round(elapsed, 1)
            return result

    def _fallback_analyze(self, subject: str, body: str) -> dict:
        """Fallback: simple keyword matching."""
        text = subject + " " + body

        sn_match = re.search(r"SN-?\d+", text)
        sn = sn_match.group(0) if sn_match else None

        keywords = ["edm", "SN-", "sn-", "token", "模板", "email marketing", "邮件营销"]
        if any(kw.lower() in text.lower() for kw in keywords):
            return {
                "action": "edm_process",
                "confidence": 80,
                "reason": "规则匹配：检测到 EDM 相关关键词",
                "sn": sn,
            }

        if sn:
            return {
                "action": "edm_process",
                "confidence": 90,
                "reason": "规则匹配：检测到 SN 号码",
                "sn": sn,
            }

        return {
            "action": "ignore",
            "confidence": 60,
            "reason": "未检测到 EDM 相关关键词",
            "sn": None,
        }


# =========================================================================
# 4. EDM 执行器 — 调用 edm_process.py
# =========================================================================

class EDMExecutor:
    """Execute EDM processing pipeline."""

    def __init__(self):
        self.process_script = os.path.join(
            BASE_DIR, ".claude", "skills", "edm-process", "edm_process.py"
        )

    def process(self, temp_dir: str, edm_dir: str, gui_log=None) -> dict:
        """Run edm_process.py with --temp-dir and --edm-dir.

        Args:
            temp_dir: Directory containing .msg and .xlsx inputs.
            edm_dir: Base directory for SN output folders.
            gui_log: Optional callback (step, message) for GUI log entries.
        """
        logger.info(f"Running EDM Process (temp={temp_dir}, edm={edm_dir})")

        try:
            result = subprocess.run(
                [sys.executable, self.process_script, "--temp-dir", temp_dir, "--edm-dir", edm_dir],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=BASE_DIR,
            )

            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    logger.info(f"  [Process] {line}")
                    if gui_log:
                        gui_log("处理", line)
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    logger.warning(f"  [Process-ERR] {line}")
                    if gui_log:
                        gui_log("处理", f"ERR: {line}")

            success = result.returncode == 0

            # Extract SN from log output
            sn = None
            full_output = result.stdout + result.stderr
            sn_match = re.search(r"\[SN\]\s+(SN-\d+)", full_output)
            if sn_match:
                sn = sn_match.group(1)

            sn_folder = os.path.join(edm_dir, sn) if sn else None

            # Collect last error line for summary
            error_msg = ""
            if not success:
                err_lines = result.stderr.strip().split("\n") if result.stderr else []
                # Find the actual error (last meaningful line, usually a Traceback end)
                for line in reversed(err_lines):
                    stripped = line.strip()
                    if stripped and not stripped.startswith("File") and not stripped.startswith("  "):
                        error_msg = stripped
                        break
                if not error_msg and err_lines:
                    error_msg = err_lines[-1].strip()

            return {
                "success": success,
                "sn": sn,
                "sn_folder": sn_folder,
                "return_code": result.returncode,
                "error": error_msg,
            }

        except subprocess.TimeoutExpired:
            logger.error("EDM Process timed out (>120s)")
            return {"success": False, "error": "超时 (>120s)"}
        except Exception as e:
            logger.error(f"EDM Process error: {e}")
            return {"success": False, "error": str(e)}

    def import_test_list(self, xlsx_path: str, sn: str) -> dict:
        """Import test list to Unimarketing."""
        logger.info(f"Importing test list for {xlsx_path} (SN: {sn})")

        import_skill = os.path.join(
            BASE_DIR, ".claude", "skills", "unimarketing-contactimport2list",
            "unimarketing_test_list.py",
        )

        if not os.path.isfile(import_skill):
            logger.error(f"Import skill not found: {import_skill}")
            return {"success": False, "error": "Import skill not found"}

        try:
            result = subprocess.run(
                [sys.executable, import_skill, "--xlsx", xlsx_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                cwd=BASE_DIR,
            )

            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    logger.info(f"  [Import] {line}")

            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    logger.warning(f"  [Import-ERR] {line}")

            success = result.returncode == 0

            list_id = None
            list_match = re.search(r"listId[=:\s]+(\d+)", result.stdout)
            if list_match:
                list_id = list_match.group(1)

            return {
                "success": success,
                "list_id": list_id,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            logger.error("Import timed out (>180s)")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            logger.error(f"Import error: {e}")
            return {"success": False, "error": str(e)}


# =========================================================================
# 5. 邮件通知 — 处理完成后发送通知
# =========================================================================

class NotificationSender:
    """Send processing notification via edm_agent_send_email.py.

    Uses subprocess to call the standalone SMTP sender script,
    keeping notification logic separate from the main agent.
    """

    def __init__(self):
        self.sender_script = os.path.join(BASE_DIR, "edm_agent_send_email.py")

    def send(self, subject: str, body: str) -> bool:
        """Send notification email via subprocess.

        Returns True if subprocess exited with code 0.
        """
        if not os.path.isfile(self.sender_script):
            logger.error(f"Notification script not found: {self.sender_script}")
            return False

        try:
            result = subprocess.run(
                [sys.executable, self.sender_script, "--subject", subject, "--body", body],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=BASE_DIR,
            )

            if result.returncode == 0:
                logger.info("Notification email sent successfully")
            else:
                logger.warning(
                    f"Notification email failed (rc={result.returncode}): "
                    f"{result.stderr.strip()}"
                )

            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    logger.info(f"  [Notify] {line}")
            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.warning("Notification email timed out (>30s)")
            return False
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    def build_result_html(self, subject: str, result: dict) -> str:
        """Build an HTML notification body from action_result."""
        sn = result.get("sn", "N/A") or "N/A"
        email_subject = result.get("subject", subject) or subject
        sender = result.get("sender", "N/A") or "N/A"
        action = result.get("action", "N/A")
        confidence = result.get("confidence", 0)
        reason = result.get("reason", "")
        process_ok = result.get("process_success")
        import_ok = result.get("import_success")
        sn_folder = result.get("process", {}).get("sn_folder", "N/A") if result.get("process") else "N/A"

        import_info = result.get("import", {})
        list_id = import_info.get("list_id", "N/A") if import_info else "N/A"

        overall = result.get("success", False)
        status_text = "成功" if overall else "失败"
        status_color = "#22c55e" if overall else "#ef4444"

        def _status(v):
            if v is True:
                return '<span style="color:#22c55e">✓ 成功</span>'
            if v is False:
                return '<span style="color:#ef4444">✗ 失败</span>'
            return '<span style="color:#888">—</span>'

        html = f"""\
<html>
<body style="font-family: Consolas, 'Microsoft YaHei UI', monospace; background:#f8f9fa; padding:20px;">
  <h2 style="color:{status_color};">EDM Agent 处理结果: {status_text}</h2>
  <table style="border-collapse:collapse; width:100%; max-width:600px; background:white;">
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold; width:160px;">主题</td>
        <td style="padding:8px; border:1px solid #ddd;">{email_subject}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">SN</td>
        <td style="padding:8px; border:1px solid #ddd;">{sn}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">发件人</td>
        <td style="padding:8px; border:1px solid #ddd;">{sender}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">LLM 判断</td>
        <td style="padding:8px; border:1px solid #ddd;">{action} (置信度 {confidence}%)</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">判断理由</td>
        <td style="padding:8px; border:1px solid #ddd;">{reason}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">EDM Process</td>
        <td style="padding:8px; border:1px solid #ddd;">{_status(process_ok)}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">Import Test List</td>
        <td style="padding:8px; border:1px solid #ddd;">{_status(import_ok)}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">List ID</td>
        <td style="padding:8px; border:1px solid #ddd;">{list_id}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">SN 文件夹</td>
        <td style="padding:8px; border:1px solid #ddd;">{sn_folder}</td></tr>
    <tr><td style="padding:8px; border:1px solid #ddd; font-weight:bold;">时间</td>
        <td style="padding:8px; border:1px solid #ddd;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
  </table>
</body>
</html>"""
        return html


# =============================================================================
# 6. 邮件过滤引擎 — 按发件人/主题/正文关键字筛选
# =============================================================================

class FilterEngine:
    """Filter emails by sender, subject keywords, and body keywords.

    Rule (from config ``filter_rules``):
      - ``sender``            list of accepted sender addresses
      - ``subject_keywords``  list of keywords — at least ONE must match subject
      - ``body_keywords``     list of keywords — at least ONE must match body

    An email must match sender AND (subject-keyword OR body-keyword) to pass.
    Empty list in any field means "match all".
    """

    def __init__(self, rules: dict):
        self.rules = rules
        self._sender_list = [s.lower().strip() for s in rules.get("sender", [])]
        self._subject_kws = [k.lower().strip() for k in rules.get("subject_keywords", []) if k.strip()]
        self._body_kws = [k.lower().strip() for k in rules.get("body_keywords", []) if k.strip()]

    def matches(self, sender: str, subject: str, body: str = "") -> bool:
        """Return True if the email passes all active filter rules."""
        # Sender check
        if self._sender_list:
            if sender.lower() not in self._sender_list:
                return False

        # Subject + body keywords (OR between the two groups)
        subj_lower = subject.lower()
        body_lower = body.lower()
        subj_match = any(kw in subj_lower for kw in self._subject_kws) if self._subject_kws else False
        body_match = any(kw in body_lower for kw in self._body_kws) if self._body_kws else False

        # If neither subject nor body keywords are configured, match all
        if not self._subject_kws and not self._body_kws:
            return True

        return subj_match or body_match

    def describe(self) -> str:
        """Human-readable description of the active rules."""
        parts = []
        if self._sender_list:
            parts.append(f"发件人: {', '.join(self._sender_list)}")
        if self._subject_kws:
            parts.append(f"主题关键字: {', '.join(self._subject_kws)}")
        if self._body_kws:
            parts.append(f"正文关键字: {', '.join(self._body_kws)}")
        return " | ".join(parts) if parts else "无过滤规则"


# =============================================================================
# 7. 状态持久化 — 记录已处理的邮件
# =============================================================================

class SeenTracker:
    """Track processed item IDs to avoid reprocessing."""

    def __init__(self):
        self._path = os.path.join(BASE_DIR, ".edm_agent_seen.json")
        self._seen = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, ensure_ascii=False, indent=2)

    def is_seen(self, item_id: str) -> bool:
        return item_id in self._seen

    def mark_seen(self, item_id: str, result: dict):
        self._seen[item_id] = {
            "processed_at": datetime.now().isoformat(),
            "action": result.get("action"),
            "sn": result.get("sn"),
            "success": result.get("success"),
        }
        self._save()

    def get_last_seen_time(self) -> datetime:
        """Get latest processed time, or 2 hours ago as default.

        On first run, looking back 2 hours ensures recent emails are picked up.
        """
        if not self._seen:
            return datetime.now() - timedelta(hours=2)

        latest = max(
            datetime.fromisoformat(v["processed_at"])
            for v in self._seen.values()
            if isinstance(v, dict) and "processed_at" in v
        )
        return latest


# =========================================================================
# 6. 结果输出
# =========================================================================

def save_result(result: dict):
    """Save processing result to results/ directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"agent_{timestamp}.json"
    filepath = os.path.join(RESULTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"Result saved to {filepath}")
    return filepath


# =========================================================================
# 7. XLSX 自动发现 — 复用 edm_gui.py 逻辑
# =========================================================================

def discover_xlsx(sn: str | None, search_dir: str, filename_hint: str | None = None) -> str | None:
    """Recursively search for xlsx file."""
    if not os.path.isdir(search_dir):
        return None

    # Priority 1: global filename exact match
    if filename_hint:
        hint_lower = filename_hint.lower()
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f.lower() == hint_lower:
                    return os.path.join(root, f)

    # Priority 2: SN folder match
    if not sn or sn == "SN":
        return None
    sn_no_dash = sn.replace("-", "")

    for root, dirs, files in os.walk(search_dir):
        folder_name = os.path.basename(root).lower()
        if sn_no_dash.lower() in folder_name.replace("-", "") or sn.lower() in folder_name:
            xlsx_files = [f for f in files if f.lower().endswith(".xlsx")]
            if xlsx_files:
                return os.path.join(root, xlsx_files[0])

    return None


def extract_xlsx_filename_from_msg(msg_path: str) -> str | None:
    """Extract xlsx filename from MSG body SharePoint URL."""
    try:
        from extract_msg import Message as MsgParser
        from urllib import parse as urllib_parse

        msg = MsgParser(msg_path)
        body = msg.body or ""
        msg.close()

        urls = re.findall(r'https?://[^\s<>"\']+\.xlsx[^\s<>"\']*', body)
        if not urls:
            return None

        after_last_slash = urls[0].rsplit("/", 1)[-1]
        filename = urllib_parse.unquote(after_last_slash.split("?")[0])
        return filename if filename else None
    except Exception:
        return None


def load_xlsx_search_dir() -> str:
    """Load xlsx_search_dir.json or return default."""
    xlsx_config_path = os.path.join(BASE_DIR, "xlsx_search_dir.json")
    default_dir = r"C:\Users\SI-Agent\AgentProject\Microsoft\Azure Service Notifications Collaboration - 2026"
    if os.path.isfile(xlsx_config_path):
        try:
            with open(xlsx_config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("search_directory", default_dir)
        except (json.JSONDecodeError, IOError):
            pass
    return default_dir


# =========================================================================
# 7.5  EWS Streaming Notifications Monitor
# =========================================================================

class EWSStreamingMonitor:
    """Monitor an Outlook folder for new mail using EWS Streaming Notifications.

    Launches a PowerShell subprocess that uses the EWS Managed API DLL to create
    streaming subscriptions. The subprocess outputs JSON events to stdout, one per
    line. This class reads those lines and calls the on_new_mail callback.

    Event JSON format:
        {"type":"connected", "subscription_id":"..."}
        {"type":"newmail", "item_id":"...", "subject":"...", "from":"...", "has_attachments":true}
        {"type":"error", "message":"..."}
        {"type":"disconnected"}
    """

    def __init__(self, ews_client: EWSClient, ps_script: str, on_new_mail=None, batch_size: int = 30):
        self.ews_client = ews_client
        self.ps_script = ps_script
        self.on_new_mail = on_new_mail
        self.batch_size = batch_size
        self._proc = None
        self._thread = None
        self._running = False

    def _build_args(self) -> list[str]:
        """Build the PowerShell command-line arguments."""
        config = load_config()
        ews = config["ews"]

        ps_args = []

        # Add DLL path (prefer net40, fall back to net35)
        dll_path = os.path.join(BASE_DIR, "EWS", "lib", "40", "Microsoft.Exchange.WebServices.dll")
        if not os.path.isfile(dll_path):
            dll_path = os.path.join(BASE_DIR, "EWS", "extracted", "lib", "net35", "Microsoft.Exchange.WebServices.dll")
        if os.path.isfile(dll_path):
            ps_args += ['-DllPath', dll_path]

        ps_args += ['-EwsUrl', ews["url"]]
        ps_args += ['-DomainUser', ews["domain_user"]]
        ps_args += ['-Password', ews["password"]]
        ps_args += ['-FolderName', ews.get("folder_name", "EDM")]

        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", self.ps_script,
        ] + ps_args

    def _read_events(self):
        """Background thread: read JSON lines from PowerShell stdout."""
        try:
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    etype = event.get("type", "")
                    if etype == "connected":
                        logger.info(f"Streaming connected: subscription={event.get('subscription_id')}")
                    elif etype == "newmail":
                        logger.info(f"New mail event: {event.get('subject', '')}")
                        if self.on_new_mail:
                            self.on_new_mail(event)
                    elif etype == "error":
                        logger.error(f"Streaming error: {event.get('message', '')}")
                    elif etype == "disconnected":
                        logger.warning("Streaming disconnected")
                        break
                except json.JSONDecodeError:
                    # Not JSON (PowerShell info output to stderr leaked to stdout)
                    pass
        except Exception as e:
            logger.error(f"Streaming reader error: {e}")
        finally:
            self._running = False

    def start(self):
        """Start the streaming connection."""
        if not os.path.isfile(self.ps_script):
            logger.error(f"Streaming script not found: {self.ps_script}")
            return False

        logger.info(f"Starting EWS Streaming Monitor: {self.ps_script}")
        args = self._build_args()

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as e:
            logger.error(f"Failed to start streaming subprocess: {e}")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._read_events, daemon=True)
        self._thread.start()
        logger.info("Streaming monitor started")
        return True

    def stop(self):
        """Stop the streaming connection."""
        logger.info("Stopping EWS Streaming Monitor...")
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Streaming monitor stopped")

    def is_running(self):
        return self._running and self._proc is not None and self._proc.poll() is None


# =========================================================================
# 8. 主 Agent 循环
# =========================================================================

class EDMAgent:
    """Main agent that orchestrates the pipeline.

    Pipeline:
      1. EWS polls EDM folder → finds new email (with attachments)
      2. Read email body (GetItem) → LLM analyzes intent
      3. Human confirms in GUI
      4. Save the email as .msg to EDM/Temp/
      5. Discover xlsx (from MSG body URL or local search)
      6. Copy xlsx to EDM/Temp/ (edm_process.py reads both from Temp/)
      7. Run edm_process.py → extracts nested EDM template, builds SN folder
      8. Import test list to Unimarketing
    """

    def __init__(self):
        self.ews = EWSClient()
        self.fetcher = EmailFetcher(self.ews)
        self.analyzer = EmailAnalyzer()
        self.executor = EDMExecutor()
        self.tracker = SeenTracker()
        self.notifier = NotificationSender()
        self.notify_enabled = True
        self.edm_output_dir = EDM_OUTPUT_DIR
        self.filter_engine = FilterEngine(FILTER_RULES)
        self.folder_id = None
        self.running = False
        self._history = []
        self._processing = set()  # Track items being processed to prevent duplicates
        self._streaming_monitor = None

        # Streaming script path
        self.ews_streaming_script = os.path.join(BASE_DIR, "ews_streaming.ps1")

        # Confirmation mechanism — background thread waits for GUI user input
        self._confirm_event = None      # threading.Event — set when user responds
        self._confirm_result = None     # True = proceed, False = skip

        # GUI log callback — set by AgentGUI
        self._gui_log_callback = None

    def gui_log(self, step: str, message: str):
        """Log a step-tagged message to the GUI Log tab.

        Called from any background thread; dispatches to GUI thread safely.
        """
        if self._gui_log_callback:
            self._gui_log_callback(step, message)

    def request_confirmation(self, subject: str, analysis: dict, body_preview: str = "", timeout: int = 120) -> bool:
        """Block until user confirms or skips. Called from background thread.

        Shows a dialog request in the GUI; user clicks Confirm / Skip.
        If no GUI callback registered, defaults to skip (safe).
        """
        self._confirm_event = threading.Event()
        self._confirm_result = None

        # Notify GUI to show confirmation dialog
        if hasattr(self, "_on_pending_confirmation"):
            self._on_pending_confirmation(subject, analysis, body_preview)

        # Wait for user response (with timeout for safety)
        confirmed = self._confirm_event.wait(timeout=timeout)
        result = self._confirm_result

        if not confirmed:
            logger.warning(f"Confirmation timed out for: {subject}")
            return False

        return bool(result)

    def set_confirmation(self, proceed: bool):
        """Called from GUI thread when user clicks Confirm / Skip."""
        self._confirm_result = proceed
        if self._confirm_event is not None:
            self._confirm_event.set()

    def initialize(self) -> bool:
        """Find EDM folder and verify connection."""
        logger.info("Initializing EDM Agent...")
        logger.info(f"Mailbox: {self.ews.mailbox}")
        logger.info(f"EWS URL: {self.ews.url}")
        try:
            self.folder_id = self.ews.find_folder(EWS_FOLDER_NAME)
            if self.folder_id:
                logger.info(f"Found EDM folder: {self.folder_id}")
                return True
            else:
                logger.error(f"EDM folder '{EWS_FOLDER_NAME}' not found!")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to EWS: {e}")
            return False

    def scan_and_process(self) -> list[dict]:
        """Scan for new emails, filter, analyze with LLM, and process after confirmation."""
        if not self.folder_id:
            return []

        since = self.tracker.get_last_seen_time()
        logger.info(f"Scanning for new emails since {since.isoformat()}")
        logger.info(f"Filter rules: {self.filter_engine.describe()}")

        new_items = self.ews.find_items_since(self.folder_id, since)
        logger.info(f"Found {len(new_items)} new item(s) with attachments")

        results = []

        for item in new_items:
            item_id = item["item_id"]
            if not item_id:
                continue

            if self.tracker.is_seen(item_id):
                logger.info(f"Skipping already processed: {item_id}")
                continue

            if item_id in self._processing:
                logger.info(f"Skipping currently processing: {item_id}")
                continue

            # Quick filter check (sender + subject — no body yet)
            sender = item.get("sender", "")
            subject = item.get("subject", "")
            if not self.filter_engine.matches(sender, subject):
                logger.info(f"Filter SKIP: [{subject}] from {sender}")
                # Mark as seen so we don't re-check it
                self.tracker.mark_seen(item_id, {"action": "filtered", "success": True})
                continue

            logger.info(f"Processing: [{subject}] from {sender}")
            self._processing.add(item_id)

            # Step 1: Fetch email body for analysis
            info = self.fetcher.fetch_info(item_id)

            # Re-check filter with body text included
            body_text = info.get("body", "")
            if not self.filter_engine.matches(sender, subject, body_text):
                logger.info(f"Filter SKIP (body check): [{subject}] from {sender}")
                self.tracker.mark_seen(item_id, {"action": "filtered", "success": True})
                self._processing.discard(item_id)
                continue

            # Step 2: Analyze with LLM
            # Use the subject from FindItem (always available) and body from GetItem
            analysis_subject = subject or info.get("subject", "")
            analysis = self.analyzer.analyze(
                analysis_subject,
                body_text,
            )

            action_result = {
                "item_id": item_id,
                "subject": item["subject"],
                "sender": item["sender"],
                "received": item["received"],
                "action": analysis["action"],
                "confidence": analysis.get("confidence", 0),
                "reason": analysis.get("reason", ""),
                "sn": analysis.get("sn"),
                "success": False,
            }

            # Step 3: Ask user for confirmation before executing
            if analysis["action"] == "edm_process":
                logger.info(f"LLM suggests EDM process — requesting user confirmation...")

                confirmed = self.request_confirmation(
                    analysis_subject, analysis, info.get("body", "")
                )

                if not confirmed:
                    logger.info(f"User skipped: [{analysis_subject}]")
                    action_result["action"] = "skipped_by_user"
                    action_result["success"] = True
                else:
                    logger.info(f"User confirmed — executing EDM process pipeline...")
                    self._execute_edm_pipeline(item_id, info, analysis, action_result)

            # Track and save
            self.tracker.mark_seen(item_id, action_result)
            self._processing.discard(item_id)
            save_result(action_result)
            self._history.append(action_result)
            results.append(action_result)

            logger.info(f"Completed: [{action_result['action']}] {action_result['subject'][:40]}...")

        return results

    def _cleanup_temp(self):
        """No-op: Temp files (.eml/.msg) are kept for debugging."""
        pass

    def _execute_edm_pipeline(self, item_id: str, info: dict, analysis: dict, action_result: dict):
        """Execute EDM Process + Import Test List pipeline.

        Called after user confirms. Runs in the background agent thread.

        Flow:
          1. Save email as .msg to Temp/
          2. Discover xlsx (from MSG body URL or local search)
          3. Copy xlsx to Temp/ (edm_process.py reads both from Temp/)
          4. Run edm_process.py
          5. Import test list to Unimarketing
          6. Send notification email
        """
        subject = info.get("subject", "EDM_email")
        entry_id = info.get("entry_id", "")

        # Step 1: Save email as .msg to Temp/
        self.gui_log("保存", "开始下载邮件并转换为 .msg...")
        msg_path = self.fetcher.save_as_msg(item_id, subject, entry_id=entry_id)
        if not msg_path or not os.path.isfile(msg_path):
            logger.error("Failed to save email as .msg, cannot proceed")
            self.gui_log("保存", "✗ .msg 转换失败，中止流程")
            action_result["success"] = False
            self._send_notification(subject, action_result)
            return
        self.gui_log("保存", f"✓ .msg 已保存 ({os.path.getsize(msg_path) / 1024:.1f} KB)")

        # Step 2: Find xlsx — extract filename hint from saved MSG body
        filename_hint = extract_xlsx_filename_from_msg(msg_path)
        search_dir = load_xlsx_search_dir()
        sn = analysis.get("sn")

        if filename_hint:
            logger.info(f"Found xlsx filename in MSG body: {filename_hint}")
            self.gui_log("发现", f"从 MSG 正文提取文件名: {filename_hint}")

        xlsx_path = discover_xlsx(sn, search_dir, filename_hint=filename_hint)
        if xlsx_path:
            self.gui_log("发现", f"✓ 找到 xlsx: {os.path.basename(xlsx_path)}")
        else:
            logger.warning("Could not find xlsx file, skipping EDM process")
            self.gui_log("发现", "✗ 未找到 xlsx 文件，跳过处理")
            action_result["success"] = False
            self._send_notification(subject, action_result)
            return

        # Step 3: Copy xlsx to Temp/ so edm_process.py finds it
        xlsx_in_temp = os.path.join(TEMP_DIR, os.path.basename(xlsx_path))
        shutil.copy2(xlsx_path, xlsx_in_temp)
        logger.info(f"Copied xlsx to Temp/: {os.path.basename(xlsx_path)}")

        # Step 4: Run edm_process.py (reads from temp_dir)
        self.gui_log("处理", "运行 EDM Process...")
        process_result = self.executor.process(TEMP_DIR, self.edm_output_dir, gui_log=self.gui_log)
        action_result["process"] = process_result
        if process_result["success"]:
            self.gui_log("处理", f"✓ EDM Process 成功 (SN: {process_result.get('sn', 'N/A')})")
        else:
            err = process_result.get("error", "")
            if err:
                self.gui_log("处理", f"✗ EDM Process 失败: {err}")
            else:
                self.gui_log("处理", f"✗ EDM Process 失败 (返回码: {process_result.get('return_code', '?')})")

        if process_result["success"]:
            # Step 5: Import test list (use SN folder xlsx so skill finds edm_process CSV)
            sn_folder_val = process_result.get("sn_folder")
            if sn_folder_val:
                # Find the xlsx in the SN folder (copied by edm_process)
                sn_folder_xlsx = None
                for f in os.listdir(sn_folder_val):
                    if f.lower().endswith(".xlsx"):
                        sn_folder_xlsx = os.path.join(sn_folder_val, f)
                        break
                xlsx_for_import = sn_folder_xlsx or xlsx_path
            else:
                xlsx_for_import = xlsx_path

            self.gui_log("导入", "正在导入测试列表到 Unimarketing...")
            sn_val = process_result.get("sn") or sn or ""
            import_result = self.executor.import_test_list(xlsx_for_import, sn_val)
            action_result["import"] = import_result
            action_result["import_success"] = import_result.get("success", False)
            if import_result.get("success"):
                self.gui_log("导入", f"✓ 导入成功 (List ID: {import_result.get('list_id', 'N/A')})")
            else:
                err = import_result.get("error", "")
                if err:
                    self.gui_log("导入", f"✗ 导入失败: {err}")
                else:
                    self.gui_log("导入", f"✗ 导入失败 (返回码: {import_result.get('return_code', '?')})")
        else:
            action_result["import_success"] = False

        action_result["process_success"] = process_result["success"]
        action_result["success"] = (
            process_result["success"] and action_result["import_success"]
        )

        # Step 6: Send notification email
        self.gui_log("通知", "发送处理完成通知...")
        self._send_notification(subject, action_result)

    def _send_notification(self, subject: str, result: dict):
        """Send notification email after EDM pipeline completes."""
        if not self.notify_enabled:
            logger.debug("Notification disabled, skipping")
            self.gui_log("通知", "通知已禁用，跳过发送")
            return
        try:
            sn = result.get("sn", "unknown") or "unknown"
            overall = "成功" if result.get("success") else "失败"
            notif_subject = f"[EDM Agent] {sn} 处理完成 - {overall}"
            notif_body = self.notifier.build_result_html(subject, result)
            ok = self.notifier.send(notif_subject, notif_body)
            if ok:
                self.gui_log("通知", "✓ 通知邮件发送成功")
            else:
                self.gui_log("通知", "✗ 通知邮件发送失败")
        except Exception as e:
            logger.error(f"Notification failed: {e}")
            self.gui_log("通知", f"✗ 通知发送异常: {e}")

    def _on_new_mail_streaming(self, event: dict):
        """Callback from EWSStreamingMonitor when a new mail event arrives.

        Starts a background thread to process the email to avoid blocking the
        streaming reader thread.
        """
        item_id = event.get("item_id", "")
        logger.info(f"Streaming event: new mail {item_id[:30]}...")

        # Avoid duplicate processing
        if item_id in self._processing:
            logger.info(f"Already processing: {item_id}")
            return

        # Start processing in a new thread
        t = threading.Thread(target=self._process_single_streaming, args=(event,), daemon=True)
        t.start()

    def _process_single_streaming(self, event: dict):
        """Process a single streaming event through the pipeline."""
        item_id = event.get("item_id", "")
        subject = event.get("subject", "")
        sender = event.get("from", event.get("sender", ""))
        has_attachments = event.get("has_attachments", False)

        logger.info(f"Processing streaming event: [{subject}] from {sender}")
        self.gui_log("监听", f"收到新邮件: {subject}")

        # Skip if already processed
        if self.tracker.is_seen(item_id):
            logger.info(f"Already processed: {item_id}")
            return

        # Quick skip: no attachments
        if not has_attachments:
            logger.info(f"SKIP (no attachments): [{subject}]")
            self.gui_log("过滤", f"✗ 无附件，跳过: {subject}")
            self.tracker.mark_seen(item_id, {"action": "filtered", "success": True})
            return

        self._processing.add(item_id)

        # Quick filter check (sender + subject — no body yet)
        if not self.filter_engine.matches(sender, subject):
            logger.info(f"Filter SKIP: [{subject}] from {sender}")
            self.gui_log("过滤", f"✗ 规则不匹配: {subject} (发件人: {sender})")
            self.tracker.mark_seen(item_id, {"action": "filtered", "success": True})
            self._processing.discard(item_id)
            return

        self.gui_log("过滤", f"✓ 规则匹配，进入分析 → {subject}")
        logger.info(f"Processing: [{subject}] from {sender}")

        # Step 1: Fetch email body for analysis
        info = self.fetcher.fetch_info(item_id)
        body_text = info.get("body", "")
        self.gui_log("读取", "邮件正文获取完成")

        # Re-check filter with body text included
        if not self.filter_engine.matches(sender, subject, body_text):
            logger.info(f"Filter SKIP (body check): [{subject}] from {sender}")
            self.gui_log("过滤", f"✗ 正文过滤不通过: {subject}")
            self.tracker.mark_seen(item_id, {"action": "filtered", "success": True})
            self._processing.discard(item_id)
            return

        # Step 2: Analyze with LLM
        analysis_subject = subject or info.get("subject", "")
        self.gui_log("分析", "LLM 正在分析邮件需求...")
        analysis = self.analyzer.analyze(analysis_subject, body_text)
        self.gui_log("分析", f"分析完成: action={analysis['action']}, 置信度={analysis.get('confidence', 0)}%, SN={analysis.get('sn') or '无'}")

        action_result = {
            "item_id": item_id,
            "subject": subject,
            "sender": sender,
            "received": event.get("datetime_received", ""),
            "action": analysis["action"],
            "confidence": analysis.get("confidence", 0),
            "reason": analysis.get("reason", ""),
            "sn": analysis.get("sn"),
            "success": False,
        }

        # Step 3: Ask user for confirmation before executing
        if analysis["action"] == "edm_process":
            logger.info(f"LLM suggests EDM process — requesting user confirmation...")
            self.gui_log("确认", "等待用户确认...")

            confirmed = self.request_confirmation(
                analysis_subject, analysis, info.get("body", "")
            )

            if not confirmed:
                logger.info(f"User skipped: [{analysis_subject}]")
                self.gui_log("确认", "✗ 用户跳过")
                action_result["action"] = "skipped_by_user"
                action_result["success"] = True
            else:
                logger.info(f"User confirmed — executing EDM process pipeline...")
                self.gui_log("确认", "✓ 用户确认，开始执行流程")
                self._execute_edm_pipeline(item_id, info, analysis, action_result)

        # Track and save
        self.tracker.mark_seen(item_id, action_result)
        self._processing.discard(item_id)
        save_result(action_result)
        self._history.append(action_result)

        self.gui_log("完成", f"处理完成 [{action_result['action']}]: {subject}")
        logger.info(f"Completed: [{action_result['action']}] {action_result['subject'][:40]}...")

        # Notify GUI
        if hasattr(self, "_on_scan_complete"):
            self._on_scan_complete([action_result])

        # Clean up Temp directory
        self._cleanup_temp()

    def run_loop(self, interval: int = None):
        """Main monitoring loop using EWS Streaming Notifications.

        Falls back to polling if streaming script not available or streaming dies.
        When streaming dies (max reconnects exhausted), automatically restarts
        streaming up to 3 times before falling back to polling.
        """
        if interval is None:
            interval = POLL_INTERVAL

        self.running = True

        # Try streaming first
        streaming_available = os.path.isfile(self.ews_streaming_script)
        if streaming_available:
            max_streaming_restarts = 3
            for restart in range(max_streaming_restarts):
                logger.info(f"Starting EWS Streaming Notifications (attempt {restart + 1})...")
                self._streaming_monitor = EWSStreamingMonitor(
                    self.ews, self.ews_streaming_script, self._on_new_mail_streaming
                )
                if not self._streaming_monitor.start():
                    logger.warning("Streaming start failed")
                    break

                logger.info("Streaming monitor active, waiting for events...")
                # Wait until stop() is called or streaming process dies
                while self.running:
                    if not self._streaming_monitor.is_running():
                        logger.warning(
                            f"Streaming process died (restart {restart + 1}/{max_streaming_restarts})"
                        )
                        break
                    time.sleep(2)

                if self._streaming_monitor is not None:
                    self._streaming_monitor.stop()

                if not self.running:
                    return  # User stopped

                if restart + 1 >= max_streaming_restarts:
                    logger.warning(
                        "Streaming died after %d restarts, falling back to polling",
                        max_streaming_restarts,
                    )
                    break
                else:
                    logger.info("Restarting streaming in 10s...")
                    time.sleep(10)

        # Fallback: polling loop
        logger.info(f"Starting polling loop (interval={interval}s)")
        while self.running:
            try:
                results = self.scan_and_process()
                if results:
                    logger.info(f"Processed {len(results)} email(s) this round")
                else:
                    logger.debug("No new emails")

                if hasattr(self, "_on_scan_complete"):
                    self._on_scan_complete(results)

            except Exception as e:
                logger.error(f"Error in scan loop: {e}", exc_info=True)

            time.sleep(interval)

    def stop(self):
        self.running = False
        if self._streaming_monitor:
            self._streaming_monitor.stop()
            self._streaming_monitor = None


# =========================================================================
# 9. GUI — 桌面小工具
# =========================================================================

class AgentGUI:
    """Simple tkinter GUI for the EDM Auto Agent."""

    def __init__(self, agent: EDMAgent):
        self.agent = agent
        self.root = tk.Tk()
        self.root.title("EDM Auto Agent")
        self.root.geometry("950x600")
        self.root.minsize(750, 450)

        self._build_ui()
        self._update_status("就绪", "灰色")

        # Wire up confirmation callback
        self.agent._on_pending_confirmation = self._show_confirmation

    def _show_confirmation(self, subject: str, analysis: dict, body_preview: str):
        """Show a custom confirmation dialog with analysis results and email body preview.

        Blocks (modal) until user clicks Confirm or Skip.
        """
        sn = analysis.get("sn", "") or "未提取到"
        reason = analysis.get("reason", "")
        confidence = analysis.get("confidence", 0)
        model = analysis.get("_model", "unknown")
        is_fallback = analysis.get("_fallback", False)
        elapsed = analysis.get("_elapsed", 0)

        # Truncate body preview
        preview_text = body_preview.strip()[:1500]
        if len(body_preview.strip()) > 1500:
            preview_text += "\n...（已截断）"

        self._gui_log("确认", f"等待确认: [{subject}]")
        self._update_status("等待确认...", "黄色")

        # Build custom dialog
        win = tk.Toplevel(self.root)
        win.title("确认执行 EDM 处理")
        win.geometry("780x560")
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()
        win.focus_set()

        result = [None]

        # ── Action icon & method badge ──
        top_frame = ttk.Frame(win, padding=(12, 12, 12, 6))
        top_frame.pack(fill="x")

        action = analysis.get("action", "unknown")
        action_icon = {"edm_process": "✓", "ignore": "✗", "error": "!"}.get(action, "?")
        action_color = {"edm_process": "#22c55e", "ignore": "#ef4444", "error": "#eab308"}.get(action, "#888")

        method_label = "关键词匹配 (Fallback)" if is_fallback else "LLM 语义分析"
        method_color = "#eab308" if is_fallback else "#3b82f6"

        ttk.Label(top_frame, text=f"主题: {subject}",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        # ── Analysis result table ──
        table_frame = ttk.Frame(top_frame)
        table_frame.pack(fill="x")

        # Two column layout: left label + value, right method badge
        left_frame = ttk.Frame(table_frame)
        left_frame.pack(side="left", fill="x", expand=True)

        right_frame = ttk.Frame(table_frame)
        right_frame.pack(side="right", padx=(0, 0))

        # Method badge (top right)
        badge = tk.Label(right_frame, text=f"[{method_label}]",
                         font=("Microsoft YaHei UI", 9, "bold"),
                         foreground=method_color, background="#f0f0f0",
                         padx=8, pady=3)
        badge.pack(anchor="ne", pady=(0, 4))

        # Table rows
        table_data = [
            ("模型", model, "value"),
            ("分析方式", method_label, "method" if is_fallback else "llm"),
            ("动作", f"{action_icon} {action}", "value"),
            ("置信度", f"{confidence}%", "confidence"),
            ("SN", sn, "value"),
            ("响应时间", f"{elapsed}s" if elapsed else "N/A", "value"),
        ]

        row_height = 22
        table_bg = "#f8f9fa"
        border = ttk.Separator(top_frame, orient="horizontal")

        for idx, (label, value, vtype) in enumerate(table_data):
            row_frame = ttk.Frame(left_frame)
            row_frame.pack(fill="x", pady=1)

            label_color = "#333"
            value_color = "#111"
            value_font = ("Microsoft YaHei UI", 9)

            if label == "置信度":
                if confidence >= 90:
                    value_color = "#22c55e"
                elif confidence >= 70:
                    value_color = "#3b82f6"
                else:
                    value_color = "#eab308"

            ttk.Label(row_frame, text=label, width=8, anchor="w",
                      font=("Microsoft YaHei UI", 9), foreground=label_color).pack(side="left", padx=(4, 8))

            # Wrap reason text in a separate scrollable area if it's long
            ttk.Label(row_frame, text=value, anchor="w",
                      font=value_font, foreground=value_color, wraplength=500).pack(side="left", fill="x", expand=True)

        # Separator
        ttk.Separator(top_frame, orient="horizontal").pack(fill="x", pady=(6, 0))

        # ── Reason section ──
        reason_frame = ttk.Frame(top_frame)
        reason_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(reason_frame, text="判断理由:", font=("Microsoft YaHei UI", 9, "bold"),
                  foreground="#333").pack(anchor="w")

        reason_text = tk.Text(reason_frame, height=3, wrap="word",
                              font=("Microsoft YaHei UI", 9), bg="#f5f5f5", state="disabled", padx=6)
        reason_text.pack(fill="x")
        reason_text.config(state="normal")
        reason_text.insert("1.0", reason)
        reason_text.config(state="disabled")

        # ── Body preview ──
        ttk.Label(win, text="邮件正文预览:", font=("Microsoft YaHei UI", 9, "bold"),
                  foreground="#333").pack(anchor="nw", padx=16, pady=(8, 0))

        body_frame = ttk.Frame(win)
        body_frame.pack(fill="both", expand=True, padx=12, pady=4)

        body_scroll = ttk.Scrollbar(body_frame, orient="vertical")
        body_scroll.pack(side="right", fill="y")

        body_text = tk.Text(body_frame, height=10, wrap="word", font=("Consolas", 9),
                            bg="#f5f5f5", yscrollcommand=body_scroll.set, state="disabled")
        body_text.pack(fill="both", expand=True)
        body_scroll.config(command=body_text.yview)

        body_text.config(state="normal")
        body_text.insert("1.0", preview_text if preview_text else "（无正文内容）")
        body_text.config(state="disabled")

        # Button frame at bottom
        btn_frame = ttk.Frame(win, padding=(12, 10, 12, 14))
        btn_frame.pack(fill="x")

        # Spacer to push buttons right
        btn_frame.columnconfigure(0, weight=1)

        def _skip():
            result[0] = False
            win.destroy()

        def _confirm():
            result[0] = True
            win.destroy()

        ttk.Button(btn_frame, text="跳过", command=_skip, width=10).grid(row=0, column=1, padx=(10, 8))
        ttk.Button(btn_frame, text="确认执行", command=_confirm, width=10, style="Action.TButton")\
            .grid(row=0, column=2, padx=(0, 8))

        self.root.wait_window(win)

        if result[0]:
            self._gui_log("确认", f"用户确认: [{subject}]")
            self._update_status("处理中...", "蓝色")
        else:
            self._gui_log("确认", f"用户跳过: [{subject}]")
            self._update_status("监听中", "绿色")

        self.agent.set_confirmation(bool(result[0]))

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Status.TLabel", font=("Consolas", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(8, 4))
        style.configure("Action.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(12, 6))

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        # Title + Status
        top_frame = ttk.Frame(main)
        top_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(top_frame, text="EDM Auto Agent", style="Title.TLabel").pack(side="left")

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(
            top_frame, textvariable=self.status_var, style="Status.TLabel"
        )
        self.status_label.pack(side="right")

        # Info line
        info_frame = ttk.Frame(main)
        info_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(info_frame, text=f"Mailbox: {EWS_MAILBOX}  |  Folder: {EWS_FOLDER_NAME}",
                  style="Status.TLabel").pack(side="left")

        # Control buttons
        btn_frame = ttk.Frame(main, padding=(0, 8))
        btn_frame.pack(fill="x")

        self.start_btn = ttk.Button(
            btn_frame, text="Start", command=self._start, style="Action.TButton"
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._stop, state="disabled", style="Action.TButton"
        )
        self.stop_btn.pack(side="left", padx=(0, 8))

        # Notification toggle (default off)
        self.notify_var = tk.BooleanVar(value=False)
        self.agent.notify_enabled = False
        tk.Checkbutton(
            btn_frame, text="处理完成邮件通知",
            variable=self.notify_var,
            command=self._on_notify_toggle,
        ).pack(side="left", padx=(16, 0))

        ttk.Button(
            btn_frame, text="测试通知",
            command=self._test_notification, width=10,
        ).pack(side="left", padx=(8, 0))

        # Notebook: History + Log
        notebook = ttk.Notebook(main)
        notebook.pack(fill="both", expand=True, pady=(8, 0))

        # Tab 1: Processing History
        hist_tab = ttk.Frame(notebook, padding=8)
        notebook.add(hist_tab, text="  History  ")

        columns = ("Time", "Subject", "Sender", "SN", "Action", "Status")
        self.history_tree = ttk.Treeview(hist_tab, columns=columns, show="headings", height=15)

        self.history_tree.heading("Time", text="Time")
        self.history_tree.heading("Subject", text="Subject")
        self.history_tree.heading("Sender", text="Sender")
        self.history_tree.heading("SN", text="SN")
        self.history_tree.heading("Action", text="Action")
        self.history_tree.heading("Status", text="Status")

        self.history_tree.column("Time", width=150)
        self.history_tree.column("Subject", width=420)
        self.history_tree.column("Sender", width=180)
        self.history_tree.column("SN", width=80)
        self.history_tree.column("Action", width=120)
        self.history_tree.column("Status", width=80)

        scrollbar = ttk.Scrollbar(hist_tab, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Tab 2: Log
        log_tab = ttk.Frame(notebook, padding=8)
        notebook.add(log_tab, text="  Log  ")

        self.log_text = tk.Text(
            log_tab, wrap="word", state="disabled",
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
        )
        self.log_text.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")

        # Color tags for step labels
        self.log_text.tag_configure("step_listen", foreground="#3b82f6", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_filter", foreground="#eab308", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_fetch", foreground="#a855f7", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_analyze", foreground="#06b6d4", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_confirm", foreground="#f97316", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_save", foreground="#ec4899", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_discover", foreground="#84cc16", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_process", foreground="#22c55e", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_import", foreground="#f59e0b", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_notify", foreground="#6366f1", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_complete", foreground="#22c55e", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_system", foreground="#9ca3af", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("step_tag_msg", foreground="#d4d4d4", font=("Consolas", 9))
        # Non-bold variants for message body (same color)
        self.log_text.tag_configure("msg_listen", foreground="#3b82f6", font=("Consolas", 9))
        self.log_text.tag_configure("msg_filter", foreground="#eab308", font=("Consolas", 9))
        self.log_text.tag_configure("msg_fetch", foreground="#a855f7", font=("Consolas", 9))
        self.log_text.tag_configure("msg_analyze", foreground="#06b6d4", font=("Consolas", 9))
        self.log_text.tag_configure("msg_confirm", foreground="#f97316", font=("Consolas", 9))
        self.log_text.tag_configure("msg_save", foreground="#ec4899", font=("Consolas", 9))
        self.log_text.tag_configure("msg_discover", foreground="#84cc16", font=("Consolas", 9))
        self.log_text.tag_configure("msg_process", foreground="#22c55e", font=("Consolas", 9))
        self.log_text.tag_configure("msg_import", foreground="#f59e0b", font=("Consolas", 9))
        self.log_text.tag_configure("msg_notify", foreground="#6366f1", font=("Consolas", 9))
        self.log_text.tag_configure("msg_complete", foreground="#22c55e", font=("Consolas", 9))
        self.log_text.tag_configure("msg_system",  foreground="#9ca3af", font=("Consolas", 9))
        self.log_text.tag_configure("msg_tag_msg", foreground="#d4d4d4", font=("Consolas", 9))
        self.log_text.tag_configure("log_success", foreground="#22c55e", font=("Consolas", 9))
        self.log_text.tag_configure("log_error",   foreground="#ef4444", font=("Consolas", 9))
        self.log_text.tag_configure("log_warning", foreground="#eab308", font=("Consolas", 9))

        # Wire up the GUI log callback
        self.agent._gui_log_callback = self._gui_log

        # Tab 3: Settings
        settings_tab = ttk.Frame(notebook, padding=16)
        notebook.add(settings_tab, text="  Settings  ")

        ttk.Label(settings_tab, text="路径配置", font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        # EDM Output Directory
        edm_dir_frame = ttk.Frame(settings_tab)
        edm_dir_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(edm_dir_frame, text="EDM 输出目录:").pack(side="left", padx=(0, 8))
        self.edm_dir_var = tk.StringVar(value=self.agent.edm_output_dir)
        ttk.Entry(edm_dir_frame, textvariable=self.edm_dir_var, width=60).pack(side="left", padx=(0, 8))
        ttk.Button(edm_dir_frame, text="浏览...", command=self._browse_edm_dir).pack(side="left")

        # Temp Directory
        temp_dir_frame = ttk.Frame(settings_tab)
        temp_dir_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(temp_dir_frame, text="Temp 目录:").pack(side="left", padx=(0, 8))
        self.temp_dir_var = tk.StringVar(value=TEMP_DIR)
        ttk.Entry(temp_dir_frame, textvariable=self.temp_dir_var, width=60).pack(side="left", padx=(0, 8))
        ttk.Button(temp_dir_frame, text="浏览...", command=self._browse_temp_dir).pack(side="left")

        # ── Monitor Filter Rules ──
        ttk.Separator(settings_tab, orient="horizontal").pack(fill="x", padx=8, pady=12)
        ttk.Label(settings_tab, text="监听过滤规则", font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        rules = self.agent.filter_engine.rules

        # Sender list
        sender_frame = ttk.Frame(settings_tab)
        sender_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(sender_frame, text="发件人:").pack(side="left", padx=(0, 8))
        self.sender_var = tk.StringVar(value=", ".join(rules.get("sender", [])))
        ttk.Entry(sender_frame, textvariable=self.sender_var, width=55).pack(side="left", padx=(0, 8))
        ttk.Label(sender_frame, text="逗号分隔", foreground="#888", font=("Microsoft YaHei UI", 8)).pack(side="left")

        # Subject keywords
        subj_frame = ttk.Frame(settings_tab)
        subj_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(subj_frame, text="主题关键字:").pack(side="left", padx=(0, 8))
        self.subject_kw_var = tk.StringVar(value=", ".join(rules.get("subject_keywords", [])))
        ttk.Entry(subj_frame, textvariable=self.subject_kw_var, width=55).pack(side="left", padx=(0, 8))
        ttk.Label(subj_frame, text="匹配任一即可", foreground="#888", font=("Microsoft YaHei UI", 8)).pack(side="left")

        # Body keywords
        body_frame = ttk.Frame(settings_tab)
        body_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(body_frame, text="正文关键字:").pack(side="left", padx=(0, 8))
        self.body_kw_var = tk.StringVar(value=", ".join(rules.get("body_keywords", [])))
        ttk.Entry(body_frame, textvariable=self.body_kw_var, width=55).pack(side="left", padx=(0, 8))
        ttk.Label(body_frame, text="匹配任一即可", foreground="#888", font=("Microsoft YaHei UI", 8)).pack(side="left")

        # Current rule description
        self.filter_desc_var = tk.StringVar(value=f"当前规则: {self.agent.filter_engine.describe()}")
        ttk.Label(settings_tab, textvariable=self.filter_desc_var,
                  foreground="#3b82f6", font=("Consolas", 9), wraplength=700).pack(pady=(4, 0))

        # Save button
        ttk.Button(
            settings_tab, text="保存设置", command=self._save_settings, style="Action.TButton", width=15
        ).pack(pady=(16, 0))

        # Info note
        ttk.Label(
            settings_tab,
            text="修改后需要重启 Agent 生效",
            foreground="#888", font=("Microsoft YaHei UI", 8),
        ).pack(pady=(12, 0))

        # Setup agent callback
        self.agent._on_scan_complete = self._on_scan_complete

    def _update_status(self, text: str, color: str = "灰色"):
        color_map = {
            "绿色": "#22c55e",
            "红色": "#ef4444",
            "黄色": "#eab308",
            "灰色": "#9ca3af",
            "蓝色": "#3b82f6",
        }
        self.status_var.set(text)
        c = color_map.get(color, "#9ca3af")
        self.status_label.config(foreground=c)

    def _log(self, message: str):
        self.log_text.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _gui_log(self, step: str, message: str):
        """Append a step-tagged log entry with colored step label."""
        STEP_TAG_MAP = {
            "监听": "step_listen",
            "过滤": "step_filter",
            "读取": "step_fetch",
            "分析": "step_analyze",
            "确认": "step_confirm",
            "保存": "step_save",
            "发现": "step_discover",
            "处理": "step_process",
            "导入": "step_import",
            "通知": "step_notify",
            "完成": "step_complete",
            "系统": "step_system",
        }
        tag_name = STEP_TAG_MAP.get(step, "step_tag_msg")
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{step}] {message}\n"

        self.root.after(0, self._gui_log_append, line, tag_name)

    def _gui_log_append(self, line: str, tag_name: str):
        """Thread-safe append to log Text widget with full-line coloring.

        Uses insert(index, text, *tags) to avoid +Nc offset calculations.
        Rules:
          - Lines with ✓ → entire line green (success)
          - Lines with ✗ → entire line red  (error)
          - Otherwise → timestamp default, step label bold colored, message normal colored
        """
        self.log_text.config(state="normal")

        has_success = "✓" in line
        has_error = "✗" in line

        if has_success:
            self.log_text.insert("end", line, "log_success")
        elif has_error:
            self.log_text.insert("end", line, "log_error")
        else:
            step_start = line.find("[", 11)
            if step_start >= 0:
                step_end = line.find("]", step_start)
                if step_end > step_start:
                    self.log_text.insert("end", line[:step_start])
                    self.log_text.insert("end", line[step_start:step_end + 1], tag_name)
                    msg_tag = tag_name.replace("step_", "msg_", 1)
                    self.log_text.insert("end", line[step_end + 1:], msg_tag)
                else:
                    self.log_text.insert("end", line)
            else:
                self.log_text.insert("end", line)

        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _start(self):
        if not self.agent.folder_id:
            if not self.agent.initialize():
                messagebox.showerror("Error", "Cannot connect to EWS. Check network and EDM folder.")
                return

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self._update_status("Running", "绿色")
        self._gui_log("系统", "Agent started, listening to EDM folder...")

        thread = threading.Thread(
            target=self.agent.run_loop, daemon=True
        )
        thread.start()

    def _stop(self):
        self.agent.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._update_status("Stopped", "灰色")
        self._gui_log("系统", "Agent stopped")

    def _on_notify_toggle(self):
        self.agent.notify_enabled = self.notify_var.get()
        self._gui_log("通知", f"邮件通知 {'已开启 ✓' if self.agent.notify_enabled else '已关闭'}")

    def _test_notification(self):
        """Send a test notification email."""
        self._gui_log("通知", "发送测试通知...")
        test_subject = "[EDM Agent] 测试通知"
        test_body = "<html><body style='font-family:Microsoft YaHei UI, monospace; padding:20px;'>"
        test_body += "<h2 style='color:#22c55e;'>测试通知 — EDM Agent 邮件发送正常</h2>"
        test_body += f"<p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        test_body += "<p>如果您收到此邮件，说明 EDM Agent 邮件通知功能工作正常。</p>"
        test_body += "</body></html>"

        def _do():
            ok = self.agent.notifier.send(test_subject, test_body)
            self.root.after(0, lambda: self._gui_log("通知",
                "✓ 测试通知发送成功" if ok else "✗ 测试通知发送失败"
            ))

        thread = threading.Thread(target=_do, daemon=True)
        thread.start()

    def _browse_edm_dir(self):
        folder = filedialog.askdirectory(title="选择 EDM 输出目录")
        if folder:
            self.edm_dir_var.set(folder)

    def _browse_temp_dir(self):
        folder = filedialog.askdirectory(title="选择 Temp 目录")
        if folder:
            self.temp_dir_var.set(folder)

    def _save_settings(self):
        """Save EDM output dir, temp dir, and filter rules to config file."""
        edm_dir = self.edm_dir_var.get().strip()
        temp_dir = self.temp_dir_var.get().strip()

        if not edm_dir:
            messagebox.showwarning("警告", "EDM 输出目录不能为空")
            return
        if not temp_dir:
            messagebox.showwarning("警告", "Temp 目录不能为空")
            return

        os.makedirs(temp_dir, exist_ok=True)

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}

        cfg["output_base"] = edm_dir
        cfg["temp_dir"] = temp_dir

        # Parse filter rules from text fields
        def _split_list(text: str) -> list:
            return [s.strip() for s in text.split(",") if s.strip()]

        sender_text = self.sender_var.get()
        subject_kw_text = self.subject_kw_var.get()
        body_kw_text = self.body_kw_var.get()

        cfg["filter_rules"] = {
            "sender": _split_list(sender_text),
            "subject_keywords": _split_list(subject_kw_text),
            "body_keywords": _split_list(body_kw_text),
        }

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        # Update the agent's filter engine in-memory
        self.agent.filter_engine = FilterEngine(cfg["filter_rules"])
        self.filter_desc_var.set(f"当前规则: {self.agent.filter_engine.describe()}")

        self._gui_log("系统", f"设置已保存: EDM输出={edm_dir}, Temp={temp_dir}")
        self._gui_log("系统", f"过滤规则: {self.agent.filter_engine.describe()}")
        messagebox.showinfo("成功",
            f"设置已保存\n\n"
            f"EDM 输出目录: {edm_dir}\n"
            f"Temp 目录: {temp_dir}\n\n"
            f"监听过滤规则:\n"
            f"  发件人: {sender_text or '(无限制)'}\n"
            f"  主题关键字: {subject_kw_text or '(无限制)'}\n"
            f"  正文关键字: {body_kw_text or '(无限制)'}\n\n"
            f"过滤规则已即时生效，路径修改需重启 Agent。"
        )

    def _on_scan_complete(self, results: list[dict]):
        """Update GUI table after a scan cycle."""
        def _update():
            for r in results:
                received = r.get("received", "")
                if received:
                    try:
                        dt = datetime.fromisoformat(received)
                        received = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        pass

                subject = r.get("subject", "") or ""
                sender = (r.get("sender", "") or "")[:30]
                sn = r.get("sn", "") or ""
                action = r.get("action", "")

                success = r.get("success", False)
                status = "OK" if success else "FAIL"

                self.history_tree.insert("", "end", values=(
                    received, subject, sender, sn, action, status
                ))

        self.root.after(0, _update)

    def run(self):
        self.root.mainloop()


# =========================================================================
# Entry point
# =========================================================================

def main():
    logger.info("=" * 60)
    logger.info("EDM Auto Agent 启动")
    logger.info(f"Config: {CONFIG_FILE}")
    logger.info(f"LLM Config: {LLM_CONFIG_FILE}")
    logger.info(f"LLM Model: {llm_config['model']} (timeout={llm_config.get('timeout', 30)}s)")
    logger.info(f"Mailbox: {EWS_MAILBOX}")
    logger.info(f"Folder: {EWS_FOLDER_NAME}")
    logger.info(f"Log: {LOG_FILE}")
    logger.info("=" * 60)

    agent = EDMAgent()

    # Initialize EWS connection
    if not agent.initialize():
        print("Error: Cannot connect to EWS. Please check network and EDM folder.")
        sys.exit(1)

    # Launch GUI
    gui = AgentGUI(agent)
    gui.run()


if __name__ == "__main__":
    main()
