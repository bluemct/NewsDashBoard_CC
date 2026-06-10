"""
Extract ticket/request numbers from email body text using regex.
"""
import argparse
import json
import re
import sys


COMMON_PATTERNS = {
    "Request #12345": r"Request\s*#\s*(\d+)",
    "Ticket-12345": r"Ticket[-:]?\s*(\d+)",
    "工单 12345": r"工单\s*(\d+)",
    "CASE-00123": r"CASE[-:]?\s*(\d+)",
    "Order #12345": r"Order\s*#\s*(\d+)",
    "Issue #12345": r"Issue\s*#\s*(\d+)",
}


def parse_ticket(text, pattern=None):
    """Extract ticket number from text."""
    if not pattern:
        pattern = r"Request\s*#\s*(\d+)"

    m = re.search(pattern, text)
    if m:
        return {"found": True, "number": m.group(1), "matched_pattern": pattern}

    # Try common patterns as fallback
    for name, pat in COMMON_PATTERNS.items():
        m = re.search(pat, text)
        if m:
            print(f"Matched pattern: {name}", file=sys.stderr)
            return {"found": True, "number": m.group(1), "matched_pattern": pat}

    return {"found": False, "number": None, "matched_pattern": None}


def main():
    parser = argparse.ArgumentParser(description="Extract ticket number from email text")
    parser.add_argument("--text", default=None, help="Email body text")
    parser.add_argument("--pattern", default=None, help="Custom regex pattern with capture group")
    args = parser.parse_args()

    text = args.text if args.text else sys.stdin.read()
    result = parse_ticket(text, args.pattern)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
