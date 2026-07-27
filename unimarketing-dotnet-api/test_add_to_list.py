"""
Unimarketing API — Test adding contacts to lists

Two auth methods:
1. BasicAuth (already works for contact CRUD)
2. OAuth HMAC-SHA1 (from C# SDK, try for add-to-list)

The "add to list" API uses POST /contact/ with a <link rel="related"> to the list.
"""
import base64
import hashlib
import hmac
import html
import json
import time
import urllib.parse
import uuid
from collections import OrderedDict

import requests
from requests.auth import HTTPBasicAuth

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="

# The two contacts from contact_after.json
CONTACTS = [
    {"email": "ma.chuntao@oe.21vianet.com", "contact_id": "241875793"},
    {"email": "microsoft.163163@163.com", "contact_id": "349433591"},
]


def build_oauth_signature(param_dict: dict) -> str:
    """Replicate C# SDK SignatureUtil.Sign() exactly.

    C# SDK: data = domain + "?" + sort(paramMap)
    domain = "http://" + APIKEY
    sort = sorted keys, each as key=value&, joined.
    Then HMAC-SHA1(data, secretKey), base64 output.
    """
    domain = f"http://{API_KEY}"

    # Sort by key, format as key=value&
    sorted_items = sorted(param_dict.items())
    query = ""
    for k, v in sorted_items:
        query += f"{k}={v}&"

    data = domain + "?" + query
    # HMAC-SHA1 with ASCII encoding (matching C# ASCIIEncoding)
    sig = hmac.new(
        API_SECRET.encode("ascii"),
        data.encode("ascii"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(sig).decode("ascii")


def build_oauth_url(base_url: str) -> str:
    """Build URL with OAuth HMAC-SHA1 query params (C# SDK style)."""
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())

    params = [
        f"apikey={urllib.parse.quote(API_KEY, encoding='utf-8')}",
        f"oauth_signature_method={urllib.parse.quote('HMAC-SHA1', encoding='utf-8')}",
        f"oauth_consumer_key={urllib.parse.quote(API_KEY, encoding='utf-8')}",
        f"alt=atom",
        f"oauth_timestamp={timestamp}",
        f"oauth_nonce={urllib.parse.quote(nonce, encoding='utf-8')}",
    ]

    # Build the param dict for signing (unencoded values)
    sign_params = {
        "apikey": API_KEY,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_consumer_key": API_KEY,
        "alt": "atom",
        "oauth_timestamp": timestamp,
        "oauth_nonce": nonce,
    }

    # The C# SDK signs with these param values as-is (before URL encoding)
    # But includes the header params too:
    sign_params["Authorization"] = "OAuth"
    sign_params["Host"] = "services.unimarketing.com.cn"
    sign_params["Content-Type"] = "application/atom+xml"

    signature = build_oauth_signature(sign_params)

    params.append(f"oauth_signature={urllib.parse.quote(signature, encoding='utf-8')}")

    separator = "&" if "?" in base_url else "?"
    return base_url + separator + params[0] + ("&" + "&".join(params[1:]) if len(params) > 1 else "")


def send_oauth(base_url: str, method: str = "POST", body: str = None) -> tuple:
    """Send request with OAuth HMAC-SHA1 signing (C# SDK style)."""
    url = build_oauth_url(base_url)

    headers = {
        "Content-Type": "application/atom+xml",
        "Authorization": "OAuth",
    }

    kwargs = {"timeout": 30}
    if body:
        kwargs["data"] = body.encode("utf-8")

    resp = requests.request(method, url, headers=headers, **kwargs)
    return resp.status_code, resp.text[:500]


def send_basicauth(url: str, method: str = "POST", body: str = None) -> tuple:
    """Send request with BasicAuth (already proven to work)."""
    params = {"apikey": API_KEY, "method": "post", "alt": "atom"}
    headers = {
        "Content-Type": "application/atom+xml; charset=utf-8",
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

    kwargs = {"timeout": 30, "params": params, "auth": HTTPBasicAuth(API_KEY, API_SECRET)}
    if body:
        kwargs["data"] = body.encode("utf-8")

    resp = requests.request(method, url, headers=headers, **kwargs)
    return resp.status_code, resp.text[:500]


def build_contact_to_list_xml(contact_email: str, list_id: str) -> str:
    """Build Atom Feed XML with <link rel="related"> to add contact to list."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        '  <entry>\n'
        f'    <email>{html.escape(contact_email)}</email>\n'
        f'    <link href="{HOST}/list/{list_id}/" '
        'rel="related" '
        'title="addContacts" />\n'
        '  </entry>\n'
        '</feed>'
    )


def build_contact_to_list_by_title_xml(contact_email: str, list_title: str) -> str:
    """Alternative: use list title instead of ID in the link."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        '  <entry>\n'
        f'    <email>{html.escape(contact_email)}</email>\n'
        f'    <link href="{HOST}/list/?field=title&q={html.escape(list_title)}" '
        'rel="related" '
        'title="addContacts" />\n'
        '  </entry>\n'
        '</feed>'
    )


def list_exists(list_id: str) -> tuple:
    """Check if a list exists via GET /list/{id}/."""
    # Try BasicAuth GET
    params = {"apikey": API_KEY, "alt": "atom"}
    headers = {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }
    resp = requests.get(
        f"{HOST}/list/{list_id}/",
        params=params,
        headers=headers,
        auth=HTTPBasicAuth(API_KEY, API_SECRET),
        timeout=30,
    )
    return resp.status_code, resp.text[:300]


def list_exists_oauth(list_id: str) -> tuple:
    """Check if a list exists via OAuth GET."""
    return send_oauth(f"{HOST}/list/{list_id}/", method="GET")


def get_contact(contact_id: str) -> tuple:
    """Get contact by ID to verify list membership."""
    params = {"apikey": API_KEY, "alt": "atom"}
    headers = {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }
    resp = requests.get(
        f"{HOST}/contact/{contact_id}/",
        params=params,
        headers=headers,
        auth=HTTPBasicAuth(API_KEY, API_SECRET),
        timeout=30,
    )
    return resp.status_code, resp.text[:1000]


def try_add_contact_to_list_basic(list_id: str, contact_email: str, label: str = "") -> dict:
    """Try BasicAuth POST /contact/ with <link rel="related">."""
    xml = build_contact_to_list_xml(contact_email, list_id)
    print(f"\n  [{label}] BasicAuth body:\n{xml}")
    status, body = send_basicauth(f"{HOST}/contact/", method="POST", body=xml)
    return {"auth": "BasicAuth", "list_id": list_id, "email": contact_email, "status": status, "body": body}


def try_add_contact_to_list_oauth(list_id: str, contact_email: str, label: str = "") -> dict:
    """Try OAuth HMAC-SHA1 POST /contact/ with <link rel="related">."""
    xml = build_contact_to_list_xml(contact_email, list_id)
    print(f"\n  [{label}] OAuth body:\n{xml}")
    status, body = send_oauth(f"{HOST}/contact/", method="POST", body=xml)
    return {"auth": "OAuth", "list_id": list_id, "email": contact_email, "status": status, "body": body}


def try_contact_link_method(list_id: str, contact_id: str, label: str = "") -> dict:
    """Try PUT /contact/{id}/ with <link rel="adds"> (Java SDK style)."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        '  <entry>\n'
        f'    <id>{contact_id}</id>\n'
        f'    <link href="{HOST}/list/{list_id}/" '
        'rel="related" '
        'title="addContacts" method="PUT" />\n'
        '  </entry>\n'
        '</feed>'
    )
    print(f"\n  [{label}] PUT body:\n{xml}")
    status, body = send_basicauth(f"{HOST}/contact/{contact_id}/", method="PUT", body=xml)
    return {"auth": "BasicAuth", "method": "PUT", "list_id": list_id, "contact_id": contact_id, "status": status, "body": body}


def try_list_post_contact(list_id: str, contact_email: str, label: str = "") -> dict:
    """Try POST /list/{id}/ with contact entry."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<entry xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        f'  <email>{html.escape(contact_email)}</email>\n'
        '</entry>'
    )
    print(f"\n  [{label}] POST /list/{{id}}/ body:\n{xml}")
    status, body = send_basicauth(f"{HOST}/list/{list_id}/", method="POST", body=xml)
    return {"auth": "BasicAuth", "list_id": list_id, "email": contact_email, "status": status, "body": body}


