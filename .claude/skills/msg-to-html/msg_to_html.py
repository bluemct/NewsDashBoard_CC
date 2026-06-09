"""
Convert Outlook .msg files to HTML code.

Uses Win32COM to open .msg files via Outlook, extracts the HTMLBody
(raw, with all Outlook formatting), adds a subject line matching
Outlook's style, and outputs HTML with charset=unicode.

Output preserves the original HTMLBody exactly — no character
replacements, no style stripping, no bloat removal. Only PUA
(Private Use Area) font icon characters are removed.
"""
import argparse
import os
import sys


def clean_html(text):
    """Remove PUA characters (font icons) only. Preserve all other content."""
    return "".join(
        c for c in text
        if not (0xE000 <= ord(c) <= 0xF8FF or 0xF0000 <= ord(c) <= 0xF04FF)
    )


def save_html(content, path):
    content = clean_html(content)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)


def msg_to_html(msg_path):
    """Open a .msg file via Outlook COM, extract HTMLBody with subject line."""
    import win32com.client

    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNameSpace("MAPI")

    msg = namespace.OpenSharedItem(msg_path)

    if not msg:
        print("Error: could not open .msg file.", file=sys.stderr)
        sys.exit(1)

    subject = msg.Subject or ""

    # Get HTML body — preserve exactly as-is
    html_body = msg.HTMLBody or ""

    if not html_body:
        text_body = msg.Body or ""
        if text_body:
            lines = []
            for line in text_body.split("\n"):
                lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            html_body = "<br>".join(lines)

    # Add subject line at the top, matching Outlook's style
    safe_subject = subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    subject_block = f"""<p class=MsoNormal><b><span lang=ZH-CN
style='font-family:等线;mso-hansi-font-family:Calibri;mso-bidi-font-family:等线;
color:black'>主题</span></b><span style='font-family:等线;mso-hansi-font-family:Calibri;
mso-bidi-font-family:等线;color:black'>: {safe_subject}</span></p>

<p class=MsoNormal><o:p>&nbsp;</o:p></p>
"""

    # Strip the outer <html> wrapper from html_body and prepend subject
    # The raw HTMLBody starts with <html ...> <head> <body> ... </body> </html>
    # We remove the <html> and <head> wrapper, keep <body> content, and insert subject
    html_body_stripped = html_body

    # Output: <html ...> (keep original xmlns), insert subject before body content
    # Find the original <body> tag
    body_tag_pos = html_body_stripped.lower().find('<body')
    if body_tag_pos > 0:
        # Keep everything from the opening <body> tag to the end,
        # insert subject line right after <body ...>
        html_content = html_body_stripped
        # Find end of body tag (the closing >)
        body_close = html_body_stripped.find('>', body_tag_pos)
        if body_close > 0:
            before_body = html_body_stripped[:body_close+1]
            after_body = html_body_stripped[body_close+1:]
            html_content = before_body + "\n" + subject_block + after_body
    else:
        # No body tag found, just prepend subject
        html_content = subject_block + html_body_stripped

    return html_content


def main():
    parser = argparse.ArgumentParser(
        description="Convert Outlook .msg to HTML for copy-paste into RTF email systems."
    )
    parser.add_argument("input", help="Path to source .msg file")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="Path to output HTML file (default: same name with .html extension)"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    html_content = msg_to_html(os.path.abspath(args.input))

    output_path = os.path.abspath(args.output if args.output else os.path.splitext(args.input)[0] + ".html")
    save_html(html_content, output_path)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"HTML saved to: {output_path}")
    print(f"Encoding: utf-8 (charset=unicode)")
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
