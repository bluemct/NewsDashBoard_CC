"""
EDM Email Draft Creator — 创建 Outlook 邮件草稿（不发送）

用法:
    python edm_send_draft.py
    # 在 EDM_template.html 所在目录运行

    python edm_send_draft.py --html "path/to/EDM_template.html"
    # 指定 EDM 模板文件

    python edm_send_draft.py --html "path/to/EDM_template.html" --subject "邮件标题"
    # 自定义标题（默认从 Tokenmapping.json 取 EDM_Subject）

配置:
    .edm_agent_config.json   — Sender (发件人邮箱)
    .edm_recipients.json     — To / CC / BCC (由用户编辑)

注意: 本程序只创建草稿，保存到 Outlook Drafts 文件夹，不会自动发送。
"""
import json
import os
import sys
import argparse


def load_recipients():
    """Load .edm_recipients.json. Raises on missing/invalid."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".edm_agent_recipients.json")
    if not os.path.isfile(path):
        print(f"[ERROR] Recipients config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rec = data.get("recipients", {})
    return {
        "to": rec.get("to", []),
        "cc": rec.get("cc", []),
        "bcc": rec.get("bcc", []),
    }


def load_edm_config():
    """Load .edm_agent_config.json for sender info."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".edm_agent_config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_subject_from_token_mapping():
    """Read EDM_Subject from Tokenmapping.json if available."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tokenmapping.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        mapping_list = json.load(f)
    for item in mapping_list:
        if item.get("Name") == "EDM_Subject":
            return item.get("Value", "")
    return None


def create_draft(html_file, subject=None):
    """Create an email draft in Outlook Drafts folder."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")

        # Load config
        recipients = load_recipients()
        all_emails = recipients["to"] + recipients["cc"] + recipients["bcc"]
        if not all_emails:
            print("[ERROR] No recipients configured in .edm_recipients.json", file=sys.stderr)
            print("  Please add at least one email to 'to', 'cc', or 'bcc'.")
            sys.exit(1)

        # Read HTML template
        with open(html_file, "r", encoding="utf-8") as f:
            html_body = f.read()

        # Determine subject
        if not subject:
            subject = get_subject_from_token_mapping()
            if not subject:
                subject = "EDM Email"
                print("[WARN] No subject specified and no EDM_Subject in Tokenmapping.json, using default")

        # Create mail item
        mail = outlook.CreateItem(0)
        mail.Subject = subject

        # Set recipients
        if recipients["to"]:
            mail.To = "; ".join(recipients["to"])
        if recipients["cc"]:
            mail.CC = "; ".join(recipients["cc"])
        if recipients["bcc"]:
            mail.BCC = "; ".join(recipients["bcc"])

        # Set HTML body
        mail.HTMLBody = html_body

        # Save to Drafts (do NOT send)
        mail.Save()
        print(f"[DRAFT] Created email draft in Outlook Drafts folder")
        print(f"  Subject: {subject}")
        print(f"  To:    {'; '.join(recipients['to']) or '(empty)'}")
        print(f"  CC:    {'; '.join(recipients['cc']) or '(empty)'}")
        print(f"  BCC:   {'; '.join(recipients['bcc']) or '(empty)'}")
        print(f"  HTML:  {html_file} ({len(html_body)} bytes)")
        print()
        print("  -> Open Outlook Drafts folder to review and send manually.")

        mail.Close(0)

    finally:
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description="Create EDM email draft in Outlook (does NOT send)")
    parser.add_argument("--html", help="Path to EDM_template.html (default: search EDM/SN-*/)")
    parser.add_argument("--subject", help="Override subject line")
    args = parser.parse_args()

    html_file = args.html
    if not html_file:
        # Auto-discover: find latest EDM_template.html
        base_dir = os.path.dirname(os.path.abspath(__file__))
        edm_dir = os.path.join(base_dir, "EDM")
        if os.path.isdir(edm_dir):
            latest = None
            for entry in sorted(os.listdir(edm_dir)):
                sn_folder = os.path.join(edm_dir, entry)
                template = os.path.join(sn_folder, "EDM_template.html")
                if os.path.isfile(template):
                    latest = template
            if latest:
                html_file = latest
            else:
                print("[ERROR] No EDM_template.html found in EDM/SN-*/ folders", file=sys.stderr)
                print("  Run edm_process.py first, or specify --html path")
                sys.exit(1)

    if not os.path.isfile(html_file):
        print(f"[ERROR] HTML file not found: {html_file}", file=sys.stderr)
        sys.exit(1)

    create_draft(html_file, args.subject)


if __name__ == "__main__":
    main()
