"""
Convert HTML email body to plain text using COM HTMLFile object.
"""
import argparse
import sys
import win32com.client


def html_to_text(html_str):
    """Convert HTML string to plain text."""
    if not html_str or not html_str.strip():
        return ""
    try:
        doc = win32com.client.Dispatch("HTMLFile")
        doc.write(html_str)
        raw = doc.body.innerText or ""
        # Remove empty lines
        lines = [line for line in raw.split("\n") if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        print(f"HTML conversion failed: {e}", file=sys.stderr)
        return html_str


def main():
    parser = argparse.ArgumentParser(description="Convert HTML to plain text")
    parser.add_argument("--html", default=None, help="HTML string to convert")
    args = parser.parse_args()

    if args.html:
        text = html_to_text(args.html)
    else:
        text = html_to_text(sys.stdin.read())

    print(text)


if __name__ == "__main__":
    main()
