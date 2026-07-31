"""TFS (Azure DevOps) module - REST API + webhook handler + TFS 2010 Request."""
import os
import json
import re
import base64
import html
import subprocess
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, g, current_app
from routes.auth import require_auth
from utils import task_queue

logger = logging.getLogger(__name__)

tfs_bp = Blueprint('tfs', __name__, url_prefix='/api/tfs')

# In-memory webhook log
_webhook_log = []
MAX_WEBHOOK_LOG = 100

# ─── TFS 2010 Request PowerShell Path ─────────────────────────

def _get_tfs_request_ps1():
    project_root = current_app.config.get('PROJECT_ROOT', os.getcwd())
    return os.path.join(project_root, "TfsRequestPS", "TfsRequest.ps1")


def _get_project_root():
    return current_app.config.get('PROJECT_ROOT', os.getcwd())


def _load_config():
    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_tfs_headers():
    """Build Azure DevOps auth headers from config."""
    import base64
    config = _load_config()
    tfs = config.get("tfs", {})
    pat = tfs.get("pat", "")
    if pat:
        credentials = base64.b64encode(f":{pat}".encode()).decode()
        return {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def _tfs_base_url():
    config = _load_config()
    tfs = config.get("tfs", {})
    org = tfs.get("organization", "21vianet-azure")
    return f"https://dev.azure.com/{org}"


def _tfs_project():
    config = _load_config()
    return config.get("tfs", {}).get("project", "21ViaNet-Project")


# ─── Webhook Handler ──────────────────────────────────────────

@tfs_bp.route('/webhook', methods=['POST'])
def webhook():
    """POST /api/tfs/webhook - Receive Azure DevOps webhook events.

    This endpoint is NOT auth-protected - it's called by Azure DevOps.
    Optionally check webhook secret if configured.
    """
    # Optional secret check
    config = _load_config()
    secret = config.get("webhook", {}).get("secret", "")
    if secret:
        provided = request.headers.get('X-Webhook-Secret', '')
        if provided != secret:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = data.get("eventType", "")
    resource = data.get("resource", {})
    fields = resource.get("fields", {})

    # Extract work item info
    work_item = {
        "id": resource.get("id"),
        "rev": resource.get("rev"),
        "event_type": event_type,
        "work_item_type": fields.get("System.WorkItemType", ""),
        "title": fields.get("System.Title", ""),
        "description": fields.get("System.Description", ""),
        "assigned_to": fields.get("System.AssignedTo", {}).get("displayName", "") if isinstance(fields.get("System.AssignedTo"), dict) else str(fields.get("System.AssignedTo", "")),
        "team_project": fields.get("System.TeamProject", ""),
        "url": resource.get("url", ""),
        "state": fields.get("System.State", ""),
        "received_at": datetime.now().isoformat(),
    }

    # Add to log
    _webhook_log.append(work_item)
    if len(_webhook_log) > MAX_WEBHOOK_LOG:
        _webhook_log.pop(0)

    logger.info(f"TFS Webhook: {event_type} - WI#{work_item['id']} {work_item['title']}")

    # TODO: Add auto-processing logic here based on event_type
    # e.g., auto-create ICM incident for certain Request types

    return jsonify({"ok": True, "work_item_id": work_item.get("id")})


# ─── Query Work Item ──────────────────────────────────────────

@tfs_bp.route('/workitem/<int:work_item_id>', methods=['GET'])
@require_auth
def get_workitem(work_item_id: int):
    """GET /api/tfs/workitem/<id> - Get work item details via REST API."""
    import requests

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0&$expand=fields"

    try:
        resp = requests.get(url, headers=_get_tfs_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return jsonify({"ok": True, "data": data})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@tfs_bp.route('/workitem/<int:work_item_id>/update', methods=['POST'])
@require_auth
def update_workitem(work_item_id: int):
    """PATCH work item fields via REST API.

    Body: {"fields": {"System.Description": "new desc", ...}}
    """
    import requests

    data = request.get_json()
    if not data or "fields" not in data:
        return jsonify({"error": "Body must contain 'fields' object"}), 400

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0"

    # Azure DevOps PATCH uses application/json-patch+content-type
    fields = data["fields"]
    patches = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items()]

    try:
        resp = requests.patch(
            url,
            headers={"Authorization": _get_tfs_headers().get("Authorization", ""),
                      "Content-Type": "application/json-patch+json"},
            json=patches,
            timeout=30,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "data": resp.json()})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Update Labor Time ────────────────────────────────────────

