"""Test LLM analysis directly with the email's subject and body."""
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

# Load LLM config
LLM_CONFIG_FILE = os.path.join(BASE_DIR, ".edm_agent_llm_config.json")
llm_defaults = {
    "model": "openai/Qwen3.5-27B",
    "api_base": "http://172.31.0.103:20261/v1",
    "api_key": "sk-proj-9aB3cD5eF7gH9iJ1kL3mN5oP7qR9sT1uV3wX5yZ7",
    "timeout": 30,
}
if os.path.isfile(LLM_CONFIG_FILE):
    with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
        llm_defaults.update(json.load(f))

llm_config = llm_defaults
print(f"LLM Model: {llm_config['model']}")
print(f"API Base:  {llm_config['api_base']}")
print(f"Timeout:   {llm_config.get('timeout', 30)}s\n")

# The real email data
SUBJECT = "FW: [EDM test and distribution] Incident 830353210 : SN-56619 Mooncake OCC-602: UC-Only Workspaces Enforcement Final Reminder (Group 1)"

BODY = """交由EDM Agent 来处理这封EDM


[cid:image001.png@01DD13B1.C9155320]


Michael Ma
21Vianet Blue Cloud  |  Platform Service Team  |  M: +86 15811051846
E: ma.chuntao@oe.21vianet.com  |  W: www.21vbluecloud.com
A: 12-14F,Building 6,No.6,Jiuxianqiao Road, Beijing Electronics Zone, Chaoyang District, Beijing


From: Lu Xinyu <lu.xinyu@oe.21vianet.com>
Sent: Monday, July 13, 2026 11:30 AM
To: DL-PS <DL-PS@oe.21vianet.com>; ps-tier2.support <ps-tier2.support@oe.21vianet.com>
Cc: Azure_CmMgr <Azure_CmMgr@oe.21vianet.com>
Subject: [EDM test and distribution] Incident 830353210 : SN-56619 Mooncake OCC-602: UC-Only Workspaces Enforcement Final Reminder (Group 1)

Hi Team

We got a reminder EDM. Could you please help to test and distribute it? Thanks.
Please reference the attachments for the approval Email and EDM template.

The Email token list and template were located at:
SN-56619 Group 1 Token 1-15.xlsx<https://microsoftapc.sharepoint.com/:x:/r/teams/AzureServiceNotificationsCollaboration/Shared%20Documents/2026/2026-07/830353210%20SN-56619/SN-56619%20%20Group%201%20Token%201-15.xlsx?d=w95d7dbbc7ff04e3495643e3f59398191&csf=1&web=1&e=dKVOhs>

Please feel free to let us know if you have any concerns, thanks.
"""

from edm_agent import EmailAnalyzer

print("=" * 70)
print("LLM 分析测试")
print("=" * 70)
print(f"主题: {SUBJECT}")
print(f"正文长度: {len(BODY)} 字符\n")

analyzer = EmailAnalyzer()

try:
    result = analyzer.analyze(SUBJECT, BODY)
    action = result.get("action", "unknown")
    confidence = result.get("confidence", 0)
    reason = result.get("reason", "")
    sn = result.get("sn", "")
    model = result.get("_model", "")
    is_fallback = result.get("_fallback", False)
    elapsed = result.get("_elapsed", 0)

    action_icon = {"edm_process": "✓", "ignore": "✗", "error": "!"}.get(action, "?")
    method = "关键词匹配 (Fallback)" if is_fallback else "LLM 语义分析"

    print(f"模型:       {model}")
    print(f"分析方式:   {method}")
    print(f"结果:       {action_icon} {action}")
    print(f"置信度:     {confidence}%")
    print(f"理由:       {reason}")
    print(f"SN:         {sn}")
    print(f"响应时间:   ~{elapsed}s")
except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
