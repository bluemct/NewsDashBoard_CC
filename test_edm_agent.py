"""Quick test: verify EWS connection works."""
import sys
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, ".")

from edm_agent import EWSClient, config

def test():
    try:
        c = config["ews"]
        print(f"URL:     {c['url']}")
        print(f"User:    {c['domain_user']}")
        print(f"Mailbox: {c['mailbox']}")
        print(f"Folder:  {c.get('folder_name', 'EDM')}")
        print()

        client = EWSClient()
        folder_id = client.find_folder("EDM")
        if folder_id:
            print(f"OK: Found EDM folder: {folder_id[:40]}...")
        else:
            print("FAIL: EDM folder not found")
            return False

        # Try finding items
        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(hours=24)
        items = client.find_items_since(folder_id, since, max_items=3)
        print(f"OK: Found {len(items)} recent item(s)")
        for item in items:
            print(f"  - [{item['subject'][:50]}] from {item['sender']} (has_att={item['has_attachments']})")

        return True

    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    ok = test()
    sys.exit(0 if ok else 1)