@tfs_bp.route('/update-labor', methods=['POST'])
@require_auth
def update_labor():
    """POST /api/tfs/update-labor - Update Labor Time field on a work item.

    Body: {"work_item_id": 12345, "labor_time": 8.0}
    """
    import requests

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    work_item_id = data.get("work_item_id")
    labor_time = data.get("labor_time")

    if not work_item_id or labor_time is None:
        return jsonify({"error": "work_item_id and labor_time required"}), 400

    project = _tfs_project()
    base = _tfs_base_url()
    url = f"{base}/{project}/_apis/wit/workitems/{work_item_id}?api-version=6.0"

    # Update both display and value fields
    patches = [
        {"op": "add", "path": "/fields/Hisoft.21ViaNet.TotalLaborTimeShow", "value": str(labor_time)},
        {"op": "add", "path": "/fields/Hisoft.21ViaNet.TotalLaborTime", "value": labor_time},
    ]

    try:
        resp = requests.patch(
            url,
            headers={"Authorization": _get_tfs_headers().get("Authorization", ""),
                      "Content-Type": "application/json-patch+json"},
            json=patches,
            timeout=30,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "message": f"Updated WI#{work_item_id} Labor Time to {labor_time}"})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP {resp.status_code}: {e.response.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Webhook Log ──────────────────────────────────────────────

@tfs_bp.route('/recent', methods=['GET'])
@require_auth
def recent():
    """GET /api/tfs/recent - Get recent webhook events."""
    max_items = request.args.get('max', 50, type=int)
    return jsonify({"webhooks": list(reversed(_webhook_log[:max_items]))})


# ═══════════════════════════════════════════════════════════════
# ─── TFS Request 2010 (Inner Network via PowerShell) ──────────
# ═══════════════════════════════════════════════════════════════

def _run_tfs_ps(action, **kwargs):
    """Run TfsRequest.ps1 and return parsed JSON.

    Returns (data_dict, error_string_or_None).
    """
    ps1 = _get_tfs_request_ps1()
    if not os.path.isfile(ps1):
        return None, f"TfsRequest.ps1 not found at: {ps1}"

    config_path = os.path.join(current_app.config['BASE_DIR'], 'ps_workspace_config.json')

    args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", ps1, "-Action", action, "-ConfigPath", config_path]

    if kwargs.get("work_item_ids"):
        for wid in kwargs["work_item_ids"]:
            args.extend(["-WorkItemIds", str(wid)])
    if kwargs.get("state"):
        args.extend(["-State", kwargs["state"]])
    if kwargs.get("assigned_to"):
        args.extend(["-AssignedTo", kwargs["assigned_to"]])
    if kwargs.get("property"):
        args.extend(["-Property", kwargs["property"]])
    if kwargs.get("action_field"):
        args.extend(["-ActionField", kwargs["action_field"]])
    if kwargs.get("solution"):
        args.extend(["-Solution", kwargs["solution"]])
    if kwargs.get("working_hour"):
        args.extend(["-WorkingHour", str(kwargs["working_hour"])])

    try:
        result = subprocess.run(
            ["powershell"] + args,
            capture_output=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # Decode: PowerShell sets UTF-8, but fallback to GBK on Chinese Windows
        def _decode(data):
            try:
                return data.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                return data.decode("gbk", errors="replace") if isinstance(data, bytes) else data

        stdout_text = _decode(result.stdout) if result.stdout else ""
        stderr_text = _decode(result.stderr) if result.stderr else ""
        combined_output = stdout_text.strip()
        all_output = stdout_text.strip() + "\n---STDERR---\n" + stderr_text.strip()

        if result.returncode != 0:
            logger.error(f"TFS PS error (exit {result.returncode}, action={action}):\n{all_output[:800]}")
            # In PS 5.1, Write-Error goes to stdout. Check for error text.
            err_msg = stderr_text.strip() or combined_output.split("---STDERR---")[0].strip() or "PowerShell error"
            return None, f"Exit code {result.returncode}: {err_msg[:500]}"

        # Find first valid JSON line
        for line in combined_output.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                if data.get("error"):
                    return None, data["error"]
                return data, None
        logger.error(f"TFS PS no JSON output: {combined_output[:500]}")
        return None, f"No JSON output from PowerShell. stdout: {combined_output[:500]}"
    except subprocess.TimeoutExpired:
        return None, "PowerShell script timed out (>120s)"
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}. Output: {combined_output[:500]}"
    except Exception as e:
        logger.exception(f"TFS PS subprocess error: {e}")
        return None, f"Subprocess error: {str(e)}"


# ─── AI Classification ────────────────────────────────────────

# LLM config (same as EDM Agent — reads .edm_agent_llm_config.json)
_LLM_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".edm_agent_llm_config.json")

