"""
ICM 创建 Incident 测试 - 使用 CreateIncident 类
"""
import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

from icm_create_incident import CreateIncident

config = __import__('json').load(open("icm_config.json", encoding="utf-8"))
TOKEN = config["access_token"]

# 创建 Incident 对象
inc = CreateIncident()
inc.Title = "[Python Test] ICM Ticket via Python requests"
inc.Description = "This is a test incident created from Python using the ICM API directly, replicating the C# IcmDll.CreateIncident class."
inc.Summary = "Python API test incident"
inc.Severity = 3
inc.OwningTeamId = 37883  # PS team
inc.ImpactedServices = [{"ServiceId": 20284}]
inc.ImpactedTeams = [{"TeamId": 37883}]

print("=== Payload ===")
print(inc.to_json())
print()

# 发送 POST 请求
url = "https://prod.microsofticm.com/api2/incidentapi/incidents"
headers = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

print("=== Sending POST request ===")
resp = requests.post(url, json=inc.to_dict(), headers=headers, timeout=60)
print(f"Status: {resp.status_code}")

raw = resp.content
text = raw.decode('utf-8-sig') if raw[:3] == b'\xef\xbb\xbf' else raw.decode('utf-8')
print(f"Response: {text[:2000]}")

if resp.status_code in (200, 201):
    import json
    data = json.loads(text)
    # OData format
    result = data.get("value", [data])[0] if isinstance(data, dict) and "value" in data else data
    new_id = result.get("Id")
    print()
    print(f"[OK] Incident created! New ID: {new_id}")
else:
    print()
    print("[FAIL] Create failed")
