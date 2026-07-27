"""Export all contacts to CSV (email, contact_id)."""
import csv
import sys

sys.path.insert(0, ".")
from get_contact import list_contacts

CHUNK = 50  # API max page size
rows = []
start = 1

while True:
    contacts = list_contacts(max_results=CHUNK, start_index=start)
    if not contacts:
        break
    for c in contacts:
        rows.append([c.get("email", ""), c.get("contact_id", "")])
    print(f"  fetched {start}..{start + len(contacts) - 1} ({len(rows)} total)")
    if len(contacts) < CHUNK:
        break
    start += len(contacts)

out = "contacts.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["email", "contact_id"])
    writer.writerows(rows)

print(f"Done — {len(rows)} contacts written to {out}")
