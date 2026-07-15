"""
EML to MSG Converter — Convert .eml to .msg preserving nested RFC822 attachments.

Uses win32com to create Outlook MailItems and SaveAs .msg.
Only top-level parts are processed: HTML body, file attachments, and
message/rfc822 (forwarded emails). Nested RFC822 chains are NOT walked into.

Usage:
    python eml_to_msg.py <path/to/email.eml>
    # Outputs <path/to/email.msg> in same directory
"""
import os
import re
import sys
import email as email_lib


def decode_subject(raw_subject):
    """Decode RFC 2047 encoded-word subject to readable string."""
    try:
        decoded = email_lib.header.decode_header(raw_subject or "")
        parts = []
        for text, charset in decoded:
            if isinstance(text, bytes):
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(text)
        return "".join(parts)
    except Exception:
        return raw_subject or "unnamed"


def _decode_payload(part):
    """Decode a MIME part's payload using its declared charset.

    Tries the declared charset first, then falls back to utf-8, gb18030, latin-1.
    Always returns a Unicode string.
    """
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset()
    for enc in [charset, "utf-8", "gb18030", "latin-1"]:
        try:
            return payload.decode(enc or "utf-8")
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def _top_level_parts(msg):
    """Yield top-level MIME parts without descending into message/rfc822.

    Recurses into multipart containers (mixed, related, alternative) but
    yields message/rfc822 as a leaf — does not walk into them.
    """
    if msg.is_multipart():
        for sub in msg.get_payload() or []:
            if isinstance(sub, email_lib.message.Message):
                ct = sub.get_content_type()
                if ct == "message/rfc822":
                    yield sub
                else:
                    yield from _top_level_parts(sub)
            else:
                yield sub
    else:
        yield msg


def eml_to_msg(eml_path):
    """Convert an .eml file to .msg, preserving nested RFC822 messages as .msg attachments.

    Args:
        eml_path: Path to the .eml file.

    Returns:
        Path to the created .msg file, or None on failure.
    """
    import pythoncom
    import win32com.client
    import tempfile
    import shutil

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        msg_path = _convert(eml_path, outlook, tempfile, shutil)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return None
    finally:
        pythoncom.CoUninitialize()

    return msg_path


def _convert(eml_path, outlook, tempfile, shutil):
    """Do the actual conversion given an Outlook.Application object."""
    with open(eml_path, "rb") as f:
        mime = f.read()
    emsg = email_lib.message_from_bytes(mime)

    # ---- Collect top-level parts only (no RFC822 descent) ----

    # HTML body: first text/html without filename
    html_body = ""
    # RFC822 parts (forwarded/attached emails)
    rfc822_parts = []
    # File attachments (e.g. inline images — already in HTML via cid, skip)

    for part in _top_level_parts(emsg):
        ct = part.get_content_type()
        if ct == "text/html" and not part.get_filename():
            if not html_body:
                html_body = _decode_payload(part)
        elif ct == "message/rfc822":
            rfc822_parts.append(part)

    # ---- Convert each RFC822 to a .msg attachment ----

    temp_dir = tempfile.mkdtemp(prefix="eml2msg_")
    nested_data = []

    try:
        for sub_msg in rfc822_parts:
            # The RFC822 part's payload is the raw sub-email
            payload = sub_msg.get_payload(decode=False)
            if isinstance(payload, list):
                sub = payload[0] if payload else None
            else:
                sub = payload
            if not isinstance(sub, email_lib.message.Message):
                continue

            raw_subject = sub.get("Subject", "")
            decoded = decode_subject(raw_subject)

            # Clean control characters and collapse whitespace
            clean = re.sub(r"[\x00-\x1f]", " ", decoded)
            clean = re.sub(r"\s+", " ", clean).strip()

            # Get HTML body of nested email (also top-level only)
            sub_html = ""
            for sp in _top_level_parts(sub):
                sct = sp.get_content_type()
                if sct == "text/html" and not sp.get_filename():
                    if not sub_html:
                        sub_html = _decode_payload(sp)

            # Create .msg for this nested email
            sub_mail = outlook.CreateItem(0)
            sub_mail.Subject = clean
            sub_mail.To = sub.get("To", "")
            sub_mail.CC = sub.get("Cc", "")
            if sub_html:
                sub_mail.HTMLBody = sub_html

            safe = re.sub(r"[/\\:*?\"<>|]", "_", clean[:100])
            safe = safe.rstrip(".").strip() or "unnamed"
            msg_fn = os.path.join(temp_dir, safe + ".msg")
            sub_mail.SaveAs(msg_fn, 3)
            if not os.path.isfile(msg_fn):
                raise RuntimeError(f"SaveAs did not create file: {msg_fn}")
            sub_mail.Close(0)

            nested_data.append((clean, msg_fn))
            print(f"[EML2MSG] nested: {safe}.msg ({os.path.getsize(msg_fn) / 1024:.0f} KB)")

        # ---- Build outer mail ----

        mail = outlook.CreateItem(0)
        mail.Subject = emsg.get("Subject", "")
        mail.To = emsg.get("To", "")
        mail.CC = emsg.get("Cc", "")
        if html_body:
            mail.HTMLBody = html_body

        for decoded, msg_fn in nested_data:
            mail.Attachments.Add(msg_fn)

        # Output path: same directory, .msg extension (must be absolute)
        eml_abs = os.path.abspath(eml_path)
        base, _ = os.path.splitext(eml_abs)
        msg_path = base + ".msg"
        mail.SaveAs(msg_path, 3)
        print(f"[EML2MSG] saved: {os.path.basename(msg_path)} ({os.path.getsize(msg_path) / 1024:.0f} KB)")
        mail.Close(0)

        return msg_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python eml_to_msg.py <path/to/email.eml>", file=sys.stderr)
        sys.exit(1)

    # Ensure stdout can handle UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    eml_path = sys.argv[1]
    if not os.path.isfile(eml_path):
        print(f"[ERROR] File not found: {eml_path}", file=sys.stderr)
        sys.exit(1)

    msg_path = eml_to_msg(eml_path)
    if msg_path is None:
        sys.exit(1)

    # Verify with extract-msg
    try:
        from extract_msg import Message as MsgParser

        m = MsgParser(msg_path)
        print(f"[EML2MSG] verified: {len(m.attachments)} attachments")
        for att in m.attachments:
            print(f"  {att.getFilename()}")
        m.close()
    except ImportError:
        pass


if __name__ == "__main__":
    main()
