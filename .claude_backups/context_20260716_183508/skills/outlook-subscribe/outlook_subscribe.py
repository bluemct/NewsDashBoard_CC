"""
Monitor Outlook Inbox for new mail via win32com polling.
"""
import argparse
import json
import sys
import time
import win32com.client


def main():
    parser = argparse.ArgumentParser(description="Monitor Outlook Inbox for new mail")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds (default: 5)")
    parser.add_argument("--callback", default=None, help="Python script to call on new mail (receives JSON on stdin)")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(6)  # olFolderInbox = 6
    except Exception as e:
        print(f"Error connecting to Outlook: {e}", file=sys.stderr)
        sys.exit(1)

    # Track seen EntryIDs
    seen = set()
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)

    # Seed with existing unread emails
    for i in range(min(10, items.Count)):
        mail = items[i + 1]
        if not mail.UnRead:
            seen.add(mail.EntryID)

    print(f"Monitoring {inbox.Name} for new mail (poll every {args.interval}s). Press Ctrl+C to stop.")
    sys.stdout.flush()

    try:
        while True:
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
            count = min(5, items.Count)

            for i in range(count):
                mail = items[i + 1]
                if mail.EntryID not in seen and mail.UnRead:
                    seen.add(mail.EntryID)
                    info = {
                        "subject": mail.Subject,
                        "from": mail.SenderEmailAddress,
                        "received": str(mail.ReceivedTime),
                        "entry_id": mail.EntryID,
                    }
                    print(f"[NEW] From: {info['from']} | Subject: {info['subject']} | Time: {info['received']}")
                    sys.stdout.flush()

                    if args.callback:
                        try:
                            import subprocess
                            subprocess.run(
                                ["python", args.callback],
                                input=json.dumps(info, ensure_ascii=False),
                                text=True,
                                timeout=10,
                            )
                        except Exception as e:
                            print(f"  Callback error: {e}", file=sys.stderr)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped monitoring.")


if __name__ == "__main__":
    main()
