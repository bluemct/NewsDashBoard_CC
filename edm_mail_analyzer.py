"""
Analyze all emails in the EDM Outlook folder.

Extracts date, subject, sender, conversation_topic from every email,
counts emails per conversation, and writes one JSON record per email.

Output: c:\temp\edmmailanalyzer.json
"""
import json
import os
import sys
import win32com.client


def find_edm_folder(ns):
    """Find the EDM folder anywhere in the account tree."""
    inbox = ns.GetDefaultFolder(6)  # olFolderInbox
    parent = inbox.Parent

    def search(folders):
        for f in folders:
            if f.Name.lower() == "edm":
                return f
            result = search(f.Folders)
            if result:
                return result
        return None

    result = search(inbox.Folders)
    if result:
        return result
    result = search(parent.Folders)
    return result


def main():
    # Connect to Outlook
    outlook = win32com.client.Dispatch("Outlook.Application")
    ns = outlook.GetNamespace("MAPI")

    folder = find_edm_folder(ns)
    if not folder:
        print("Error: EDM folder not found in Outlook.", file=sys.stderr)
        sys.exit(1)

    items = folder.Items
    items.Sort("[ReceivedTime]", False)  # oldest first

    print(f"Folder: {folder.FullFolderPath}")
    print(f"Total items: {items.Count}")

    records = []
    conv_counts = {}

    for i in range(items.Count):
        mail = items[i + 1]

        # Skip non-mail items
        if mail.Class != 43:  # olMail = 43
            continue

        received = str(mail.ReceivedTime) if mail.ReceivedTime else ""
        conv_topic = getattr(mail, "ConversationTopic", "")

        # Count per conversation
        if conv_topic:
            conv_counts[conv_topic] = conv_counts.get(conv_topic, 0) + 1

        record = {
            "date": received,
            "subject": mail.Subject,
            "sender": mail.SenderEmailAddress,
            "conversation_topic": conv_topic,
        }
        records.append(record)

    # Write output
    output_path = r"c:\temp\edmmailanalyzer.json"
    os.makedirs(r"c:\temp", exist_ok=True)

    # Add conversation count to each record, then append a summary
    result = []
    for r in records:
        entry = dict(r)
        entry["conversation_count"] = conv_counts.get(r["conversation_topic"], 0)
        result.append(entry)

    # Append summary block
    result.append({
        "_summary": True,
        "total_emails": len(records),
        "conversations": {
            topic: count for topic, count in sorted(conv_counts.items(), key=lambda x: -x[1])
        }
    })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Written {len(records)} records to {output_path}")
    print(f"\nConversations ({len(conv_counts)} total):")
    for topic, count in sorted(conv_counts.items(), key=lambda x: -x[1]):
        print(f"  [{count}] {topic}")


if __name__ == "__main__":
    main()