def _load_llm_config():
    """Load .edm_agent_llm_config.json. Returns defaults if missing."""
    defaults = {
        "model": "openai/Qwen3.5-27B",
        "api_base": "http://172.31.0.103:20261/v1",
        "api_key": "",
        "timeout": 15,
    }
    if not os.path.isfile(_LLM_CONFIG_FILE):
        return defaults
    try:
        with open(_LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in defaults.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception:
        return defaults


def _strip_html(text):
    """Strip HTML tags from text and decode entities, keeping only readable text."""
    # Remove script/style content first
    clean = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove all remaining tags
    clean = re.sub(r'<[^>]+>', ' ', clean)
    # Decode common HTML entities
    clean = html.unescape(clean)
    # Collapse whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


# ── Assign To mapping (email → name) ──

_ASSIGNEE_MAP = {
    "teng.jiangtao@oe.21vianet.com": "Jerome Teng",
    "su.hang3@oe.21vianet.com": "Su Hang3",
    "qiao.jinxiu3@oe.21vianet.com": "Jancy Qiao",
    "ouyang.mengmeng@oe.21vianet.com": "Romy Ouyang",
    "ma.chuntao@oe.21vianet.com": "Michael Ma",
    "liu.wenya@oe.21vianet.com": "Liu Wenya",
}


def _extract_assigned_to(tsg_log, title=""):
    """Extract sender email from TSGLog HTML and map to assignee name.

    Strategy:
    1. Strip HTML to get plain text
    2. Find the first "From:" line (most recent email reply)
    3. Extract email from that line
    4. Look up in _ASSIGNEE_MAP
    Returns assignee name or empty string.
    """
    if not tsg_log:
        text = title
        logger.debug("[AssignTo] No TSGLog, scanning title")
    else:
        text = _strip_html(tsg_log)

    if not text:
        logger.debug("[AssignTo] No text to scan")
        return ""

    # Find "From:" lines — the first one is the most recent reply
    from_lines = re.findall(r'From:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    search_text = ""
    if from_lines:
        search_text = from_lines[0]
        logger.info(f"[AssignTo] From line: {search_text.strip()[:100]}")
    else:
        search_text = text
        logger.debug("[AssignTo] No 'From:' header found, scanning full text")

    # Extract email from the search text
    emails = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', search_text)
    if not emails:
        # Broader search across the whole text
        emails = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', text)
        logger.info(f"[AssignTo] Emails in full text: {emails[:5]}")
    else:
        logger.info(f"[AssignTo] Emails in From line: {emails}")

    for email in emails:
        email_lower = email.lower()
        if email_lower in _ASSIGNEE_MAP:
            name = _ASSIGNEE_MAP[email_lower]
            logger.info(f"[AssignTo] Matched: {email_lower} -> {name}")
            return name

    logger.warning(f"[AssignTo] No match found in map. Found emails: {emails[:3]}")
    return ""


def _classify_ticket(description, title="", tsg_log=""):
    """Classify a ticket into a Property category.

    Tries description first; if empty or too short, falls back to TSGLog or title.
    Tier 1: litellm AI.
    Tier 2: keyword-based classification.

    Returns (property, solution, working_hour).
    """
    # Build the text to classify — prefer description, fall back to TSGLog, then title
    text_to_classify = (description or "").strip()
    if len(text_to_classify) < 10 and title:
        text_to_classify = _strip_html(title).strip()
        logger.info(f"TFS classify: description empty/short, using title: {title[:100]}...")
    if len(text_to_classify) < 10:
        logger.debug("TFS classify: no content to classify, returning PS-General")
        return ("PS-General", "General support request.", 1, "")

    # Strip HTML if it looks like HTML (TSGLog is HTML)
    if '<' in text_to_classify[:100]:
        text_to_classify = _strip_html(text_to_classify)

    # Truncate very long text (TSGLog can be huge) — keep last 2000 chars (latest reply)
    if len(text_to_classify) > 2000:
        text_to_classify = text_to_classify[-2000:]

    # ── Tier 1: AI via litellm ──
    ai_result = _classify_ticket_ai(text_to_classify)
    if ai_result is not None:
        return ai_result

    # ── Tier 2: Keyword fallback ──
    logger.info(f"TFS classify: AI unavailable, keyword fallback for: {text_to_classify[:80]}...")
    return _classify_by_keywords(text_to_classify)


# ── Shared AI prompts ──

_AI_SYSTEM_PROMPT = """You are a PS (Platform Support) team ticket classification assistant.
Your task is to analyze ticket content (usually email threads from TFS TSGLog) and for each ticket:
1. Classify it into a Property category
2. Extract the sender email from the latest email to suggest Assign To
3. Provide a concise solution summary **in English**
4. Estimate the working hour

Return ONLY valid JSON. Do NOT output any other content."""

_AI_CATEGORY_DESC = """Category descriptions (strictly use these, do not invent new ones):
GFS-Active Directory: AD Group, Domain Controller, OU management, user accounts
GFS-ADFS: AD FS, Claims, Claims Provider, federation authentication
GFS-PKI: PKI, Certificate, Thumbprint, PKCS, CA
GFS-Monitoring: SCOM, Monitoring, Alert, event alerts
GFS-Definitive Software Library: DSL, Software distribution, Software Library
GFS-Imaging: OS Image, WDS, bare metal deployment
GFS-WebProxy: Web proxy, reverse proxy
PS-AAD: Azure AD, Entra ID, cloud identity
PS-DSTS: DSTS system
PS-EDM: EDM, email templates, Token replacement, email distribution
PS-HYPERV: Hyper-V, virtualization, VM host
PS-Nethop: Nethop network management
PS-PAW: PAW platform, Privileged Access
PS-Other: Others that cannot be categorized
PS-Secret Store: Credential store, Secret, Password Vault
PS-Server Security: Server security, patching, Vulnerability
PS-SNMPX: SNMP, SNMPX, network management protocol

Rules:
- PKI/Certificate → GFS-PKI
- SCOM/Monitoring → GFS-Monitoring
- AD Group/Domain Controller → GFS-Active Directory
- AD FS/Claims → GFS-ADFS
- DSL/Software distribution → GFS-Definitive Software Library
- OS Image/WDS → GFS-Imaging
- EDM email → PS-EDM
- Nethop → PS-Nethop"""

_AI_ASSIGNEE_MAPPING = """邮件联系人到 Assign To 的映射（严格按此映射，不写其他名字）：
teng.jiangtao@oe.21vianet.com → Jerome Teng
su.hang3@oe.21vianet.com → Su Hang3
qiao.jinxiu3@oe.21vianet.com → Jancy Qiao
ouyang.mengmeng@oe.21vianet.com → Romy Ouyang
ma.chuntao@oe.21vianet.com → Michael Ma
liu.wenya@oe.21vianet.com → Liu Wenya"""

_AI_ASSIGNEE_RULES = """提取 Assign To 规则：
- 找到 TSGLog 中**最新一封邮件**（最上面的 From）
- 提取发件人邮箱，对照上方映射表找到对应的 Assign To 姓名
- 如果邮箱不在映射表中，但名字能匹配到 PS 团队成员，返回姓名
- 如果无法确定，返回空字符串 """""


def _build_user_content(description):
    """Build user content for single-ticket AI classify."""
    return f"""{_AI_CATEGORY_DESC}

工单内容：
{description}"""


def _build_batch_user_content(tickets):
    """Build user content for batch AI classify.

    tickets: list of {"id": int, "title": str, "text": str}
    """
    lines = [
        _AI_CATEGORY_DESC,
        "",
        _AI_ASSIGNEE_MAPPING,
        "",
        _AI_ASSIGNEE_RULES,
        "",
        f"Classify the following {len(tickets)} tickets. Return a JSON array:",
        'Each ticket: {"id": <id>, "property": "...", "solution": "<English summary>", "working_hour": <int>, "assigned_to": "<name or empty string>"}',
        "Return ONLY the JSON array, nothing else.",
        "",
    ]
    for i, t in enumerate(tickets):
        text = t["text"][:2000]  # truncate per-ticket text
        lines.append(f"=== Ticket {i+1} / {len(tickets)} (ID: {t['id']}) ===")
        lines.append(f"Title: {t['title']}")
        lines.append(f"Content:\n{text}")
        lines.append("")
    return "\n".join(lines)


def _parse_single_ai_response(content):
    """Parse a single-ticket AI response into (property, solution, working_hour)."""
    if "```" in content:
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            content = match.group(1).strip()

    elif not content.startswith("{"):
        obj_match = re.search(r'\{[\s\S]*\}', content)
        if obj_match:
            content = obj_match.group(0)

    result = json.loads(content)
    prop = result.get("property", "PS-Other")
    sol = result.get("solution", "AI classified support request.")
    wh = int(result.get("working_hour", 1))
    return (prop, sol, wh)


def _classify_batch_ai(tickets):
    """Batch AI classify: send all tickets in one batch, or split if too large.

    tickets: list of {"id": int, "title": str, "text": str}
    Returns dict {id: (property, solution, working_hour)} or None on failure.
    """
    import time
    start = time.time()
    try:
        import litellm
        cfg = _load_llm_config()
        if not cfg.get("api_key"):
            logger.warning("TFS batch-classify: api_key not set")
            return None

        # Determine batch size dynamically
        all_content = _build_batch_user_content(tickets)
        # Qwen reasoning model uses ~8000 max_tokens. Input chars + output (~200 chars/ticket)
        # Safe limit: ~8000 input chars for reasoning model
        MAX_INPUT_CHARS = 8000

        if len(all_content) <= MAX_INPUT_CHARS:
            # All tickets fit in one batch
            batches = [tickets]
            logger.info(f"[AI-classify-batch] All {len(tickets)} tickets fit in one batch ({len(all_content)} chars)")
        else:
            # Split into batches, each batch under MAX_INPUT_CHARS
            batches = []
            current_batch = []
            current_chars = 0
            for t in tickets:
                t_chars = len(f"标题: {t['title']}\n内容:\n{t['text'][:2000]}") + 80  # overhead
                if current_batch and current_chars + t_chars > MAX_INPUT_CHARS:
                    batches.append(current_batch)
                    current_batch = [t]
                    current_chars = t_chars
                else:
                    current_batch.append(t)
                    current_chars += t_chars
            if current_batch:
                batches.append(current_batch)
            logger.info(f"[AI-classify-batch] Split into {len(batches)} batches")

        all_results = {}
        for batch_idx, batch in enumerate(batches):
            batch_num = batch_idx + 1
            total_batches = len(batches)

            user_content = _build_batch_user_content(batch)
            logger.info(f"[AI-classify-batch] === Batch {batch_num}/{total_batches}: count={len(batch)} content_len={len(user_content)} ===")
            logger.info(f"[AI-classify-batch] --- SYSTEM PROMPT ({len(_AI_SYSTEM_PROMPT)} chars) ---")
            logger.info(f"[AI-classify-batch] {_AI_SYSTEM_PROMPT}")
            logger.info(f"[AI-classify-batch] --- USER CONTENT ({len(user_content)} chars) ---")
            logger.info(f"[AI-classify-batch] {user_content}")

            resp = litellm.completion(
                model=cfg["model"],
                api_base=cfg.get("api_base"),
                api_key=cfg.get("api_key"),
                messages=[
                    {"role": "system", "content": _AI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=8000,
                temperature=0,
                timeout=cfg.get("timeout", 120),
            )

            raw_content = resp.choices[0].message.content.strip()
            reasoning_content = getattr(resp.choices[0].message, "reasoning_content", None) or ""
            finish_reason = resp.choices[0].finish_reason

            logger.info(f"[AI-classify-batch] === Batch {batch_num} RESPONSE: finish_reason={finish_reason} raw_len={len(raw_content)} reasoning_len={len(reasoning_content)} ===")
            logger.info(f"[AI-classify-batch] --- RAW CONTENT ({len(raw_content)} chars) ---")
            logger.info(f"[AI-classify-batch] {raw_content}")
            if reasoning_content:
                logger.info(f"[AI-classify-batch] --- REASONING CONTENT ({len(reasoning_content)} chars) ---")
                logger.info(f"[AI-classify-batch] {reasoning_content}")

            # For reasoning models: use content first, fall back to reasoning_content
            content = raw_content
            if not content and reasoning_content:
                content = reasoning_content.strip()
                logger.info(f"[AI-classify-batch] Batch {batch_num}: using reasoning_content ({len(content)} chars)")

            # Extract JSON array
            if "```" in content:
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()

            elif not content.startswith("["):
                arr_match = re.search(r'\[[\s\S]*\]', content)
                if arr_match:
                    content = arr_match.group(0)

            results = json.loads(content)
            for item in results:
                wid = item.get("id")
                if wid is None:
                    continue
                prop = item.get("property", "PS-Other")
                sol = item.get("solution", "AI classified support request.")
                wh = int(item.get("working_hour", 1))
                assigned = item.get("assigned_to", "")
                all_results[wid] = (prop, sol, wh, assigned)
                logger.info(f"[AI-classify-batch] WI#{wid}: property={prop} assigned_to={assigned}")

        elapsed = round(time.time() - start, 1)
        logger.info(f"[AI-classify-batch] Done: {len(all_results)}/{len(tickets)} tickets in {elapsed}s")
        return all_results

    except ImportError:
        logger.warning("litellm not installed, falling back to keyword classification")
        return None
    except Exception as e:
        logger.warning(f"[AI-classify-batch] Failed after {round(time.time()-start,1)}s: {e}, falling back to per-ticket")
        return None

    except ImportError:
        logger.warning("litellm not installed, falling back to keyword classification")
        return None
    except Exception as e:
        logger.warning(f"[AI-classify-batch] Failed after {round(time.time()-start,1)}s: {e}, falling back to per-ticket")
        return None


def _classify_ticket_ai(description):
    """Try litellm classification (single ticket). Returns (property, solution, hour) or None."""
    import time
    start = time.time()
    try:
        import litellm
        cfg = _load_llm_config()
        if not cfg.get("api_key"):
            logger.warning("TFS classify: api_key not set in .edm_agent_llm_config.json")
            return None

        system_prompt = _AI_SYSTEM_PROMPT
        user_content = _build_user_content(description)

        logger.info(f"[AI-classify] Request: model={cfg['model']} desc={description[:100]}...")

        resp = litellm.completion(
            model=cfg["model"],
            api_base=cfg.get("api_base"),
            api_key=cfg.get("api_key"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=800,
            temperature=0,
            timeout=cfg.get("timeout", 30),
        )
        elapsed = round(time.time() - start, 1)

        raw_content = resp.choices[0].message.content.strip()
        reasoning_content = getattr(resp.choices[0].message, "reasoning_content", None) or ""
        finish_reason = resp.choices[0].finish_reason

        logger.info(f"[AI-classify] Response: finish_reason={finish_reason} elapsed={elapsed}s raw_content_len={len(raw_content)} reasoning_len={len(reasoning_content)}")
        logger.info(f"[AI-classify] Raw content: {raw_content[:500]}")
        if reasoning_content:
            logger.info(f"[AI-classify] Reasoning content: {reasoning_content[:500]}")

        # Use content; fall back to reasoning_content if empty
        content = raw_content
        if not content:
            if reasoning_content:
                content = reasoning_content.strip()
                logger.info(f"[AI-classify] Using reasoning_content as fallback ({len(content)} chars)")
            else:
                logger.error("[AI-classify] Both content and reasoning_content are empty!")

        # Extract JSON from markdown code block if present (same logic as EDM agent)
        if "```" in content:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                content = match.group(1).strip()
                logger.info(f"[AI-classify] Extracted from code block: {content[:300]}")

        # Fallback: find first {...} object in text (Qwen often wraps JSON in prose)
        elif not content.startswith("{"):
            obj_match = re.search(r'\{[\s\S]*\}', content)
            if obj_match:
                content = obj_match.group(0)
                logger.info(f"[AI-classify] Extracted {{...}} object: {content[:300]}")

        result = json.loads(content)
        prop = result.get("property", "PS-General")
        sol = result.get("solution", "AI classified support request.")
        wh = int(result.get("working_hour", 1))
        logger.info(f"[AI-classify] Result: property={prop} solution={sol[:60]} working_hour={wh}")
        return (prop, sol, wh)
    except ImportError:
        logger.warning("litellm not installed, falling back to keyword classification")
        return None
    except Exception as e:
        logger.warning(f"[AI-classify] Failed after {round(time.time()-start,1)}s: {e}, falling back to keywords")
        return None


# ── Keyword-based classification fallback ──

_EDM_KEYWORDS = [
    "edm", "email distribution", "email template", "token replace",
    "edm process", "edm dashboard", "edm notification", "edm send",
    "mail merge", "bulk email", "%%", "edm guidance",
]

_EMAIL_KEYWORDS = [
    "outlook", "exchange", "mailbox", "smtp", "email rule",
    "email forward", "mail flow", "transport rule",
]

_AZURE_KEYWORDS = [
    "azure", "vm", "virtual machine", "storage account", "resource group",
    "subscription", "portal", "arm template", "vnet", "aks", "aks",
    "application gateway", "load balancer", "vmss", "scale set",
    "function app", "function app", "app service", "logic app",
    "key vault", "cosmos", "sql azure", "azure monitor",
]

_AD_KEYWORDS = [
    "active directory", "ad group", "ad user", "password reset",
    "gpo", "group policy", "ou structure", "domain join",
    "user account", "disabled account", "enable account",
]

_O365_KEYWORDS = [
    "office 365", "m365", "sharepoint", "teams", "onedrive",
    "license", "yammer", "ms teams", "office365",
]

_NETWORK_KEYWORDS = [
    "vpn", "firewall", "dns", "connectivity", "proxy",
    "network security", "nsG", "route table", "network watcher",
    "private endpoint", "private link",
]

_GFS_PKI_KEYWORDS = [
    "pki", "certificate", "cert", "thumbprint", "pkcs",
    "x509", "certification authority", "ca server",
]

_GFS_MONITORING_KEYWORDS = [
    "scom", "monitor", "monitoring", "alert", "event",
    "system center operations manager", "scm alert",
]

_GFS_AD_KEYWORDS = [
    "ad group", "domain controller", "ou management",
    "active directory", "ad user", "password reset",
    "user account", "disabled account", "enable account",
]

_GFS_ADFS_KEYWORDS = [
    "ad fs", "adfs", "claims", "claims provider",
    "federation", "sts", "trusted relying party",
]

_GFS_DSL_KEYWORDS = [
    "definitive software library", "dsl", "software library",
    "application catalog", "software catalog",
]

_GFS_IMAGING_KEYWORDS = [
    "image", "os image", "wds", "bare metal", "osd",
    "system imaging", "deploy image",
]

_GFS_WEBPROXY_KEYWORDS = [
    "web proxy", "reverse proxy", "url rewrite",
    "iis proxy", "proxy farm",
]

_PS_AAD_KEYWORDS = [
    "azure ad", "aad", "entra id", "cloud identity",
    "conditional access", "sso", "azure active directory",
]

_PS_DSTS_KEYWORDS = [
    "dsts", "dsts system",
]

_PS_HYPERV_KEYWORDS = [
    "hyper-v", "hyperv", "virtualization host",
    "vm host", "nested virtualization",
]

_PS_NETHOP_KEYWORDS = [
    "nethop", "network hop",
]

_PS_PAW_KEYWORDS = [
    "paw", "privileged access", "pivoted access workstation",
]

_PS_SECRET_STORE_KEYWORDS = [
    "secret store", "credential store", "password vault",
    "secret management", "credential manager",
]

_PS_SERVER_SECURITY_KEYWORDS = [
    "server security", "vulnerability", "patching", "patch missing",
    "security update", "monthly patching",
]

_PS_SNMPX_KEYWORDS = [
    "snmpx", "snmp", "netmib",
]


def _classify_by_keywords(text):
    """Keyword-based classification fallback when AI is unavailable."""
    t = text.lower()

    categories = [
        ("GFS-PKI", _GFS_PKI_KEYWORDS),
        ("GFS-Monitoring", _GFS_MONITORING_KEYWORDS),
        ("GFS-Active Directory", _GFS_AD_KEYWORDS),
        ("GFS-ADFS", _GFS_ADFS_KEYWORDS),
        ("GFS-Definitive Software Library", _GFS_DSL_KEYWORDS),
        ("GFS-Imaging", _GFS_IMAGING_KEYWORDS),
        ("GFS-WebProxy", _GFS_WEBPROXY_KEYWORDS),
        ("PS-AAD", _PS_AAD_KEYWORDS),
        ("PS-DSTS", _PS_DSTS_KEYWORDS),
        ("PS-EDM", _EDM_KEYWORDS),
        ("PS-HYPERV", _PS_HYPERV_KEYWORDS),
        ("PS-Nethop", _PS_NETHOP_KEYWORDS),
        ("PS-PAW", _PS_PAW_KEYWORDS),
        ("PS-Secret Store", _PS_SECRET_STORE_KEYWORDS),
        ("PS-Server Security", _PS_SERVER_SECURITY_KEYWORDS),
        ("PS-SNMPX", _PS_SNMPX_KEYWORDS),
        ("PS-Other", []),  # always a fallback but with 0 score
    ]

    # Count keyword matches per category
    scores = {}
    for prop, keywords in categories:
        count = sum(1 for kw in keywords if kw in t)
        if count > 0:
            scores[prop] = count

    if not scores:
        return ("PS-Other", "General support request (keyword match not found).", 1, "")

    # Pick the category with the most matches
    best_prop = max(scores, key=scores.get)
    sol_map = {
        "PS-EDM": "Follow the EDM guidance to implement the EDM solution.",
        "GFS-PKI": "Handle PKI certificate request/renewal/installation.",
        "GFS-Monitoring": "Investigate SCOM monitoring alert or event.",
        "GFS-Active Directory": "Handle AD group or domain controller task.",
        "GFS-ADFS": "Investigate ADFS/Claims/federation issue.",
        "GFS-Definitive Software Library": "Manage DSL software catalog entry.",
        "GFS-Imaging": "Handle OS image or WDS deployment task.",
        "GFS-WebProxy": "Investigate web proxy configuration.",
        "PS-AAD": "Handle Azure AD/Entra ID identity issue.",
        "PS-HYPERV": "Handle Hyper-V virtualization task.",
        "PS-Nethop": "Handle Nethop network management task.",
        "PS-PAW": "Handle PAW privileged access task.",
        "PS-Secret Store": "Manage secret/credential store.",
        "PS-Server Security": "Handle server patching/security update.",
        "PS-SNMPX": "Handle SNMP/SNMPX monitoring configuration.",
    }
    return (best_prop, sol_map.get(best_prop, "General support request."), 1, "")


# ─── TFS Request 2010 Endpoints ───────────────────────────────

@tfs_bp.route('/request/tickets', methods=['GET'])
@require_auth
def request_tickets():
    """GET /api/tfs/request/tickets - Query open TFS Request tickets for PS team."""
    data, err = _run_tfs_ps("query")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    # Log TSGLog presence
    tickets = data.get("tickets", [])
    tsg_count = sum(1 for t in tickets if t.get("tsgLog"))
    logger.info(f"[tickets] Fetched {len(tickets)} tickets, {tsg_count} have tsgLog content")
    return jsonify({
        "ok": True,
        "count": data.get("count", 0),
        "tickets": data.get("tickets", []),
    })


@tfs_bp.route('/request/classify', methods=['POST'])
@require_auth
def request_classify():
    """POST /api/tfs/request/classify - AI classify a ticket description.

    Body: {"description": "..."}
    Returns: {"property": "PS-EDM", "solution": "...", "working_hour": 2}
    """
    body = request.get_json()
    if not body or not body.get("description"):
        return jsonify({"error": "description is required"}), 400

    prop, sol, wh = _classify_ticket(body["description"])
    return jsonify({"ok": True, "property": prop, "solution": sol, "working_hour": wh})


@tfs_bp.route('/request/batch-classify', methods=['POST'])
@require_auth
def request_batch_classify():
    """POST /api/tfs/request/batch-classify — AI classify a batch of tickets, return results WITHOUT updating TFS.

    Body: {"tickets": [{"id":123, "title":"...", "description":"...", ...}, ...]}
    Returns: list of {id, title, description, property, solution, workingHour}
    """
    body = request.get_json()
    if not body or not body.get("tickets"):
        return jsonify({"error": "tickets list is required"}), 400

    tickets = body["tickets"]
    logger.info(f"[batch-classify] Received {len(tickets)} tickets")

    # Filter: only classify "Assigned To Implementer" tickets, skip others
    to_classify = [t for t in tickets if t.get("state") == "Assigned To Implementer"]
    skip_list = [t for t in tickets if t.get("state") != "Assigned To Implementer"]
    logger.info(f"[batch-classify] {len(to_classify)} to classify, {len(skip_list)} skipped (already in process or other state)")

    # Prepare per-ticket data for AI
    ai_inputs = []
    for ticket in to_classify:
        desc = ticket.get("description", "")
        tsg_log = ticket.get("tsgLog", "")
        title = ticket.get("title", "")
        wid = ticket.get("id")
        has_tsg = bool(tsg_log)
        tsg_len = len(tsg_log) if tsg_log else 0
        logger.info(f"[batch-classify] WI#{wid}: has_tsgLog={has_tsg} tsgLog_len={tsg_len} title={title[:60]}")
        # Use TSGLog as fallback when description is empty
        text = desc if desc else tsg_log
        # Strip HTML for AI
        ai_text = _strip_html(text) if text else ""
        if len(ai_text) > 2000:
            ai_text = ai_text[-2000:]
        ai_inputs.append({
            "id": wid,
            "title": title,
            "text": ai_text,
            "tsgLog": tsg_log,
        })

    # ── Tier 1: Batch AI (all tickets in one prompt) ──
    ai_results = _classify_batch_ai(ai_inputs)

    # ── Tier 2: Per-ticket fallback if batch AI fails ──
    if ai_results is None:
        ai_results = {}
        for inp in ai_inputs:
            if inp["text"]:
                prop, sol, wh, _ = _classify_ticket(inp["text"], title=inp["title"])
                ai_results[inp["id"]] = (prop, sol, wh, "")

    # Build response
    results = []
    for ticket in tickets:
        current_state = ticket.get("state", "")
        wid = ticket.get("id")
        current_assigned = ticket.get("assignedTo", "")
        current_property = ticket.get("property", "")
        desc = ticket.get("description", "")
        title = ticket.get("title", "")

        if current_state == "Assigned To Implementer":
            # AI analyzed
            ai = ai_results.get(wid)
            if ai:
                prop, sol, wh, ai_assigned = ai
            else:
                prop, sol, wh, ai_assigned = "PS-Other", "No content to classify.", 1, ""
            # Code-based assign-to as fallback when AI doesn't return one
            tsg_log = ticket.get("tsgLog", "")
            code_assigned = _extract_assigned_to(tsg_log, title=title)
            suggested_assigned = ai_assigned if ai_assigned else code_assigned
            text = desc if desc else tsg_log
            needs_state_change = True
        else:
            # Skip AI — keep existing values
            prop = current_property if current_property else "PS-Other"
            sol = ""
            wh = 0
            suggested_assigned = current_assigned
            text = desc
            needs_state_change = False

        results.append({
            "id": wid,
            "title": title,
            "description": _strip_html(text)[:200] if text else "",
            "state": current_state,
            "assignedTo": current_assigned,
            "workItemType": ticket.get("workItemType", ""),
            "property": prop,
            "solution": sol,
            "workingHour": wh,
            "suggestedAssignedTo": suggested_assigned,
            "needsStateChange": needs_state_change,
            "skipped": current_state != "Assigned To Implementer",
        })
    return jsonify({"ok": True, "classifications": results})


@tfs_bp.route('/request/batch-apply', methods=['POST'])
@require_auth
def request_batch_apply():
    """POST /api/tfs/request/batch-apply — Apply confirmed classifications to TFS.

    Body: {
        "classifications": [{id, property, solution, workingHour, assigned_to, state}, ...],
        "assigned_to": "Michael Ma",  # default fallback
        "action_field": "1ST Update"
    }
    """
    body = request.get_json()
    if not body or not body.get("classifications"):
        return jsonify({"error": "classifications list is required"}), 400

    classifications = body["classifications"]
    default_assigned_to = body.get("assigned_to", "")
    action_field = body.get("action_field", "1ST Update")

    results = []
    for cls in classifications:
        wid = cls.get("id")
        if not wid:
            continue
        # Per-ticket assigned_to falls back to global default
        at = cls.get("assigned_to") or default_assigned_to
        # Per-ticket state falls back to In Process Implementer
        state = cls.get("state") or "In Process Implementer"
        update_data, update_err = _run_tfs_ps(
            "update",
            work_item_ids=[wid],
            state=state,
            assigned_to=at,
            property=cls.get("property"),
            action_field=action_field,
            solution=cls.get("solution"),
            working_hour=cls.get("workingHour"),
        )

        if update_err:
            results.append({
                "workItemId": wid,
                "ok": False,
                "error": update_err,
            })
        else:
            results.append({
                "workItemId": wid,
                "ok": True,
                "property": cls.get("property"),
                "solution": cls.get("solution"),
                "workingHour": cls.get("workingHour"),
                "assignedTo": at,
            })

    success_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - success_count

    return jsonify({
        "ok": True,
        "total": len(results),
        "success": success_count,
        "failed": fail_count,
        "results": results,
    })


@tfs_bp.route('/request/auto-process', methods=['POST'])
@require_auth
def request_auto_process():
    """POST /api/tfs/request/auto-process - DEPRECATED, use batch-classify + batch-apply instead.

    Kept for backward compatibility.
    """
    body = request.get_json()
    if not body:
        return jsonify({"error": "JSON body required"}), 400

    assigned_to = body.get("assigned_to", "")
    action_field = body.get("action_field", "1ST Update")

    # First, query open tickets
    data, err = _run_tfs_ps("query")
    if err:
        return jsonify({"ok": False, "error": err}), 500

    tickets = data.get("tickets", [])
    results = []
    for ticket in tickets:
        desc = ticket.get("description", "")
        tsg_log = ticket.get("tsgLog", "")
        title = ticket.get("title", "")
        text = desc if desc else tsg_log
        prop, sol, wh = _classify_ticket(text, title=title)

        # Update the ticket
        update_data, update_err = _run_tfs_ps(
            "update",
            work_item_ids=[ticket["id"]],
            state="In Process Implementer",
            assigned_to=assigned_to,
            property=prop,
            action_field=action_field,
            solution=sol,
            working_hour=wh,
        )

        if update_err:
            results.append({
                "workItemId": ticket["id"],
                "title": ticket.get("title", ""),
                "ok": False,
                "error": update_err,
                "property": prop,
                "solution": sol,
                "workingHour": wh,
            })
        else:
            results.append({
                "workItemId": ticket["id"],
                "title": ticket.get("title", ""),
                "ok": True,
                "property": prop,
                "solution": sol,
                "workingHour": wh,
                "state": "In Process Implementer",
                "assignedTo": assigned_to,
            })

    success_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - success_count

    return jsonify({
        "ok": True,
        "total": len(results),
        "success": success_count,
        "failed": fail_count,
        "results": results,
    })


@tfs_bp.route('/request/update', methods=['POST'])
@require_auth
def request_update():
    """POST /api/tfs/request/update - Update a single TFS Request work item.

    Body: {
        "work_item_id": 12345,
        "state": "In Process Implementer",
        "assigned_to": "Michael Ma",
        "property": "PS-EDM",
        "action_field": "1ST Update",
        "solution": "...",
        "working_hour": 1
    }
    """
    body = request.get_json()
    if not body or not body.get("work_item_id"):
        return jsonify({"error": "work_item_id is required"}), 400

    data, err = _run_tfs_ps(
        "update",
        work_item_ids=[body["work_item_id"]],
        state=body.get("state"),
        assigned_to=body.get("assigned_to"),
        property=body.get("property"),
        action_field=body.get("action_field"),
        solution=body.get("solution"),
        working_hour=body.get("working_hour"),
    )
    if err:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True, "result": data.get("result", {})})


@tfs_bp.route('/request/resolve', methods=['POST'])
@require_auth
def request_resolve():
    """POST /api/tfs/request/resolve - Resolve a single ticket.

    Body: {"work_item_id": 12345}
    """
    body = request.get_json()
    if not body or not body.get("work_item_id"):
        return jsonify({"error": "work_item_id is required"}), 400

    data, err = _run_tfs_ps("resolve", work_item_ids=[body["work_item_id"]])
    if err:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True, "result": data.get("result", {})})


@tfs_bp.route('/request/batch-resolve', methods=['POST'])
@require_auth
def request_batch_resolve():
    """POST /api/tfs/request/batch-resolve - Batch resolve multiple tickets.

    Body: {"work_item_ids": [12345, 12346, ...]}
    """
    body = request.get_json()
    if not body or not body.get("work_item_ids"):
        return jsonify({"error": "work_item_ids list is required"}), 400

    work_item_ids = body["work_item_ids"]
    if not isinstance(work_item_ids, list) or len(work_item_ids) == 0:
        return jsonify({"error": "work_item_ids must be a non-empty list"}), 400

    data, err = _run_tfs_ps("batch_resolve", work_item_ids=work_item_ids)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({
        "ok": True,
        "total": data.get("total", 0),
        "success": data.get("success", 0),
        "failed": data.get("failed", 0),
        "results": data.get("results", []),
    })


@tfs_bp.route('/request/get/<int:work_item_id>', methods=['GET'])
@require_auth
def request_get(work_item_id):
    """GET /api/tfs/request/get/<id> - Get single work item details."""
    # Use PowerShell to get the item
    ps1 = _get_tfs_request_ps1()
    args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", ps1, "-Action", "connect"]

    # For get, we need a separate call. Let's reuse the update path but just read.
    # Actually, let's query all and filter, or we can add a simpler approach.
    # Best: query and filter for this ID.
    data, err = _run_tfs_ps("query")
    if err:
        return jsonify({"ok": False, "error": err}), 500

    tickets = data.get("tickets", [])
    for t in tickets:
        if t.get("id") == work_item_id:
            return jsonify({"ok": True, "ticket": t})

    return jsonify({"ok": False, "error": f"Work item #{work_item_id} not found in open tickets"}), 404
