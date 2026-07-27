"""
Unimarketing API — Alternative approaches to add contacts to lists

After the BasicAuth 201 actually did write the contacts, try:
1. GET /list/349611/contact/ - list contacts in a list
2. POST /list/349611/contacts/ - add contacts via list endpoint
3. POST /contact/?list=349611 - query param approach
4. PUT /contact/{id}/ - with adds rel
5. POST /list/349611/ - with contact entry (different formats)
6. DELETE then re-add approach
"""
import requests
from requests.auth import HTTPBasicAuth
import xml.sax.saxutils as sax

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="

params = {"apikey": API_KEY, "method": "post", "alt": "atom"}
headers = {
    "Content-Type": "application/atom+xml; charset=utf-8",
    "Accept": "application/atom+xml",
    "Authorization": "OAuth",
}
auth = HTTPBasicAuth(API_KEY, API_SECRET)

def try_api(label, method, url, body=None, extra_params=None, extra_headers=None):
    """Try an API call and print result."""
    p = dict(params)
    if extra_params:
        p.update(extra_params)
    h = dict(headers)
    if extra_headers:
        h.update(extra_headers)

    kwargs = {"timeout": 30, "params": p, "auth": auth, "headers": h}
    if body:
        kwargs["data"] = body.encode("utf-8")

    try:
        resp = requests.request(method, url, **kwargs)
        print(f"  {label}: {resp.status_code} - {resp.text[:300]}")
        return resp.status_code, resp.text[:500]
    except Exception as e:
        print(f"  {label}: ERROR - {e}")
        return None, str(e)


def check_contact_in_list(contact_id, list_id):
    """Check if a contact has a list in its links."""
    r = requests.get(
        f"{HOST}/contact/{contact_id}/",
        params={"apikey": API_KEY, "alt": "atom"},
        headers={"Accept": "application/atom+xml", "Authorization": "OAuth"},
        auth=auth,
        timeout=30,
    )
    return list_id in r.text


def check_list_count(list_id):
    """Get the activeCount of a list."""
    r = requests.get(
        f"{HOST}/list/{list_id}/",
        params={"apikey": API_KEY, "alt": "atom"},
        headers={"Accept": "application/atom+xml", "Authorization": "OAuth"},
        auth=auth,
        timeout=30,
    )
    import re
    match = re.search(r'<um:activeCount>(\d+)</um:activeCount>', r.text)
    return int(match.group(1)) if match else None


def main():
    list_id = "349611"
    c1_email = "ma.chuntao@oe.21vianet.com"
    c1_id = "241875793"

    print("=== Unimarketing Add Contact to List — Alternative Approaches ===\n")

    # Baseline
    count_before = check_list_count(list_id)
    print(f"List {list_id} activeCount before: {count_before}\n")

    # Approach 1: GET list contacts
    print("--- Approach 1: GET contacts from list ---")
    try_api("GET /list/{id}/contact/", "GET", f"{HOST}/list/{list_id}/contact/")
    try_api("GET /list/{id}/contacts/", "GET", f"{HOST}/list/{list_id}/contacts/")

    # Approach 2: POST to list endpoint with contact entry
    print("\n--- Approach 2: POST to list endpoint ---")
    xml1 = f'''<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>{HOST}/contact/{c1_id}</id>
  <email>{sax.escape(c1_email)}</email>
</entry>'''
    try_api("POST /list/{id}/ (entry)", "POST", f"{HOST}/list/{list_id}/", body=xml1)

    xml2 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <id>{HOST}/contact/{c1_id}</id>
    <email>{sax.escape(c1_email)}</email>
  </entry>
</feed>'''
    try_api("POST /list/{id}/ (feed)", "POST", f"{HOST}/list/{list_id}/", body=xml2)

    # Approach 3: POST /contact/ with query param list=
    print("\n--- Approach 3: POST /contact/ with list= query param ---")
    xml3 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
  </entry>
</feed>'''
    try_api("POST /contact/?list=", "POST", f"{HOST}/contact/", body=xml3, extra_params={"list": list_id})

    xml4 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_api("POST /contact/ + link + list=", "POST", f"{HOST}/contact/", body=xml4, extra_params={"list": list_id})

    # Approach 4: PUT /contact/{id}/ with <link rel="adds">
    print("\n--- Approach 4: PUT /contact/{id}/ with adds ---")
    xml5 = f'''<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <id>{HOST}/contact/{c1_id}</id>
  <link href="{HOST}/list/{list_id}/" rel="adds"/>
</entry>'''
    try_api("PUT /contact/{id}/ (adds)", "PUT", f"{HOST}/contact/{c1_id}/", body=xml5)

    xml6 = f'''<entry xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts"/>
</entry>'''
    try_api("PUT /contact/{id}/ (related)", "PUT", f"{HOST}/contact/{c1_id}/", body=xml6)

    xml7 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_api("PUT /contact/{id}/ (feed)", "PUT", f"{HOST}/contact/{c1_id}/", body=xml7)

    # Approach 5: POST /contact/ with um:listName attribute
    print("\n--- Approach 5: POST /contact/ with um:listName ---")
    xml8 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <um:listName>{list_id}</um:listName>
  </entry>
</feed>'''
    try_api("POST + um:listName", "POST", f"{HOST}/contact/", body=xml8)

    xml9 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <um:list>{list_id}</um:list>
  </entry>
</feed>'''
    try_api("POST + um:list", "POST", f"{HOST}/contact/", body=xml9)

    xml10 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="http://purl.org/dc/terms/isPartOf"/>
  </entry>
</feed>'''
    try_api("POST + isPartOf rel", "POST", f"{HOST}/contact/", body=xml10)

    # Approach 6: POST with link method="PUT"
    print("\n--- Approach 6: POST with link method=PUT ---")
    xml11 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related" method="PUT" title="addContacts"/>
  </entry>
</feed>'''
    try_api("POST + method=PUT", "POST", f"{HOST}/contact/", body=xml11)

    # Approach 7: JSON content type
    print("\n--- Approach 7: JSON body ---")
    import json
    jbody = json.dumps({"email": c1_email, "list": list_id})
    try_api("POST JSON", "POST", f"{HOST}/contact/", body=jbody,
            extra_headers={"Content-Type": "application/json"})

    # Check result
    count_after = check_list_count(list_id)
    in_list = check_contact_in_list(c1_id, list_id)
    print(f"\n=== Result ===")
    print(f"List {list_id} activeCount: {count_before} -> {count_after}")
    print(f"Contact {c1_id} in list: {in_list}")


if __name__ == "__main__":
    main()
