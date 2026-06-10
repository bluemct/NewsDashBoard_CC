"""
Convert Outlook .msg files to HTML code.

Uses win32com to open .msg via Outlook, extracts the raw HTMLBody.
Uses GetShortPathName to handle Chinese filename paths that cause COM errors.
"""
import argparse
import ctypes
import os
import sys


def _get_short_path(long_path):
    """Convert long path (with Chinese chars) to short DOS path for COM."""
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(long_path, buf, 512)
    return buf.value


def msg_to_html(msg_path):
    """Open a .msg file via Outlook COM, return raw HTMLBody."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
    except Exception as e:
        print(f"Error: could not connect to Outlook: {e}", file=sys.stderr)
        pythoncom.CoUninitialize()
        sys.exit(1)

    short_path = _get_short_path(os.path.abspath(msg_path))
    msg = namespace.OpenSharedItem(short_path)

    if not msg:
        print("Error: could not open .msg file.", file=sys.stderr)
        pythoncom.CoUninitialize()
        sys.exit(1)

    html_body = msg.HTMLBody or ""

    msg.Close()
    pythoncom.CoUninitialize()

    return html_body


def main():
    parser = argparse.ArgumentParser(
        description="Convert Outlook .msg to HTML for copy-paste into RTF email systems."
    )
    parser.add_argument("input", help="Path to source .msg file")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="Path to output HTML file (default: same name with .html extension)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    html_content = msg_to_html(os.path.abspath(args.input))

    output_path = os.path.abspath(
        args.output if args.output else os.path.splitext(args.input)[0] + ".html"
    )
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(html_content)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"HTML saved to: {output_path}")
    print(f"Encoding: utf-8")
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()