"""
List recent emails from an Outlook folder via win32com (read-only).
"""
import argparse
import sys
import win32com.client

FOLDER_MAP = {
    "inbox": 6,
    "sent items": 5,
    "drafts": 16,
    "deleted items": 3,
    "outbox": 4,
    "junk email": 23,
}


def main():
    parser = argparse.ArgumentParser(description="List Outlook emails")
    parser.add_argument("folder", default="Inbox", help="Folder name (Inbox, Sent Items, Drafts)")
    parser.add_argument("--count", type=int, default=10, help="Number of emails to list (default: 10)")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
    except Exception as e:
        print(f"Error connecting to Outlook: {e}", file=sys.stderr)
        sys.exit(1)

    folder_id = FOLDER_MAP.get(args.folder.lower())
    if not folder_id:
        print(f"Unknown folder '{args.folder}'. Use: {', '.join(FOLDER_MAP.keys())}", file=sys.stderr)
        sys.exit(1)

    try:
        folder = ns.GetDefaultFolder(folder_id)
        items = folder.Items
        items.Sort("[ReceivedTime]", True)

        count = min(args.count, items.Count)
        if count == 0:
            print(f"No emails in {args.folder}.")
            return

        print(f"\n{'Subject':.<60} {'From':.<30} {'Date':.<20} {'Read':.>4}")
        print("-" * 114)

        for i in range(count):
            mail = items[i + 1]  # COM is 1-based
            subject = (mail.Subject or "")[:58]
            sender = str(mail.SenderEmailAddress)[:28]
            date = str(mail.SentOn)[:19] if hasattr(mail, "SentOn") else str(mail.ReceivedTime)[:19]
            read = "N" if mail.UnRead else "Y"
            print(f"{subject:<60} {sender:<30} {date:<20} {read:>4}")

        print(f"\nTotal: {count} emails shown of {items.Count} in {args.folder}")
    except Exception as e:
        print(f"Error listing emails: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
