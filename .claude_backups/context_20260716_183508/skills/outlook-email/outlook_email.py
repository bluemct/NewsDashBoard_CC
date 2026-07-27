"""
Read an Outlook email by EntryID via win32com (read-only).
"""
import argparse
import sys
import win32com.client


def main():
    parser = argparse.ArgumentParser(description="Read Outlook email by EntryID")
    parser.add_argument("entry_id", help="Outlook EntryID")
    parser.add_argument("--plain-text", action="store_true", help="Convert HTML body to plain text")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        mail = ns.GetItemFromID(args.entry_id)

        print(f"Subject: {mail.Subject}")
        print(f"From: {mail.SenderEmailAddress}")
        print(f"Sent: {mail.SentOn}")
        print(f"Read: {mail.UnRead}")
        print(f"EntryID: {mail.EntryID}")
        print()

        # Show recipients
        to_addrs = [r.Address for r in mail.Recipients if r.AddressType in ("SMTP", "")]
        if to_addrs:
            print(f"To: {', '.join(to_addrs)}")
            print()

        body = mail.Body  # plain text body
        if args.plain_text or not mail.HTMLBody:
            body = mail.Body
        else:
            # Try HTML-to-text via COM
            try:
                doc = win32com.client.Dispatch("HTMLFile")
                doc.write(str(mail.HTMLBody))
                body = doc.body.innerText or mail.Body
            except Exception:
                body = mail.Body

        print(body)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