def main():
    # Test list IDs from the previous session
    test_list_id = "349611"

    print(f"=== Unimarketing Add Contact to List Test ===\n")
    print(f"List ID: {test_list_id}")
    print(f"Contacts: {[c['email'] for c in CONTACTS]}")

    # Step 1: Verify list exists
    print(f"\n--- Step 1: Verify list {test_list_id} exists ---")
    status, body = list_exists(test_list_id)
    print(f"  GET /list/{test_list_id}/ -> {status}")
    if status == 200:
        print(f"  List exists: {body[:200]}")
    else:
        print(f"  Error: {body}")

    # Step 2: Get contact details to see current list membership
    print(f"\n--- Step 2: Get contact details ---")
    for c in CONTACTS:
        status, body = get_contact(c["contact_id"])
        print(f"  Contact {c['contact_id']} ({c['email']}): status={status}")
        # Check if there's a <link> to a list in the response
        if "<link" in body:
            print(f"  Links found in response")

    # Step 3: Try OAuth HMAC-SHA1 (C# SDK style) — this is new
    print(f"\n--- Step 3: OAuth HMAC-SHA1 add to list ---")
    oauth_results = []
    for c in CONTACTS:
        result = try_add_contact_to_list_oauth(test_list_id, c["email"], label=f"OAuth contact={c['contact_id']}")
        oauth_results.append(result)
        print(f"  -> {result['status']}: {result['body'][:200]}")

    # Step 4: Try BasicAuth (confirm previous 500)
    print(f"\n--- Step 4: BasicAuth add to list (confirm 500) ---")
    basic_results = []
    for c in CONTACTS:
        result = try_add_contact_to_list_basic(test_list_id, c["email"], label=f"Basic contact={c['contact_id']}")
        basic_results.append(result)
        print(f"  -> {result['status']}: {result['body'][:200]}")

    # Step 5: After each batch, check if contacts are now in the list
    print(f"\n--- Step 5: Check list after OAuth attempt ---")
    status, body = list_exists(test_list_id)
    print(f"  GET /list/{test_list_id}/ -> {status}")
    print(f"  Response: {body[:500]}")

    # Step 6: Check if contacts have list links after 500
    print(f"\n--- Step 6: Check contact details after attempts ---")
    for c in CONTACTS:
        status, body = get_contact(c["contact_id"])
        print(f"\n  Contact {c['contact_id']} ({c['email']}): status={status}")
        print(f"  Full response:")
        # Print more of the response to see list links
        print(f"  {body[:2000]}")

    # Summary
    print(f"\n=== Summary ===")
    all_results = oauth_results + basic_results
    for r in all_results:
        print(f"  {r['auth']} + link={r['list_id']} + {r.get('email', r.get('contact_id', ''))}: {r['status']}")


if __name__ == "__main__":
    main()
