"""Test POST /contact/ endpoint — create a single contact and observe the response."""
import argparse
import json
import sys
import urllib.parse
from xml.etree import ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="

ATOM_NS = "http://www.w3.org/2005/Atom"
UM_NS = "http://www.unimarketing.com.cn/xmlns/"

def _headers():
    return {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

def _auth():
    return HTTPBasicAuth(API_KEY, API_SECRET)


def get_contact_by_email(email: str) -> str:
    """GET /contact/?field=email&q={email}"""
    params = {
        "apikey": API_KEY,
        "method": "get",
        "alt": "atom",
        "field": "email",
        "q": email,
    }
    url = f"{HOST}/contact/"
    resp = requests.get(url, params=params, headers=_headers(), auth=_auth(), timeout=30)
    print(f"GET {url} params={params}")
    print(f"Status: {resp.status_code}")
    print(f"Body ({len(resp.text)} chars):")
    print(resp.text[:500])
    return resp.text


def post_contact(email: str, attributes: dict) -> str:
    """Try multiple approaches to create/update a contact."""
    ET.register_namespace("", "http://www.w3.org/2005/Atom")
    ET.register_namespace("um", UM_NS)

    entry = ET.Element(f"{{{ATOM_NS}}}entry")
    email_el = ET.SubElement(entry, f"{{{ATOM_NS}}}email")
    email_el.text = email
    for name, value in attributes.items():
        if not value:
            continue
        attr = ET.SubElement(entry, f"{{{UM_NS}}}attribute")
        attr.set("name", name)
        attr.text = str(value)

    xml_body = ET.tostring(entry, encoding="unicode", xml_declaration=False)
    print(f"\n--- Entry XML ---\n{xml_body}\n--------------------")

    post_headers = {
        "Content-Type": "application/atom+xml; charset=utf-8",
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

    # --- 尝试 1: POST /contactimport/ (import endpoint) ---
    print("\n========== 尝试 1: POST /contactimport/ (Atom XML) ==========")
    url1 = f"{HOST}/contactimport/"
    resp1 = requests.post(
        url1, params={"apikey": API_KEY, "method": "post", "alt": "atom"},
        headers=post_headers, auth=_auth(),
        data=xml_body.encode("utf-8"), timeout=30
    )
    print(f"Status: {resp1.status_code}")
    print(f"Body ({len(resp1.text)} chars):")
    print(resp1.text[:1500])

    # --- 尝试 2: POST /contact/ with CSV form data ---
    print("\n\n========== 尝试 2: POST /contact/ (CSV form-data) ==========")
    csv_data = f"email,Token1\n{email},{attributes.get('Token1', '')}\n"
    form_headers = {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }
    resp2 = requests.post(
        f"{HOST}/contactimport/",
        params={"apikey": API_KEY},
        headers=form_headers,
        auth=_auth(),
        files={"file": ("test.csv", csv_data.encode("utf-8"), "text/csv")},
        data={"method": "post"},
        timeout=30
    )
    print(f"Status: {resp2.status_code}")
    print(f"Body ({len(resp2.text)} chars):")
    print(resp2.text[:1500])

    # --- 尝试 3: POST /contactimport/ with CSV as multipart ---
    print("\n\n========== 尝试 3: POST /contactimport/ (CSV multipart) ==========")
    resp3 = requests.post(
        f"{HOST}/contactimport/",
        params={"apikey": API_KEY, "method": "post"},
        headers=form_headers,
        auth=_auth(),
        files={"file": ("test.csv", csv_data.encode("utf-8"), "text/csv")},
        timeout=30
    )
    print(f"Status: {resp3.status_code}")
    print(f"Body ({len(resp3.text)} chars):")
    print(resp3.text[:1500])

    # --- 尝试 4: POST /contact/ with email as query param + CSV body ---
    print("\n\n========== 尝试 4: POST /contact/ (email in body as CSV text) ==========")
    resp4 = requests.post(
        f"{HOST}/contact/",
        params={"apikey": API_KEY, "method": "post", "email": email},
        headers={"Content-Type": "text/csv", "Authorization": "OAuth"},
        auth=_auth(),
        data=csv_data.encode("utf-8"),
        timeout=30
    )
    print(f"Status: {resp4.status_code}")
    print(f"Body ({len(resp4.text)} chars):")
    print(resp4.text[:1500])

    # --- 尝试 5: POST /contact/ with just email param (update) ---
    print("\n\n========== 尝试 5: POST /contact/ (email param, XML body with id) ==========")
    entry_with_id = ET.Element(f"{{{ATOM_NS}}}entry")
    id_el = ET.SubElement(entry_with_id, f"{{{ATOM_NS}}}id")
    id_el.text = f"http://services.unimarketing.com.cn/contact/349903623"
    email_el2 = ET.SubElement(entry_with_id, f"{{{ATOM_NS}}}email")
    email_el2.text = email
    xml_with_id = ET.tostring(entry_with_id, encoding="unicode", xml_declaration=False)
    resp5 = requests.post(
        f"{HOST}/contact/349903623/",
        params={"apikey": API_KEY, "method": "post", "alt": "atom"},
        headers=post_headers, auth=_auth(),
        data=xml_with_id.encode("utf-8"), timeout=30
    )
    print(f"Status: {resp5.status_code}")
    print(f"Body ({len(resp5.text)} chars):")
    print(resp5.text[:1500])

    return resp1.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("email", help="Test contact email")
    parser.add_argument("--token", nargs=2, action="append", metavar=("NAME", "VALUE"),
                        help="Token attribute (can repeat)")
    args = parser.parse_args()

    # First: check if contact already exists
    print("=== Step 1: Check if contact exists ===")
    get_contact_by_email(args.email)

    # Build attributes
    attributes = {}
    if args.token:
        for name, value in args.token:
            attributes[name] = value
    else:
        # Default: just Token1 with a placeholder
        attributes = {"Token1": "00000000-0000-0000-0000-000000000000, TEST-IMPORT"}

    print(f"\n=== Step 2: POST /contact/ ===")
    print(f"Email: {args.email}, Attributes: {attributes}")
    post_contact(args.email, attributes)


if __name__ == "__main__":
    main()
