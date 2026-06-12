"""
Unimarketing API — Create a single contact via POST /contact/

Auth: BasicAuth(API_KEY, API_SECRET) + Authorization: OAuth header
Body: Atom Feed wrapping Entry, with <email> and <um:attribute> children.
"""
import argparse
import json
import sys
import xml.sax.saxutils as sax

import requests
from requests.auth import HTTPBasicAuth

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="


def _build_feed(email: str, attributes: dict) -> str:
    """Build Atom Feed XML body for contact creation."""
    attrs = ""
    for name, value in attributes.items():
        if not value:
            continue
        attrs += (
            f'    <um:attribute name="{sax.escape(name)}">'
            f'{sax.escape(str(value))}</um:attribute>\n'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        '  <entry>\n'
        f'    <email>{sax.escape(email)}</email>\n'
        f'{attrs}'
        '  </entry>\n'
        '</feed>'
    )


def create_contact(email: str, attributes: dict, verbose: bool = False) -> dict:
    """Create a single contact via POST /contact/. Returns result dict."""
    xml_body = _build_feed(email, attributes)

    if verbose:
        print(f"XML body:\n{xml_body}\n")

    headers = {
        "Content-Type": "application/atom+xml; charset=utf-8",
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

    resp = requests.post(
        f"{HOST}/contact/",
        params={"apikey": API_KEY, "method": "post", "alt": "atom"},
        headers=headers,
        auth=HTTPBasicAuth(API_KEY, API_SECRET),
        data=xml_body.encode("utf-8"),
        timeout=30,
    )

    if resp.status_code == 201:
        return {"success": True, "email": email, "status_code": 201}
    elif resp.status_code == 400:
        # Server returns GBK-encoded error messages
        try:
            error_msg = resp.content.decode("gbk", errors="replace")
        except Exception:
            error_msg = resp.text
        return {"success": False, "email": email, "status_code": 400, "error": error_msg}
    else:
        return {"success": False, "email": email, "status_code": resp.status_code, "error": resp.text[:500]}


def main():
    parser = argparse.ArgumentParser(description="Unimarketing API — Create Contact")
    parser.add_argument("email", nargs="?", help="Contact email address")
    parser.add_argument(
        "--token", nargs=2, action="append", metavar=("NAME", "VALUE"),
        help="Token attribute (e.g. --token Token value1 --token TokenT value2). "
             "Name must be pure English letters only (e.g. Token, TokenT, TokenH)."
    )
    parser.add_argument("--json-input", help="JSON file with array of {email, attributes} objects")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print request XML")
    args = parser.parse_args()

    contacts_to_create = []

    if args.json_input:
        with open(args.json_input, encoding="utf-8") as f:
            for item in json.load(f):
                contacts_to_create.append({
                    "email": item["email"],
                    "attributes": item.get("attributes", {}),
                })
    elif args.email:
        attrs = {}
        if args.token:
            for name, value in args.token:
                attrs[name] = value
        contacts_to_create.append({"email": args.email, "attributes": attrs})
    else:
        parser.print_help()
        return

    results = []
    for c in contacts_to_create:
        result = create_contact(c["email"], c["attributes"], verbose=args.verbose)
        results.append(result)
        status = "OK" if result["success"] else f"FAILED ({result['status_code']}: {result.get('error', '')})"
        print(f"  {c['email']} — {status}")

    print(f"\nSummary: {sum(1 for r in results if r['success'])} created, {sum(1 for r in results if not r['success'])} failed")
    sys.exit(0 if all(r["success"] for r in results) else 1)


if __name__ == "__main__":
    main()
