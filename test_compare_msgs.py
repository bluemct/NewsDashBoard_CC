"""Compare the content element structure (CDATA wrapper, attributes)."""
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="

headers = {
    "Accept": "application/atom+xml",
    "Authorization": "OAuth",
}
auth = HTTPBasicAuth(API_KEY, API_SECRET)
ns_atom = "http://www.w3.org/2005/Atom"

for msg_id in [3232247, 3233026, 3232968]:
    print(f"\n{'='*60}")
    print(f"Message ID: {msg_id}")
    print(f"{'='*60}")

    resp = requests.get(
        f"{HOST}/message/{msg_id}?preview",
        params={"apikey": API_KEY, "alt": "atom"},
        headers=headers,
        auth=auth,
        timeout=30,
    )

    raw = resp.content.decode("utf-8")

    # Find the content tag (with its attributes)
    content_start = raw.find("<content")
    content_end = raw.find("</content>") + len("</content>")
    if content_start >= 0 and content_end > content_start:
        content_tag = raw[content_start:content_end]
        # Show only the first 500 chars
        print(f"Content tag (first 500 chars):")
        print(content_tag[:500])

    # Check first 100 chars of content text
    cdata_start = raw.find("<![CDATA[")
    if cdata_start >= 0:
        print(f"\nFirst 100 chars of content: {raw[cdata_start:cdata_start+100]}")
