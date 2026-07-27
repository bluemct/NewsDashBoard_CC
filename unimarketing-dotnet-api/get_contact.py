"""
Unimarketing API client — Python port using BasicAuth + query params.

Auth pattern:
  URL: {HOST}/{endpoint}/?apikey={API_KEY}&method=get&alt=atom
  Headers: Authorization: OAuth, Accept: application/atom+xml
  BasicAuth: username=API_KEY, password=API_SECRET
"""
import argparse
import csv
import json
import urllib.parse
from xml.etree import ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

# ==================== 配置参数 ====================
HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="
# ================================================

ATOM_NS = "http://www.w3.org/2005/Atom"
UM_NS = "http://www.unimarketing.com.cn/xmlns/"


def _headers():
    return {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }


def _auth():
    return HTTPBasicAuth(API_KEY, API_SECRET)


def api_get(endpoint: str, extra: dict | None = None) -> str:
    """GET request to Unimarketing API."""
    params = {
        "apikey": API_KEY,
        "method": "get",
        "alt": "atom",
    }
    if extra:
        params.update(extra)
    url = f"{HOST}/{endpoint}/"
    resp = requests.get(url, params=params, headers=_headers(), auth=_auth(), timeout=30)
    resp.raise_for_status()
    return resp.text


# ==================== Get Account ====================

def get_account() -> dict:
    """GET /account/ — retrieve account information."""
    xml = api_get("account")
    return _parse_account(xml)


def _parse_account(xml_str: str) -> dict:
    root = ET.fromstring(xml_str)
    result = {}

    def _tag_name(el):
        """Strip namespace, return short tag name."""
        if el.tag.startswith("{"):
            return el.tag.split("}", 1)[1]
        return el.tag

    id_el = root.find("{*}id")
    if id_el is not None:
        result["account_id"] = id_el.text.rsplit("/", 1)[-1]
    title = root.find("{*}title")
    if title is not None:
        result["company_name"] = title.text

    for child in root:
        tag = _tag_name(child)
        if tag == "email" and child.text:
            result["email"] = child.text.strip()
        elif tag == "attribute":
            name = child.get("name", "")
            if name:
                result[name] = (child.text or "").strip()
        elif tag not in ("id", "title", "updated", "email", "link"):
            if child.text:
                # Prefix with 'um_' for um:namespace elements
                if child.tag.startswith(UM_NS):
                    result[f"um_{tag}"] = child.text.strip()

    return result


# ==================== Get Contact ====================

def get_contact(contact_id_or_email: str) -> list[dict]:
    """
    Get contact by ID:  /contact/{id}/
    Get contact by email: /contact/?field=email&q={email}
    """
    if contact_id_or_email.isdigit():
        xml = api_get(f"contact/{contact_id_or_email}")
    else:
        xml = api_get("contact", {"field": "email", "q": contact_id_or_email})
    return _parse_contact_feed(xml)


def list_contacts(max_results: int = 100, start_index: int = 1) -> list[dict]:
    """GET /contact/ — list all contacts."""
    params = {
        "max-results": str(max_results),
        "start-index": str(start_index),
    }
    xml = api_get("contact", params)
    return _parse_contact_feed(xml)


def _parse_contact_feed(xml_str: str) -> list[dict]:
    root = ET.fromstring(xml_str)
    contacts = []

    # Find entries
    entries = root.findall(f"{{{ATOM_NS}}}entry")
    if not entries:
        entries = root.findall("entry")
    for entry in entries:
        c = {}
        email_el = entry.find(f"{{{ATOM_NS}}}email")
        if email_el is not None and email_el.text:
            c["email"] = email_el.text.strip()

        id_el = entry.find(f"{{{ATOM_NS}}}id")
        if id_el is not None:
            c["contact_id"] = id_el.text.rsplit("/", 1)[-1]

        status_el = entry.find(f"{{{UM_NS}}}status")
        if status_el is not None:
            c["status"] = status_el.text

        created_el = entry.find(f"{{{UM_NS}}}created")
        if created_el is not None:
            c["created"] = created_el.text

        # Parse all um:attribute elements
        for attr in entry.findall(f"{{{UM_NS}}}attribute"):
            name = attr.get("name", "")
            if name:
                c[name] = (attr.text or "").strip()

        # Parse other um: fields
        for child in entry:
            tag = child.tag
            if tag.startswith(UM_NS):
                short = tag.replace(UM_NS, "")
                if short != "attribute" and child.text and short not in c:
                    c[short] = child.text.strip()

        contacts.append(c)

    return contacts


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Unimarketing API — Get Contact")
    sub = parser.add_subparsers(dest="command")

    # get-account
    sub.add_parser("get-account", help="Get account info")

    # get-contact <id_or_email>
    p1 = sub.add_parser("get-contact", help="Get contact by ID or email")
    p1.add_argument("id_or_email", help="Contact ID or email address")

    # list-contacts
    p2 = sub.add_parser("list-contacts", help="List all contacts")
    p2.add_argument("--max", type=int, default=100, help="Max results (default: 100)")
    p2.add_argument("--start", type=int, default=1, help="Start index (default: 1)")

    # export-csv
    p3 = sub.add_parser("export-csv", help="Export all contacts to CSV")
    p3.add_argument("output", help="Output CSV file path", default="contacts.csv")

    args = parser.parse_args()

    if args.command == "get-account":
        info = get_account()
        print(json.dumps(info, ensure_ascii=False, indent=2))

    elif args.command == "get-contact":
        contacts = get_contact(args.id_or_email)
        if contacts:
            for c in contacts:
                print(json.dumps(c, ensure_ascii=False, indent=2))
        else:
            print(f"No contact found for: {args.id_or_email}")

    elif args.command == "list-contacts":
        contacts = list_contacts(args.max, args.start)
        print(f"Showing {len(contacts)} contacts:")
        print(f"{'Email':.<40} {'Contact ID':.<20} {'Status':.<10}")
        print("-" * 70)
        for c in contacts:
            email = (c.get("email") or "")[:38]
            cid = c.get("contact_id") or ""
            status = c.get("status") or ""
            print(f"{email:<40} {cid:<20} {status:<10}")

    elif args.command == "export-csv":
        rows = []
        start = 1
        while True:
            contacts = list_contacts(max_results=50, start_index=start)
            if not contacts:
                break
            for c in contacts:
                rows.append([c.get("email", ""), c.get("contact_id", "")])
            print(f"  fetched {start}..{start + len(contacts) - 1} ({len(rows)} total)")
            if len(contacts) < 50:
                break
            start += len(contacts)
        with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["email", "contact_id"])
            writer.writerows(rows)
        print(f"Done — {len(rows)} contacts written to {args.output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
