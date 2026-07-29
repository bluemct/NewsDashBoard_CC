"""
EDM Process for EML — Pure Python, no Outlook COM / win32com dependency.

Drops in as a replacement for edm_process.py when input is .eml instead of .msg.

Full pipeline:
  1. Read .eml from EDM/Temp/
  2. Extract SN from subject, create EDM/SN-xxxxx/ folder
  3. Find message/rfc822 without recipients (EDM template)
  4. Extract text/html, apply Token replacement, save EDM_template.html
  5. Save nested EDM template as .eml for reference
  6. Copy xlsx to SN folder, convert to CSV, generate formal/test CSV

Usage:
    python edm_process_eml.py [--temp-dir DIR] [--edm-dir DIR] [--file FILE]

No Outlook COM / win32com required.
"""
import argparse
import os
import re
import sys
import csv
import json
import shutil
import glob as glob_mod
import subprocess
import email as email_lib


# ─── Helpers ─────────────────────────────────────────────────

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
        return raw_subject or ""


def decode_payload(part):
    """Decode a MIME part's payload using its declared charset."""
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset()
    for enc in [charset, "utf-8", "gb18030", "latin-1"]:
        try:
            return payload.decode(enc or "utf-8", errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def top_level_parts(msg):
    """Yield top-level MIME parts without descending into message/rfc822."""
    if msg.is_multipart():
        for sub in msg.get_payload() or []:
            if isinstance(sub, email_lib.message.Message):
                if sub.get_content_type() == "message/rfc822":
                    yield sub
                else:
                    yield from top_level_parts(sub)
            else:
                yield sub
    else:
        yield msg


def extract_sn(text):
    """Extract SN-12345 from any text."""
    m = re.search(r"SN\s*-\s*(\d+)", text)
    return f"SN-{m.group(1)}" if m else None


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

        print(f"  [TOKEN] %%{name}%% -> {value}")

    result_parts.append(html[prev_end_html:])
    return ''.join(result_parts)


# ─── Path resolution (same structure as edm_process.py) ──────

def _default_base_dir():
    """Default EDM output directory (4 levels up from this script + EDM)."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "EDM"
    )


def _parse_args():
    parser = argparse.ArgumentParser(description="EDM Process for EML (no Outlook COM)")
    parser.add_argument("--temp-dir", default=None,
                        help="Directory containing input .eml and .xlsx files")
    parser.add_argument("--edm-dir", default=_default_base_dir(),
                        help="Base directory for SN output folders (default: project/EDM)")
    parser.add_argument("--file", default=None,
                        help="Specific .eml file to process (filename only)")
    args = parser.parse_args()

    if args.temp_dir is None:
        args.temp_dir = os.path.join(args.edm_dir, "Temp")
    return args.temp_dir, args.edm_dir, args.file


# ─── Main Pipeline ──────────────────────────────────────────

def process_edm_eml():
    """Full EDM processing workflow from .eml (no Outlook COM)."""
    temp_dir, base_dir, cli_file = _parse_args()

    if not os.path.isdir(temp_dir):
        print(f"Error: Temp directory not found: {temp_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Find .eml file
    if cli_file:
        eml_file = cli_file
        eml_path = os.path.join(temp_dir, eml_file)
        if not os.path.isfile(eml_path):
            print(f"Error: specified file not found: {eml_path}", file=sys.stderr)
            sys.exit(1)
        # Pick up ALL .xlsx in Temp/ — caller (edm.py) cleans stale xlsx before running
        xlsx_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.xlsx')]
    else:
        eml_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.eml')]
        if not eml_files:
            print("Error: no .eml file found in Temp/", file=sys.stderr)
            sys.exit(1)
        # Pick the most recently modified .eml
        eml_file = sorted(eml_files, key=lambda f: os.path.getmtime(os.path.join(temp_dir, f)), reverse=True)[0]
        xlsx_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.xlsx')]

    eml_path = os.path.join(temp_dir, eml_file)
    print(f"[INPUT] {eml_file}")

    with open(eml_path, "rb") as f:
        mime = f.read()

    emsg = email_lib.message_from_bytes(mime)
    outer_subject = decode_subject(emsg.get("Subject", ""))
    print(f"[EMAIL] Subject: {outer_subject[:120]}")

    # 2. Extract SN, create folder
    sn = extract_sn(outer_subject)
    if not sn:
        sn = extract_sn(eml_file)
    if not sn:
        print("Error: no SN number found in subject or file path.", file=sys.stderr)
        sys.exit(1)

    print(f"[SN] {sn}")
    sn_folder = os.path.join(base_dir, sn)
    os.makedirs(sn_folder, exist_ok=True)
    print(f"[FOLDER] {sn_folder}")

    # Clean previous round output
    for fname in os.listdir(sn_folder):
        fpath = os.path.join(sn_folder, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
            print(f"[CLEANUP] removed stale: {fname}")

    # 3. Find EDM template rfc822 (no recipients)
    rfc822_parts = []
    for part in top_level_parts(emsg):
        if part.get_content_type() == "message/rfc822":
            rfc822_parts.append(part)

    if not rfc822_parts:
        print("Error: no message/rfc822 attachments found", file=sys.stderr)
        sys.exit(1)

    print(f"[RFC822] Found {len(rfc822_parts)} nested message(s)")

    target = None
    for i, rfc822 in enumerate(rfc822_parts):
        payload = rfc822.get_payload(decode=False)
        if isinstance(payload, list):
            sub = payload[0] if payload else None
        else:
            sub = payload

        if not isinstance(sub, email_lib.message.Message):
            continue

        subj = decode_subject(sub.get("Subject", ""))
        to = (sub.get("To") or "").strip()
        cc = (sub.get("Cc") or "").strip()
        bcc = (sub.get("Bcc") or "").strip()
        has_recipients = bool(to or cc or bcc)

        label = "EDM Template" if not has_recipients else "Reminder/Other"
        print(f"  [{i}] {subj[:80]}  ({label})")

        if not has_recipients:
            target = sub

    if target is None:
        print("Error: EDM Template (no recipients) not found", file=sys.stderr)
        sys.exit(1)

    template_subject = decode_subject(target.get("Subject", ""))

    # 4. Save nested EDM template as .eml for reference
    target_bytes = (email_lib.message_as_bytes(target)
                    if hasattr(email_lib, 'message_as_bytes')
                    else target.as_string().encode("utf-8"))
    save_name = re.sub(r'[/\\:*?"<>|]', '_', template_subject[:80])
    save_name = re.sub(r'\s+', ' ', save_name).strip() or "EDM_template"
    save_name = save_name.rstrip('.')
    nested_eml_path = os.path.join(sn_folder, save_name + "_nested.eml")
    with open(nested_eml_path, "wb") as f:
        f.write(target_bytes)
    print(f"\n[ATTACH] saved nested .eml: {os.path.basename(nested_eml_path)} ({len(target_bytes) / 1024:.1f} KB)")

    # 5. Extract HTML body from EDM template
    html_body = ""
    for sp in top_level_parts(target):
        sct = sp.get_content_type()
        if sct == "text/html" and not sp.get_filename():
            html_body = decode_payload(sp)
            break

    if not html_body:
        print("Error: no text/html found in EDM Template", file=sys.stderr)
        sys.exit(1)

    print(f"\n[HTML] Extracted: {len(html_body) / 1024:.0f} KB")

    # 6. Token replacement
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    mapping_path = os.path.join(project_root, "Tokenmapping.json")
    if os.path.isfile(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_list = json.load(f)
        token_mapping = {item["Name"]: item["Value"] for item in mapping_list}
        html_body = replace_span_tokens(html_body, token_mapping)

    # 7. Insert subject line at top of body (matching Outlook's style)
    safe_subject = template_subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    subject_block = (
        f'<p class=MsoNormal><b><span lang=ZH-CN\n'
        f"style='font-family:等线;mso-hansi-font-family:Calibri;mso-bidi-font-family:等线;\n"
        f"color:black'>主题</span></b><span style='font-family:等线;mso-hansi-font-family:Calibri;\n"
        f"mso-bidi-font-family:等线;color:black'>: {safe_subject}</span></p>\n"
        f"\n"
        f'<p class=MsoNormal><o:p>&nbsp;</o:p></p>\n'
    )
    body_pos = html_body.lower().find("<body")
    if body_pos >= 0:
        body_close = html_body.find(">", body_pos)
        if body_close >= 0:
            html_body = html_body[:body_close + 1] + "\n" + subject_block + html_body[body_close + 1:]

    # 8. Remove _MailOriginal anchor block
    html_body = re.sub(
        r'<a\s+name="_MailOriginal">\s*<span[^>]*>\s*<o:p>\s*&nbsp;\s*</o:p>\s*</span>\s*</a>\s*</p>',
        '<p class=MsoNormal><o:p>&nbsp;</o:p></p>',
        html_body,
        flags=re.DOTALL | re.IGNORECASE,
    )

    html_path = os.path.join(sn_folder, "EDM_template.html")
    with open(html_path, "w", encoding="utf-8", newline="") as f:
        f.write(html_body)
    size_kb = os.path.getsize(html_path) / 1024
    print(f"[HTML] saved: EDM_template.html ({size_kb:.1f} KB)")

    # 9. Copy .xlsx to SN folder and convert to CSV
    for xlsx_file in xlsx_files:
        src = os.path.join(temp_dir, xlsx_file)
        dst = os.path.join(sn_folder, xlsx_file)
        shutil.copy2(src, dst)
        print(f"\n[COPY] {xlsx_file} -> {sn}/")

        # Call xlsx_to_csv.py
        xlsx_skill = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            ".claude", "skills", "xlsx-to-csv", "xlsx_to_csv.py",
        )
        result = subprocess.run(
            [sys.executable, xlsx_skill, dst],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0 and result.stderr:
            print(f"  [WARN] xlsx_to_csv stderr: {result.stderr[:200]}")

        # Generate formal/test CSV
        xlsx_base = os.path.splitext(xlsx_file)[0]
        csv_files = glob_mod.glob(os.path.join(sn_folder, xlsx_base + "*.csv"))
        csv_path = csv_files[0] if csv_files else None
        if csv_path:
            _generate_formal_test_csv(csv_path, sn_folder, xlsx_base, project_root)

    print(f"\nDone — SN folder: {sn_folder}")


def _generate_formal_test_csv(csv_path, sn_dir, base, project_root):
    """Generate formal_*.csv (all rows) and test_*.csv (N rows, one per test email)."""
    with open(csv_path, encoding="gb18030", newline="") as f:
        reader = list(csv.reader(f))
        header = reader[0]
        rows = reader[1:]

    # Formal CSV: copy all rows
    formal_path = os.path.join(sn_dir, f"formal_{base}.csv")
    shutil.copy2(csv_path, formal_path)
    print(f"  [CSV-FORMAL] formal_{base}.csv ({len(rows)} rows)")

    # Test emails config
    config_path = os.path.join(project_root, "config.json")
    default_emails = ["ma.chuntao@oe.21vianet.com", "microsoft.163163@163.com"]
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
    print(f"  [CSV-TEST] test_{base}.csv ({len(selected)} rows)")


def main():
    # Force UTF-8 stdout so filenames with special characters don't crash print()
    if sys.stdout is not None and sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    process_edm_eml()


if __name__ == "__main__":
    main()
