"""
Monitor a specific Outlook folder for new mail and log to a JSON file.

Usage:
    python email_monitor.py [--folder "Inbox"] [--interval 10] [--output email_monitor.json]
    python email_monitor.py --folder "Inbox" --sender "xxx@microsoft.com"

Output:
    JSON file with: entry_id, conversation_topic, subject, sender_address, received

Safety:
    - READ-ONLY on Outlook: reads EntryID, ConversationTopic, Subject, SenderEmailAddress, ReceivedTime
    - No .Send(), .Delete(), .Move(), .MarkAsRead()
    - Writes to a local JSON file
"""
import argparse
import json
import os
import sys
import time

import win32com.client


def find_folder(ns, folder_name):
    """
    Search for a folder by name across the account root and Inbox subfolders.
    """
    inbox = ns.GetDefaultFolder(6)  # olFolderInbox
    parent = inbox.Parent

    # Search the entire account tree
    def search(folders):
        for f in folders:
            if f.Name.lower() == folder_name.lower():
                return f
            result = search(f.Folders)
            if result:
                return result
        return None

    if inbox.Name.lower() == folder_name.lower():
        return inbox
    result = search(inbox.Folders)
    if result:
        return result
    result = search(parent.Folders)
    if result:
        return result
    return None


def load_records(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_records(path, records):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(records, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Monitor an Outlook folder for new mail")
    parser.add_argument(
        "--folder", default="收件箱",
        help="Outlook folder name to monitor (default: 收件箱)"
    )
    parser.add_argument(
        "--interval", type=int, default=10,
        help="Poll interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--output", default="email_monitor.json",
        help="JSON output file (default: email_monitor.json)"
    )
    parser.add_argument(
        "--sender", default=None,
        help="Only record mail from this sender address (optional)"
    )
    args = parser.parse_args()

    # Connect to Outlook
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
    except Exception as e:
        print(f"Error connecting to Outlook: {e}", file=sys.stderr)
        sys.exit(1)

    # Find the target folder
    folder = find_folder(ns, args.folder)
    if not folder:
        print(f"Error: folder '{args.folder}' not found in Outlook.", file=sys.stderr)
        sys.exit(1)

    print(f"Monitoring folder: {folder.FullFolderPath}")
    print(f"Output file:   {os.path.abspath(args.output)}")
    print(f"Poll interval: {args.interval}s")
    if args.sender:
        print(f"Filter sender: {args.sender}")
    print("Press Ctrl+C to stop.\n")
    sys.stdout.flush()

    # Load existing records
    records = load_records(args.output)
    seen = {r["entry_id"] for r in records}
    prev_count = len(records)

    try:
        while True:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)
            count = min(5, items.Count)

            for i in range(count):
                mail = items[i + 1]
                if mail.EntryID in seen:
                    continue

                # Filter by sender if specified
                if args.sender and mail.SenderEmailAddress != args.sender:
                    seen.add(mail.EntryID)
                    continue

                record = {
                    "entry_id": mail.EntryID,
                    "conversation_topic": getattr(mail, "ConversationTopic", ""),
                    "subject": mail.Subject,
                    "sender_address": mail.SenderEmailAddress,
                    "received": str(mail.ReceivedTime),
                }
                records.append(record)
                seen.add(mail.EntryID)

                print(f"[NEW] Subject: {record['subject']}")
                print(f"      From:    {record['sender_address']}")
                print(f"      Topic:   {record['conversation_topic']}")
                print(f"      Time:    {record['received']}")
                sys.stdout.flush()

            if len(records) > prev_count:
                save_records(args.output, records)
                prev_count = len(records)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nStopped monitoring.")
        save_records(args.output, records)
        print(f"Saved {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
