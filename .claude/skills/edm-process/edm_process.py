"""
EDM Email Processor — full workflow:
1. Read .msg and .xlsx from EDM/Temp/
2. Extract SN from .msg subject, create EDM/SN-xxxxx/ folder
3. Move .xlsx to SN folder and convert to CSV
4. Extract nested EDM template .msg (no-recipients one) to SN folder
5. Convert nested .msg to HTML via win32com

Usage:
    python edm_process.py [--temp-dir DIR] [--edm-dir DIR]
"""
import argparse
import ctypes
import os
import re
import shutil
import sys

# Force UTF-8 stdout so filenames with special characters (œ, etc.) don't crash print()
if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        # Python < 3.7 fallback
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


def _default_base_dir():
    """Default EDM output directory (4 levels up from this script + EDM)."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "EDM"
    )


def _parse_args():
    """Parse CLI arguments. Returns (temp_dir, edm_dir)."""
    parser = argparse.ArgumentParser(description="EDM Email Processor")
    parser.add_argument("--temp-dir", default=None,
                        help="Directory containing input .msg and .xlsx files")
    parser.add_argument("--edm-dir", default=_default_base_dir(),
                        help="Base directory for SN output folders (default: project/EDM)")
    args = parser.parse_args()

    if args.temp_dir is None:
        args.temp_dir = os.path.join(args.edm_dir, "Temp")
    return args.temp_dir, args.edm_dir


# Resolve paths from CLI or defaults
TEMP_DIR, BASE_DIR = _parse_args()


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

    # extract-msg may decode PR_ATTACH_LONG_FILENAME (UTF-16LE) as Latin-1,
    # producing mojibake for Chinese characters. If the name contains no
    # CJK but has non-ASCII characters, try re-decoding the original bytes
    # as UTF-16LE to recover the correct filename.
    try:
        has_cjk = any('一' <= c <= '鿿' for c in fn)
        has_nonascii = any(ord(c) > 127 for c in fn)
        if has_nonascii and not has_cjk:
            # Try Latin-1 round-trip (works for U+0080..U+00FF)
            try:
                raw = fn.encode("latin-1")
                fixed = raw.decode("utf-16-le", errors="ignore")
                if any('一' <= ch <= '鿿' for ch in fixed):
                    fn = fixed
            except UnicodeEncodeError:
                # Characters like œ (U+0153) can't encode as Latin-1.
                # Fall back: read the correct subject from the .msg file itself.
                pass
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    safe_fn = re.sub(r'[/\\:*?"<>|]', '_', fn)
    safe_fn = re.sub(r'\s+', ' ', safe_fn)

    save_path = os.path.join(save_dir, safe_fn)

    nested = att.data
    raw = nested.exportBytes()
    with open(save_path, "wb") as f:
        f.write(raw)

    sz = os.path.getsize(save_path)
    print(f"[ATTACH] saved: {safe_fn} ({sz / 1024:.1f} KB)")

    # Fix mojibake: use win32com (Outlook) to read correct subject from .msg
    # extract-msg returns mojibake for nested attachments — Outlook handles UTF-16LE properly
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        short_path = _get_short_path(save_path)
        outlook_msg = namespace.OpenSharedItem(short_path)
        correct_subject = (outlook_msg.Subject or "")[:100]
        try:
            outlook_msg.Close(0)
        except Exception:
            pass
        pythoncom.CoUninitialize()
        if correct_subject and any('一' <= c <= '鿿' for c in correct_subject):
            new_name = re.sub(r'[/\\:*?"<>|]', '_', correct_subject)
            new_name = re.sub(r'\s+', ' ', new_name)
            new_name = new_name.rstrip('.').strip() or "EDM_template"
            new_path = os.path.join(save_dir, new_name + ".msg")
            if os.path.isfile(new_path):
                new_path = os.path.join(save_dir, f"{new_name}_nested.msg")
            elif new_path != save_path:
                os.rename(save_path, new_path)
                save_path = new_path
                print(f"[ATTACH] renamed to: {os.path.basename(new_path)}")
    except Exception as e:
        print(f"[ATTACH] rename skipped (no Outlook or error): {e}", file=sys.stderr)

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


def generate_formal_test_csv(xlsx_path):
    """Generate formal_*.csv (all rows) and test_*.csv (N rows, one per test email)."""
    import csv
    import shutil
    import glob
    import json

    sn_dir = os.path.dirname(xlsx_path)
    base = os.path.splitext(os.path.basename(xlsx_path))[0]
    csv_files = glob.glob(os.path.join(sn_dir, base + "*.csv"))
    csv_path = csv_files[0] if csv_files else None

    if not csv_path or not os.path.exists(csv_path):
        print("[CSV] no source CSV found for formal/test generation", file=sys.stderr)
        return

    # Read source CSV
    with open(csv_path, encoding="gb18030", newline="") as f:
        reader = list(csv.reader(f))
        header = reader[0]
        rows = reader[1:]

    # Formal CSV: copy all rows
    formal_path = os.path.join(sn_dir, f"formal_{base}.csv")
    shutil.copy2(csv_path, formal_path)
    print(f"[CSV-FORMAL] saved: {os.path.basename(formal_path)} ({len(rows)} rows)")

    # Load test emails from config.json
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.path.join(project_root, "config.json")
    default_emails = [
        "ma.chuntao@oe.21vianet.com",
        "microsoft.163163@163.com",
    ]
    if os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        test_emails = config.get("test_emails", default_emails)
    else:
        test_emails = default_emails
    test_count = max(len(test_emails), 2)

    # Find Email and Token columns
    email_idx = None
    for i, col in enumerate(header):
        if col.strip().lower() == "email":
            email_idx = i
            break

    token_cols = [i for i, col in enumerate(header) if col.strip().lower().startswith("token")]
    row_scores = []
    for i, row in enumerate(rows):
        score = sum(1 for idx in token_cols if idx < len(row) and row[idx].strip())
        if score > 0:
            row_scores.append((score, i, row))
    row_scores.sort(reverse=True)

    # Collect up to test_count distinct rows
    selected = []
    idx = 0
    while len(selected) < test_count:
        if idx < len(row_scores):
            selected.append(list(row_scores[idx][2]))
        elif len(rows) > len(selected):
            selected.append(list(rows[len(selected)]))
        else:
            selected.append(["" for _ in header])
        idx += 1

    if email_idx is not None:
        for i, row in enumerate(selected):
            if i < len(test_emails):
                row[email_idx] = test_emails[i]

    test_path = os.path.join(sn_dir, f"test_{base}.csv")
    with open(test_path, "w", encoding="gb18030", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in selected:
            writer.writerow(row)
    print(f"[CSV-TEST] saved: {os.path.basename(test_path)} ({len(selected)} rows)")


def replace_span_tokens(html, mapping):
    """Replace %%TokenN%% / %%SubIdN%% split across <span> tags."""
    text_to_html = {}
    tp = 0
    in_tag = False
    for i, ch in enumerate(html):
        if ch == '<':
            in_tag = True
            continue
        if in_tag:
            if ch == '>':
                in_tag = False
            continue
        text_to_html[tp] = i
        tp += 1

    pattern = re.compile(r'%%(Token\d+|SubId\d+)%%')

    plain = []
    in_tag = False
    for ch in html:
        if ch == '<':
            in_tag = True
            continue
        if in_tag:
            if ch == '>':
                in_tag = False
            continue
        plain.append(ch)
    plain_text = ''.join(plain)

    matches = list(pattern.finditer(plain_text))
    if not matches:
        return html

    result_parts = []
    prev_end_html = 0
    for m in matches:
        name = m.group(1)
        value = mapping.get(name)
        if not value:
            continue

        first_html = text_to_html[m.start()]
        last_text_html = text_to_html[m.end() - 1]

        result_parts.append(html[prev_end_html:first_html])
        result_parts.append(value)

        rest = html[last_text_html + 1:]
        end_span = rest.find('</span>')
        if end_span >= 0:
            prev_end_html = last_text_html + 1 + end_span + len('</span>')
        else:
            prev_end_html = last_text_html + 1

        print(f"[TOKEN] %%{name}%% -> {value} (cross-span)")

    result_parts.append(html[prev_end_html:])
    return ''.join(result_parts)


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

    try:
        msg.Close(0)
    except Exception:
        pass

    pythoncom.CoUninitialize()

    if not html_body:
        print("[HTML] no HTMLBody found", file=sys.stderr)
        return False

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
    body_pos = html_body.lower().find("<body")
    if body_pos > 0:
        body_close = html_body.find(">", body_pos)
        if body_close > 0:
            html_body = html_body[:body_close + 1] + "\n" + subject_block + html_body[body_close + 1:]

    # Load token mapping from Tokenmapping.json
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    mapping_path = os.path.join(project_root, "Tokenmapping.json")
    if os.path.isfile(mapping_path):
        import json
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_list = json.load(f)
        token_mapping = {item["Name"]: item["Value"] for item in mapping_list}
        html_body = replace_span_tokens(html_body, token_mapping)

    # Remove Outlook's "_MailOriginal" anchor block between subject and table content, add a blank line
    html_body = re.sub(
        r'<a\s+name="_MailOriginal">\s*<span[^>]*>\s*<o:p>\s*&nbsp;\s*</o:p>\s*</span>\s*</a>\s*</p>',
        "<p class=MsoNormal><o:p>&nbsp;</o:p></p>",
        html_body,
        flags=re.DOTALL | re.IGNORECASE,
    )

    with open(output_html, "w", encoding="utf-8", newline="") as f:
        f.write(html_body)

    size_kb = os.path.getsize(output_html) / 1024
    print(f"[HTML] saved: {os.path.basename(output_html)} ({size_kb:.1f} KB)")
    return True


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

    # --- Clean previous round's output ---
    for fname in os.listdir(sn_folder):
        fpath = os.path.join(sn_folder, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
            print(f"[CLEANUP] removed stale: {fname}")

    # --- Extract nested EDM template .msg ---
    target_idx = find_target_attachment_idx(msg_path)
    attach_path = None
    if target_idx is not None and target_idx < len(msg.attachments):
        matched_att = msg.attachments[target_idx]
        attach_path = save_target_attachment(matched_att, sn_folder)
    else:
        print("[ATTACH] no target .msg attachment found", file=sys.stderr)

    msg.close()

    # --- Copy original .msg to SN folder (after msg.close to release file handle) ---
    msg_dst = os.path.join(sn_folder, msg_file)
    shutil.copy2(msg_path, msg_dst)
    print(f"[COPY] {msg_file} -> {sn}/ (original email)")

    # --- Convert nested .msg to HTML via win32com ---
    if attach_path:
        html_path = os.path.join(sn_folder, "EDM_template.html")
        convert_msg_to_html(attach_path, html_path)

    # --- Copy .xlsx to SN folder and convert to CSV ---
    for xlsx_file in xlsx_files:
        src = os.path.join(TEMP_DIR, xlsx_file)
        dst = os.path.join(sn_folder, xlsx_file)
        shutil.copy2(src, dst)
        print(f"[COPY] {xlsx_file} -> {sn}/")
        convert_xlsx_to_csv(dst)
        generate_formal_test_csv(dst)

    print(f"\nDone — SN folder: {sn_folder}")


def main():
    process_edm()


if __name__ == "__main__":
    main()