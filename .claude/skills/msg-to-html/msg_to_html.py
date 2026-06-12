"""
Convert Outlook .msg files to HTML code.

Uses win32com to open .msg via Outlook, extracts the raw HTMLBody.
Uses GetShortPathName to handle Chinese filename paths that cause COM errors.
Also supports --word-html to export the full Word-format HTML via WordEditor.
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

    try:
        msg.Close(0)  # 0 = olDiscard
    except Exception:
        pass

    pythoncom.CoUninitialize()

    return html_body


def msg_to_word_html(msg_path, output_path):
    """Open a .msg file via Outlook COM, use WordEditor.SaveAs2 to export full Word HTML."""
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
    try:
        msg = namespace.OpenSharedItem(short_path)
    except Exception as e:
        print(f"Error: could not open .msg file: {e}", file=sys.stderr)
        pythoncom.CoUninitialize()
        sys.exit(1)

    try:
        inspector = msg.GetInspector
        word_doc = inspector.WordEditor
        # wdFormatHTML = 8 (Word 97-2003 HTML with full Word markup)
        word_doc.SaveAs2(output_path, 8)
    except Exception as e:
        print(f"Error: WordEditor failed: {e}", file=sys.stderr)
        try:
            msg.Close()  # olPromptForSaveChanges
        except Exception:
            pass
        pythoncom.CoUninitialize()
        sys.exit(1)

    # Cleanup: WordEditor doc from shared .msg is read-only, Close may fail
    try:
        word_doc.Close(0)  # 0 = wdDoNotSaveChanges
    except Exception:
        pass

    try:
        msg.Close(0)  # 0 = olDiscard
    except Exception:
        pass

    pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(
        description="Convert Outlook .msg to HTML for copy-paste into RTF email systems."
    )
    parser.add_argument("input", help="Path to source .msg file")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="Path to output HTML file (default: same name with .html extension)",
    )
    parser.add_argument(
        "--word-html", action="store_true",
        help="Export full Word-format HTML via WordEditor (includes header/footer, company logo etc.)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    output_path = os.path.abspath(
        args.output if args.output else os.path.splitext(args.input)[0] + ".html"
    )

    if args.word_html:
        msg_to_word_html(os.path.abspath(args.input), output_path)
        # WordEditor.SaveAs2 produces UTF-16 LE, convert to UTF-8 for web use
        with open(output_path, "r", encoding="utf-16") as f:
            content = f.read()
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    else:
        html_content = msg_to_html(os.path.abspath(args.input))
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(html_content)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"HTML saved to: {output_path}")
    print(f"Encoding: utf-8")
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()