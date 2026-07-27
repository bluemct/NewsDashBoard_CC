"""
EDM Email Sender — 通过 SMTP 发送邮件

用法:
    python edm_agent_send_email.py
    python edm_agent_send_email.py --subject "自定义标题"
    python edm_agent_send_email.py --body "这是一段纯文本内容"

配置:
    edm_email_config.json   — SMTP 服务器 + 发件人 + 收件人 + 默认标题 + 默认正文
"""
import json
import os
import sys
import argparse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def load_config():
    """Load edm_email_config.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edm_email_config.json")
    if not os.path.isfile(path):
        print(f"[ERROR] Config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def send_email(config, subject, body):
    """Send email via SMTP.

    Priority:
      1. --subject / --body from CLI
      2. subject / body from config JSON
      3. fallback defaults
    """

    # ---- Determine subject ----
    if not subject:
        subject = config.get("subject", "")
    if not subject:
        subject = "EDM Proces Email"

    # ---- Determine body ----
    if body is not None:
        sub_type = "html"
        content = body
        body_label = "text (from CLI)"
    elif config.get("body"):
        sub_type = "plain"
        content = config["body"]
        body_label = "text (from config)"
    else:
        content = f"<p>EDM Process Email sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        sub_type = "html"
        body_label = "default placeholder"

    # ---- Recipients ----
    recipients = config.get("recipients", {})
    to_list = recipients.get("to", [])
    cc_list = recipients.get("cc", [])
    bcc_list = recipients.get("bcc", [])
    all_recipients = to_list + cc_list + bcc_list

    if not all_recipients:
        print("[ERROR] No recipients configured", file=sys.stderr)
        sys.exit(1)

    # ---- Build message ----
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["sender"]
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.attach(MIMEText(content, sub_type, "utf-8"))

    # ---- Send via SMTP ----
    smtp_server = config["smtp_server"]
    smtp_port = config.get("smtp_port", 25)

    print(f"[SMTP] Connecting to {smtp_server}:{smtp_port}...")
    try:
        smtp = smtplib.SMTP(smtp_server, smtp_port)
    except Exception as e:
        print(f"[ERROR] Failed to connect to SMTP server: {e}", file=sys.stderr)
        sys.exit(1)

    sender = config["sender"]
    try:
        smtp.sendmail(sender, all_recipients, msg.as_string())
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}", file=sys.stderr)
        smtp.quit()
        sys.exit(1)
    finally:
        smtp.quit()

    print(f"[OK] Email sent successfully")
    print(f"  Subject: {subject}")
    print(f"  From:    {sender}")
    print(f"  To:      {', '.join(to_list) or '(empty)'}")
    print(f"  CC:      {', '.join(cc_list) or '(empty)'}")
    print(f"  BCC:     {', '.join(bcc_list) or '(empty)'}")
    print(f"  Body:    {body_label}")


def main():
    parser = argparse.ArgumentParser(description="Send EDM  Process email via SMTP")
    parser.add_argument("--subject", help="Override subject line")
    parser.add_argument("--body", help="Inline HTML/text body (overrides config body)")
    args = parser.parse_args()

    config = load_config()
    send_email(config, args.subject, args.body)


if __name__ == "__main__":
    main()
