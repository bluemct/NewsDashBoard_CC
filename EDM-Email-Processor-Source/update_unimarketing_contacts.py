"""
Update Unimarketing contacts from EDM CSV.

Reads a formal_*.csv file, maps Token1~Token15 to API field names,
and calls POST /contact/ for each email.

Usage:
    python update_unimarketing_contacts.py "path/to/formal_*.csv"
"""
import csv
import os
import sys
import base64
import urllib.request
import urllib.error

# Token column (lowercase) -> API attribute name (letters only)
TOKEN_MAP = {
    "token1": "Token",
    "token2": "TokenT",
    "token3": "TokenH",
    "token4": "TokenF",
    "token5": "TokenI",
    "token6": "TokenS",
    "token7": "TokenE",
    "token8": "TokenG",
    "token9": "TokenN",
    "token10": "TokenTEN",
    "token11": "TokenL",
    "token12": "TokenW",
    "token13": "TokenR",
    "token14": "TokenO",
    "token15": "TokenV",
}

API_HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
# Get API_SECRET from environment, or use the default path
API_SECRET = os.environ.get("UM_API_SECRET", "/CUkafFTgALhtSSZn9KcZ1hw4lI=")

ENDPOINT = f"{API_HOST}/contact/?apikey={API_KEY}&method=post&alt=atom"


def _build_xml(email: str, tokens: dict) -> str:
    """Build Atom Feed XML — always includes all 15 token fields (empty string if missing)."""
    attrs = []
    for col_lower, api_name in TOKEN_MAP.items():
        value = tokens.get(col_lower, "").strip()
        if not value:
            continue
        # Escape XML special characters
        value = (value.replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;")
                      .replace("'", "&apos;")
                      .replace("\"", "&quot;"))
        attrs.append(f'    <um:attribute name="{api_name}">{value}</um:attribute>')
    attrs_xml = "\n".join(attrs)
    email_escaped = email.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:um="http://www.unimarketing.com.cn/xmlns/">
  <entry>
    <email>{email_escaped}</email>
{attrs_xml}
  </entry>
</feed>'''


def _send(email: str, xml: str) -> int:
    """Send POST /contact/ and return HTTP status code."""
    data = xml.encode("utf-8")
    creds = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    req = urllib.request.Request(
        ENDPOINT, data=data, method="POST",
        headers={
            "Content-Type": "application/atom+xml; charset=utf-8",
            "Authorization": f"Basic {creds}",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError as e:
        print(f"  CONNECTION ERROR: {e.reason}", file=sys.stderr)
        return -1


def update_contacts(csv_path: str, dry_run: bool = False) -> None:
    if not API_SECRET:
        print("Error: set UM_API_SECRET or update the default", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, encoding="gb18030", newline="") as f:
        reader = list(csv.reader(f))
    header = [c.strip().lower() for c in reader[0]]
    rows = reader[1:]

    email_idx = None
    for i, col in enumerate(header):
        if col == "email":
            email_idx = i
            break
    if email_idx is None:
        print("Error: no 'Email' column found in CSV", file=sys.stderr)
        sys.exit(1)

    total = len(rows)
    success = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        email = row[email_idx].strip() if email_idx < len(row) else ""
        if not email:
            print(f"  [{i}/{total}] SKIP (empty email)")
            continue

        # Build token dict from this row
        tokens = {}
        for j, col in enumerate(header):
            if col in TOKEN_MAP and j < len(row):
                tokens[col] = row[j].strip()

        if not tokens:
            print(f"  [{i}/{total}] {email} — SKIP (no tokens)", file=sys.stderr)
            success += 1
            continue

        xml = _build_xml(email, tokens)

        if dry_run:
            print(f"  [{i}/{total}] DRY-RUN {email} ({len(tokens)} tokens)")
            success += 1
            continue

        status = _send(email, xml)
        if status == 201:
            print(f"  [{i}/{total}] OK {email}")
            success += 1
        else:
            print(f"  [{i}/{total}] FAIL {email} (HTTP {status})", file=sys.stderr)
            failed += 1

    print(f"\nDone: {success} ok, {failed} failed, {total} total")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        csv_path = sys.argv[2] if len(sys.argv) >= 3 else None
        dry_run = True
    else:
        csv_path = sys.argv[1] if len(sys.argv) >= 2 else None
        dry_run = False

    if not csv_path or not os.path.isfile(csv_path):
        print(f"Usage: python {sys.argv[0]} [--dry-run] <path/to/formal_*.csv>", file=sys.stderr)
        sys.exit(1)

    update_contacts(csv_path, dry_run=dry_run)
