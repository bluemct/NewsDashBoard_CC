"""
Unimarketing API — Systematic test of addContacts from Java SDK

Based on the Java SDK pattern, try variations of:
- link title: "addContacts" vs "related" vs list title
- link href: with/without trailing slash, full URL vs relative
- link rel: "related" vs "http://api.unimarketing.com/rel/addContact"
- Entry vs Feed wrapper
- Different method=query params
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

list_id = "349611"
c1_email = "ma.chuntao@oe.21vianet.com"
c1_id = "241875793"


def try_label(label, method, url, body, extra_params=None):
    p = dict(params)
    if extra_params:
        p.update(extra_params)
    try:
        r = requests.request(
            method, url,
            params=p, headers=headers, auth=auth,
            data=body.encode("utf-8"),
            timeout=30,
        )
        text = r.text[:300]
        print(f"  {label}: {r.status_code} — {text}")
        return r
    except Exception as e:
        print(f"  {label}: ERROR — {e}")
        return None


def check():
    r = requests.get(f"{HOST}/contact/{c1_id}/", params={"apikey": API_KEY, "alt": "atom"},
                     headers={"Accept": "application/atom+xml", "Authorization": "OAuth"},
                     auth=auth, timeout=30)
    return list_id in r.text


def main():
    print("=== Java SDK addContacts Pattern Test ===\n")
    print(f"List: {list_id}, Contact: {c1_email}\n")

    # Baseline
    print(f"Contact in list before: {check()}\n")

    print("--- Variation 1: href without trailing slash ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_label("no trailing slash", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 2: relative href ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="/list/{list_id}/" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_label("relative href", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 3: with <id> element ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <id>{HOST}/contact/{c1_id}</id>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_label("with <id>", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 4: um:addContacts as attribute ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <um:addContacts>{HOST}/list/{list_id}/</um:addContacts>
  </entry>
</feed>'''
    try_label("um:addContacts attr", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 5: POST to /contactimport/ with list ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
  </entry>
</feed>'''
    try_label("/contactimport/ + list=", "POST", f"{HOST}/contactimport/", xml,
              extra_params={"type": "addContacts", "list": list_id})
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 6: POST to /contactimport/ with contact-type ---")
    try_label("/contactimport/ + type=contact", "POST", f"{HOST}/contactimport/", xml,
              extra_params={"type": "contact", "list": list_id})
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 7: POST to /contactimport/ with feed + list in XML ---")
    xml2 = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related"/>
  </entry>
</feed>'''
    try_label("/contactimport/ + link", "POST", f"{HOST}/contactimport/", xml2,
              extra_params={"type": "addContacts"})
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 8: POST /contact/ with link type=application/atom+xml ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts" type="application/atom+xml"/>
  </entry>
</feed>'''
    try_label("link with type=", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 9: POST with <source> ref to list ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <source>
      <link href="{HOST}/list/{list_id}/" rel="related"/>
    </source>
  </entry>
</feed>'''
    try_label("source + link", "POST", f"{HOST}/contact/", xml)
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 10: POST with method param=put ---")
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{sax.escape(c1_email)}</email>
    <link href="{HOST}/list/{list_id}/" rel="related" title="addContacts"/>
  </entry>
</feed>'''
    try_label("method=put param", "POST", f"{HOST}/contact/", xml,
              extra_params={"method": "put"})
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 11: POST /contact/?rel=list ---")
    try_label("rel=list param", "POST", f"{HOST}/contact/", xml,
              extra_params={"rel": "list"})
    print(f"  Contact in list: {check()}\n")

    print("--- Variation 12: POST /contact/ with X-Rel header ---")
    try:
        h = dict(headers)
        h["X-Rel"] = f"{HOST}/list/{list_id}/"
        r = requests.request(
            "POST", f"{HOST}/contact/",
            params=params, headers=h, auth=auth,
            data=xml.encode("utf-8"),
            timeout=30,
        )
        print(f"  X-Rel header: {r.status_code} — {r.text[:300]}")
        print(f"  Contact in list: {check()}\n")
    except Exception as e:
        print(f"  X-Rel header: ERROR — {e}\n")

    # Final
    print("=== Final ===")
    print(f"Contact {c1_id} in list {list_id}: {check()}")


if __name__ == "__main__":
    main()
