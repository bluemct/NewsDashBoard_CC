"""
Create an Outlook email draft via win32com. Saves to Drafts, NEVER sends.
"""
import argparse
import sys
import win32com.client


def main():
    parser = argparse.ArgumentParser(description="Create Outlook email draft (does NOT send)")
    parser.add_argument("--to", required=True, nargs="+", help="Recipient email addresses")
    parser.add_argument("--cc", nargs="+", default=[], help="CC email addresses")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", required=True, help="Email body")
    parser.add_argument("--html", action="store_true", help="Treat body as HTML")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # olMailItem = 0

        # To recipients
        for addr in args.to:
            mail.To = f"{mail.To};{addr}".strip(";") if mail.To else addr

        # CC recipients
        for addr in args.cc:
            mail.CC = f"{mail.CC};{addr}".strip(";") if mail.CC else addr

        mail.Subject = args.subject

        if args.html:
            mail.HTMLBody = args.body
        else:
            mail.Body = args.body

        # Save as draft only — NO .Send
        mail.Save()

        print("Draft created successfully!")
        print(f"  To: {', '.join(args.to)}")
        print(f"  CC: {', '.join(args.cc)}" if args.cc else "  CC: (none)")
        print(f"  Subject: {args.subject}")
        print(f"  EntryID: {mail.EntryID}")
        print()
        print("  [!] Draft is saved in your Drafts folder.")
        print("  [!] Open Outlook and click Send when ready.")

    except Exception as e:
        print(f"Error creating draft: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
