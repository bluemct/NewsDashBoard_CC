"""
EDM Email Processor — full workflow:
1. Read .msg and .xlsx from EDM/Temp/
2. Extract SN from .msg subject, create EDM/SN-xxxxx/ folder
3. Move .xlsx to SN folder and convert to CSV
4. Extract nested EDM template .msg (no-recipients one) to SN folder
5. Convert nested .msg to HTML via win32com

Usage:
    python edm_process.py
"""
import ctypes
import os
import re
import shutil
import sys

try:
    from extract_msg import Message as MsgParser
except ImportError:
    print("Error: 'extract-msg' not installed. Run: pip install extract-msg", file=sys.stderr)
    sys.exit(1)


def _get_short_path(long_path):
    """Convert long path (with Chinese chars) to short DOS path for COM."""
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(long_path, buf, 512)
    return buf.value


BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "EDM"
)
TEMP_DIR = os.path.join(BASE_DIR, "Temp")


def extract_sn(text):
    """Extract SN-12345 from any text."""
    match = re.search(r"SN-\d+", text)
    return match.group(0) if match else None


def find_target_attachment_idx(msg_path):
    """Use olefile to find the attachment index with 0 recipients in nested 3701000D."""
    import olefile

    ole = olefile.OleFileIO(msg_path)
    all_entries = ole.listdir()

    att_prefixes = set()
    _id_pattern = re.compile(r'__attach_version.+_(#0000000\d+)')
    for entry in all_entries:
        if entry and entry[0].startswith("__attach_version"):
            m = _id_pattern.search(entry[0])
            if m:
                att_prefixes.add(entry[0])

    att_list = sorted(att_prefixes, key=lambda p: re.search(r'#0000000(\d+)', p).group(1))

    for idx, prefix in enumerate(att_list):
        nested_p = f"{prefix}.__substg1.0_3701000D"
        has_recipients = False
        for e in all_entries:
            ej = ".".join(e)
            if ej.startswith(nested_p + ".") and "__recip_version" in ej:
                has_recipients = True
                break
        if not has_recipients:
            ole.close()
            return idx

    ole.close()
    return None


def save_target_attachment(att, save_dir):
    """Save the target embedded .msg attachment to save_dir."""
    fn = att.getFilename()
    if not fn:
        fn = "attached.msg"

    safe_fn = re.sub(r'[/\\:*?"<>|]', '_', fn)
    safe_fn = re.sub(r'\s+', ' ', safe_fn)

    save_path = os.path.join(save_dir, safe_fn)

    nested = att.data
    raw = nested.exportBytes()
    with open(save_path, "wb") as f:
        f.write(raw)

    sz = os.path.getsize(save_path)
    print(f"[ATTACH] saved: {safe_fn} ({sz / 1024:.1f} KB)")
    return save_path


def convert_xlsx_to_csv(xlsx_path):
    """Convert .xlsx to CSV using xlsx-to-csv skill."""
    xlsx_skill = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        ".claude", "skills", "xlsx-to-csv", "xlsx_to_csv.py",
    )
    import subprocess
    result = subprocess.run(
        [sys.executable, xlsx_skill, xlsx_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode == 0


def convert_msg_to_html(msg_path, output_html):
    """Convert .msg to HTML via win32com (Outlook HTMLBody)."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
    except Exception as e:
        print(f"Error: could not connect to Outlook: {e}", file=sys.stderr)
        pythoncom.CoUninitialize()
        return False

    short_path = _get_short_path(msg_path)
    try:
        msg = namespace.OpenSharedItem(short_path)
    except Exception as e:
        print(f"Error: could not open .msg file: {e}", file=sys.stderr)
        pythoncom.CoUninitialize()
        return False

    html_body = msg.HTMLBody or ""
    subject = msg.Subject or ""
    del msg
    pythoncom.CoUninitialize()

    if html_body:
        # Insert subject line at top of body, matching Outlook's style
        safe_subject = subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        subject_block = (
            f"<p class=MsoNormal><b><span lang=ZH-CN\n"
            f"style='font-family:等线;mso-hansi-font-family:Calibri;mso-bidi-font-family:等线;\n"
            f"color:black'>主题</span></b><span style='font-family:等线;mso-hansi-font-family:Calibri;\n"
            f"mso-bidi-font-family:等线;color:black'>: {safe_subject}</span></p>\n"
            f"\n"
            f"<p class=MsoNormal><o:p>&nbsp;</o:p></p>\n"
        )
        # Insert right after <body ...> tag
        body_pos = html_body.lower().find("<body")
        if body_pos > 0:
            body_close = html_body.find(">", body_pos)
            if body_close > 0:
                html_body = html_body[:body_close + 1] + "\n" + subject_block + html_body[body_close + 1:]

        with open(output_html, "w", encoding="utf-8", newline="") as f:
            f.write(html_body)
        size_kb = os.path.getsize(output_html) / 1024
        print(f"[HTML] saved: {os.path.basename(output_html)} ({size_kb:.1f} KB)")
        return True
    else:
        print("[HTML] no HTMLBody found", file=sys.stderr)
        return False


def process_edm():
    """Full EDM processing workflow."""
    if not os.path.isdir(TEMP_DIR):
        print(f"Error: Temp directory not found: {TEMP_DIR}", file=sys.stderr)
        sys.exit(1)

    # Find .msg and .xlsx files in Temp/
    msg_files = [f for f in os.listdir(TEMP_DIR) if f.lower().endswith('.msg')]
    xlsx_files = [f for f in os.listdir(TEMP_DIR) if f.lower().endswith('.xlsx')]

    if not msg_files:
        print("Error: no .msg file found in Temp/", file=sys.stderr)
        sys.exit(1)

    msg_file = msg_files[0]
    msg_path = os.path.join(TEMP_DIR, msg_file)
    print(f"[INPUT] {msg_file}")

    # Extract SN from subject
    msg = MsgParser(msg_path)
    subject = msg.subject or ""
    print(f"[EMAIL] Subject: {subject}")

    sn = extract_sn(subject)
    if not sn:
        sn = extract_sn(msg_path)
    if not sn:
        print("Error: no SN number found in subject or file path.", file=sys.stderr)
        msg.close()
        sys.exit(1)

    print(f"[SN] {sn}")

    # Create SN folder
    sn_folder = os.path.join(BASE_DIR, sn)
    os.makedirs(sn_folder, exist_ok=True)
    print(f"[FOLDER] {sn_folder}")

    # Copy .xlsx to SN folder and convert to CSV
    for xlsx_file in xlsx_files:
        src = os.path.join(TEMP_DIR, xlsx_file)
        dst = os.path.join(sn_folder, xlsx_file)
        shutil.copy2(src, dst)
        print(f"[COPY] {xlsx_file} -> {sn}/")
        convert_xlsx_to_csv(dst)

    # Extract nested EDM template .msg (no-recipients one)
    target_idx = find_target_attachment_idx(msg_path)
    attach_path = None
    if target_idx is not None and target_idx < len(msg.attachments):
        matched_att = msg.attachments[target_idx]
        attach_path = save_target_attachment(matched_att, sn_folder)
    else:
        print("[ATTACH] no target .msg attachment found", file=sys.stderr)

    msg.close()

    # Convert nested .msg to HTML via win32com
    if attach_path:
        html_path = os.path.join(sn_folder, "EDM_template.html")
        convert_msg_to_html(attach_path, html_path)

    print(f"\nDone — SN folder: {sn_folder}")


def main():
    process_edm()


if __name__ == "__main__":
    main()