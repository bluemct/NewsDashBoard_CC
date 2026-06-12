"""
Unimarketing API — Create an email (message) from HTML content

Creates a message draft in the Unimarketing platform. This does NOT send the email.
The email is saved to the specified folder and can be previewed/sent from the Unimarketing web UI.

Auth: BasicAuth(API_KEY, API_SECRET) + Authorization: OAuth
Body: Atom XML entry with title, um:header, um:footer, content, and link (folder).
"""
import argparse
import re
import sys
import xml.sax.saxutils as sax

import requests
from requests.auth import HTTPBasicAuth

HOST = "http://services.unimarketing.com.cn"
API_KEY = "customersupport"
API_SECRET = "/CUkafFTgALhtSSZn9KcZ1hw4lI="


def _clean_word_html(raw: str) -> str:
    """Light cleanup of Word HTML - keep structure, remove only broken tags."""
    clean = raw
    # Remove empty mso-bookmark spans (no content to preserve)
    clean = re.sub(r"<span[^>]*mso-bookmark[^>]*>\s*</span>", "", clean)
    clean = re.sub(r"<span[^>]*_MailOriginal[^>]*>\s*</span>", "", clean)
    # Remove empty o:p tags
    clean = re.sub(r"<o:p>\s*</o:p>", "", clean)
    return clean


def _extract_body(html: str) -> str:
    """Return the full HTML document as-is (not just body)."""
    return html


def _build_message_xml(
    title: str,
    html_content: str,
    folder_url: str,
    language: str = "zh_CN",
    trigger_type: str = "normal",
    include_header_footer: str = "2",
) -> str:
    """Build Atom XML for POST /message/ request."""
    # Escape HTML < > & so they survive the outer XML + inner CDATA parsing
    escaped_content = sax.escape(html_content)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<entry xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:um="http://www.unimarketing.com.cn/xmlns/">\n'
        f'  <title type="text">{sax.escape(title)}</title>\n'
        '  <um:header align="left"></um:header>\n'
        '  <um:footer align="left"></um:footer>\n'
        f'  <um:isContainPageHeadFooter>{include_header_footer}</um:isContainPageHeadFooter>\n'
        f'  <um:language>{language}</um:language>\n'
        f'  <um:triggerType>{trigger_type}</um:triggerType>\n'
        '  <content type="text" xml:base="http://www.unimarketing.com.cn/xmlns/">'
        '&lt;![CDATA[ '
        + escaped_content
        + ' ]]&gt;'
        '</content>\n'
        f'  <link href="{folder_url}" rel="related"></link>\n'
        '</entry>'
    )


def create_message(
    title: str,
    html_content: str,
    folder_url: str,
    language: str = "zh_CN",
    trigger_type: str = "normal",
    include_header_footer: str = "2",
    verbose: bool = False,
) -> dict:
    """Create a message (email draft) via POST /message/. Returns result dict."""
    xml_body = _build_message_xml(
        title, html_content, folder_url, language, trigger_type, include_header_footer
    )

    if verbose:
        print(f"XML body:\n{xml_body}\n")

    headers = {
        "Content-Type": "application/atom+xml; charset=utf-8",
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

    resp = requests.post(
        f"{HOST}/message/",
        params={"apikey": API_KEY, "method": "post", "alt": "atom"},
        headers=headers,
        auth=HTTPBasicAuth(API_KEY, API_SECRET),
        data=xml_body.encode("utf-8"),
        timeout=60,
    )

    if resp.status_code in (200, 201):
        return {"success": True, "title": title, "status_code": resp.status_code, "response": resp.text}
    else:
        try:
            error_msg = resp.content.decode("utf-8", errors="replace")
        except Exception:
            error_msg = resp.text
        return {"success": False, "title": title, "status_code": resp.status_code, "error": error_msg}


def list_folders(verbose: bool = False) -> list:
    """List available email folders via GET /folder/."""
    headers = {
        "Accept": "application/atom+xml",
        "Authorization": "OAuth",
    }

    resp = requests.get(
        f"{HOST}/folder/",
        params={"apikey": API_KEY, "alt": "atom", "max-results": "50"},
        headers=headers,
        auth=HTTPBasicAuth(API_KEY, API_SECRET),
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"Failed to list folders: {resp.status_code}")
        return []

    import xml.etree.ElementTree as ET

    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    folders = []
    for entry in root.findall("atom:entry", ns):
        id_el = entry.find("atom:id", ns)
        title_el = entry.find("atom:title", ns)
        folders.append({
            "id": id_el.text if id_el is not None else "",
            "title": title_el.text if title_el is not None else "",
        })
        if verbose:
            print(f"  {folders[-1]['title']} — {folders[-1]['id']}")
    return folders


def main():
    parser = argparse.ArgumentParser(description="Unimarketing API — Create Email (Message Draft)")
    parser.add_argument("--html-file", help="Path to an HTML file to use as email body")
    parser.add_argument("--html-content", help="Inline HTML content for email body")
    parser.add_argument("--title", required=True, help="Email title/name")
    parser.add_argument("--folder", default="14409", help="Folder ID (default: 14409 = Azure)")
    parser.add_argument("--language", default="zh_CN", choices=["zh_CN", "en_US"], help="Language (default: zh_CN)")
    parser.add_argument("--trigger-type", default="normal", choices=["normal", "transaction"], help="Email type")
    parser.add_argument("--no-header-footer", action="store_true", help="Disable page header/footer (default: enabled)")
    parser.add_argument("--header-footer", action="store_true", help="Enable platform page header/footer wrapper")
    parser.add_argument("--list-folders", action="store_true", help="List available folders and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print request XML")
    args = parser.parse_args()

    if args.list_folders:
        print("Available folders:")
        folders = list_folders(verbose=True)
        print(f"\nTotal: {len(folders)} folders")
        return

    folder_url = f"http://services.unimarketing.com.cn/folder/{args.folder}"

    if args.html_file:
        with open(args.html_file, encoding="utf-8") as f:
            raw_html = f.read()
        # Extract and clean the body content
        body = _extract_body(raw_html)
        html_content = _clean_word_html(body)
    elif args.html_content:
        html_content = args.html_content
    else:
        parser.error("Must provide either --html-file or --html-content")
        return

    include_header_footer = "2" if args.no_header_footer else "1"

    result = create_message(
        title=args.title,
        html_content=html_content,
        folder_url=folder_url,
        language=args.language,
        trigger_type=args.trigger_type,
        include_header_footer=include_header_footer,
        verbose=args.verbose,
    )

    if result["success"]:
        print(f"SUCCESS: Created message '{args.title}' (status {result['status_code']})")
        print(f"Response: {result['response']}")
    else:
        print(f"FAILED: {result['status_code']} — {result.get('error', '')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
