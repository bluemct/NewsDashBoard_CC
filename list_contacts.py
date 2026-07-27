"""
Fetch all contacts (with attributes) from a Unimarketing list.

Uses ThreadPoolExecutor to parallelize paginated requests,
significantly faster than sequential pagination for large lists.

Usage:
  python list_contacts.py --list-id 350021
  python list_contacts.py --list-id 350021 --workers 20
  python list_contacts.py --list-id 350021 --output contacts.json
"""
import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Unimarketing API constants
# ---------------------------------------------------------------------------
HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="

ATOM_NS = "http://www.w3.org/2005/Atom"
UM_NS = "http://www.unimarketing.com.cn/xmlns/"
OS_NS = "http://a9.com/-/spec/opensearchrss/1.0/"


def _headers():
    return {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }


def _auth():
    return HTTPBasicAuth(API_KEY, API_SECRET)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _atom(tag: str) -> str:
    return "{" + ATOM_NS + "}" + tag


def parse_total(xml_str: str) -> int:
    """Extract <openSearch:totalResults> from Atom feed."""
    root = ET.fromstring(xml_str)
    el = root.find("{" + OS_NS + "}" + "totalResults")
    if el is not None and el.text:
        return int(el.text)
    return 0


def parse_contacts(xml_str: str) -> list[dict]:
    """Parse an Atom feed page, return list of contact dicts."""
    root = ET.fromstring(xml_str)
    contacts = []
    for entry in root.findall(_atom("entry")):
        c = {}

        # email
        email_el = entry.find(_atom("email"))
        if email_el is not None and email_el.text:
            c["email"] = email_el.text.strip()

        # contact_id
        id_el = entry.find(_atom("id"))
        if id_el is not None:
            c["contact_id"] = id_el.text.rsplit("/", 1)[-1]

        # status
        status_el = entry.find("{" + UM_NS + "}" + "status")
        if status_el is not None:
            c["status"] = status_el.text

        # created
        created_el = entry.find("{" + UM_NS + "}" + "created")
        if created_el is not None:
            c["created"] = created_el.text

        # um:attribute elements
        attrs = {}
        for attr in entry.findall("{" + UM_NS + "}" + "attribute"):
            name = attr.get("name", "")
            if name:
                attrs[name] = (attr.text or "").strip()
        if attrs:
            c["attributes"] = attrs

        contacts.append(c)
    return contacts


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def fetch_page(list_id: str, start_index: int, page_size: int = 50) -> list[dict]:
    """Fetch one page of contacts from a list."""
    params = {
        "apikey": API_KEY,
        "method": "get",
        "alt": "atom",
        "q": f"[email=null,status=null,listId={list_id}]",
        "max-results": str(page_size),
        "start-index": str(start_index),
    }
    resp = requests.get(
        f"{HOST}/contact/",
        params=params,
        headers=_headers(),
        auth=_auth(),
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  [WARN] HTTP {resp.status_code} at start-index={start_index}")
        return []
    return parse_contacts(resp.text)


def get_list_info(list_id: str) -> dict | None:
    """GET /list/{id}/ — return list info dict."""
    params = {"apikey": API_KEY, "method": "get", "alt": "atom"}
    resp = requests.get(
        f"{HOST}/list/{list_id}/",
        params=params,
        headers=_headers(),
        auth=_auth(),
        timeout=30,
    )
    if resp.status_code != 200:
        return None

    root = ET.fromstring(resp.content)

    def _t(tag):
        el = root.find(_atom(tag))
        return el.text.strip() if el is not None and el.text else None

    def _um(tag):
        el = root.find("{" + UM_NS + "}" + tag)
        return el.text.strip() if el is not None and el.text else None

    return {
        "title": _t("title") or "",
        "activeCount": int(_um("activeCount")) if _um("activeCount") else 0,
        "unsubscribeCount": int(_um("unsubscribeCount")) if _um("unsubscribeCount") else 0,
        "invalidateCount": int(_um("invalidateCount")) if _um("invalidateCount") else 0,
        "unconfirmCount": int(_um("unconfirmCount")) if _um("unconfirmCount") else 0,
    }


def fetch_list_contacts(
    list_id: str,
    page_size: int = 50,
    max_workers: int = 10,
) -> list[dict]:
    """
    Fetch all contacts in a list with parallel pagination.

    Returns list of dicts: [{contact_id, email, status, created, attributes}, ...]
    """
    # 1. Get total
    info = get_list_info(list_id)
    if info is None:
        print(f"Error: cannot get list info for listId={list_id}", file=sys.stderr)
        return []

    total = (
        info["activeCount"]
        + info["unsubscribeCount"]
        + info["invalidateCount"]
        + info["unconfirmCount"]
    )

    print(f"List: {info['title']}")
    print(f"Total contacts: {total}  |  Pages: {math.ceil(total / page_size)}")

    if total == 0:
        return []

    # 2. Build page start-indices
    pages = [i * page_size + 1 for i in range(math.ceil(total / page_size))]

    # 3. Fetch all pages in parallel
    contacts = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(fetch_page, list_id, si, page_size): si for si in pages
        }
        for fut in as_completed(futs):
            si = futs[fut]
            try:
                page = fut.result()
                contacts.extend(page)
            except Exception as e:
                print(f"  [ERROR] start-index={si}: {e}", file=sys.stderr)

    elapsed = time.time() - start_time
    print(f"Fetched {len(contacts)} contacts in {elapsed:.1f}s")

    return contacts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fetch all contacts from a Unimarketing list (parallel)"
    )
    parser.add_argument("--list-id", required=True, help="Unimarketing list ID")
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Max concurrent requests (default: 10)"
    )
    parser.add_argument(
        "--page-size", type=int, default=50,
        help="Results per page, max 50 (default: 50)"
    )
    parser.add_argument("--output", default=None, help="Output JSON file path")

    args = parser.parse_args()

    contacts = fetch_list_contacts(
        list_id=args.list_id,
        page_size=args.page_size,
        max_workers=args.workers,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(contacts, f, ensure_ascii=False, indent=2)
        print(f"Saved to {args.output}")
    elif contacts:
        # Print summary table
        print(f"\n{'Contact ID':.<15} {'Email':.<40} {'Attributes'}")
        print("-" * 80)
        for c in contacts[:20]:
            cid = c.get("contact_id", "")
            email = (c.get("email") or "")[:38]
            attrs = c.get("attributes", {})
            attr_keys = ", ".join(attrs.keys())[:30]
            print(f"{cid:<15} {email:<40} {attr_keys}")
        if len(contacts) > 20:
            print(f"... and {len(contacts) - 20} more (use --output to export all)")


if __name__ == "__main__":
    main()
