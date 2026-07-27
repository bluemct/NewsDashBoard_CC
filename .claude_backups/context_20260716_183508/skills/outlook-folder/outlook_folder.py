"""
Find or list Outlook folders via win32com (read-only).
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


def list_folders(ns, folder=None, indent=0):
    """Recursively list folder names."""
    if folder is None:
        root = ns.Folders
        for f in root:
            list_folders(ns, f, 0)
    else:
        print(" " * indent + f"- {folder.Name} (items: {folder.Items.Count})")
        for sub in folder.Folders:
            list_folders(ns, sub, indent + 2)


def main():
    parser = argparse.ArgumentParser(description="Find Outlook folder")
    parser.add_argument("name", nargs="?", default=None, help="Folder name (Inbox, Sent Items, Drafts, etc.)")
    parser.add_argument("--list", action="store_true", help="List all folders")
    args = parser.parse_args()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
    except Exception as e:
        print(f"Error connecting to Outlook: {e}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("All folders:")
        list_folders(ns)
        return

    if not args.name:
        # Default to Inbox
        args.name = "Inbox"

    folder_id = FOLDER_MAP.get(args.name.lower())
    if folder_id:
        folder = ns.GetDefaultFolder(folder_id)
        print(f"Folder: {folder.Name}")
        print(f"EntryID: {folder.EntryID}")
        print(f"Items: {folder.Items.Count}")
        print(f"Unread: {folder.UnReadItemCount}")
    else:
        print(f"Folder '{args.name}' not in known list. Use --list to see all folders.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
