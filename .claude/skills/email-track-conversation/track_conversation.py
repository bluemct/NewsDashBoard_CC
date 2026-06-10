"""
Track email conversations — classify as Sent, Reply, or Other.
"""
import argparse
import hashlib
import json
import os
import sys
import win32com.client

# Store path for conversation tracking
_STORE_PATH = os.path.expanduser("~/.claude/conversations.json")


def load_store():
    if os.path.exists(_STORE_PATH):
        with open(_STORE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_store(store):
    with open(_STORE_PATH, "w") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def conversation_key(mail):
    """Generate a conversation key from subject (strip Re:/Fw: prefix)."""
    subject = (mail.Subject or "").strip().lower()
    # Remove Re:/Fw:/RE:/FW: prefix
    while subject.startswith(("re:", "re ", "fw:", "fw ")):
        subject = re.split(r"[:\s]+", subject, maxsplit=1)[-1]
    import re
    return hashlib.md5(subject.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Track email conversation")
    parser.add_argument("--entry-id", required=True, help="Outlook EntryID")
    parser.add_argument("--my-address", required=True, help="Your email address")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        mail = ns.GetItemFromID(args.entry_id)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sender = mail.SenderEmailAddress.lower()
    my_addr = args.my_address.lower()
    conv_key = conversation_key(mail)

    store = load_store()
    result = {
        "subject": mail.Subject,
        "sender": sender,
        "conversation": conv_key,
        "classification": "Other",
    }

    if sender == my_addr:
        store[conv_key] = True
        result["classification"] = "Sent"
        print(f"[SENT] Conversation tracked: {conv_key}")
    elif conv_key in store:
        result["classification"] = "Reply"
        print(f"[REPLY] Conversation: {conv_key} | Sender: {sender}")
    else:
        print(f"[OTHER] Conversation: {conv_key} | Sender: {sender} | Subject: {mail.Subject}")

    save_store(store)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
