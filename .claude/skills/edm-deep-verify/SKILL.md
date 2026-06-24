# edm-deep-verify

Deep verify Unimarketing list contacts against xlsx — field by field comparison.

## What it does

1. Reads xlsx with openpyxl, builds Map<email, column values>
2. Queries each xlsx email via `GET /contact/?q=[email=X,listId=Y]` (parallel, no pagination)
3. Exports found contacts to UTF-8 CSV in `listverify/` directory
4. Compares every field between xlsx and CSV with email as primary key
5. Outputs pass/fail report with detailed differences

## Approach change (2026-06-24)

Previously fetched all list contacts via paginated API (`start-index`), but API ordering is unstable — same entry appears on different pages across requests, causing duplicates and missing entries. Now queries each xlsx email individually, avoiding pagination entirely.

## Difference from email-only verify

| | Email Only | Deep Verify |
|--|-----------|-------------|
| Compare | Email existence only | All fields (Token, SubId, Customer, etc.) |
| Query | Parallel `q=[email=X,listId=Y]` per xlsx email | Same, returns full attributes |
| Export | `.txt` (emails) | UTF-8 CSV (full attributes) |

## Usage

```bash
python deep_verify_list.py --list-id 350021 --xlsx "C:\path\ContactInfo.xlsx" --workers 10
```

## Files

- `deep_verify_list.py` — Main module (project root)

## Key findings

- API returns `name` ("SubIdT") and `label` ("SubId2") — use label for Token/SubId columns
- API values are "uuid, DisplayName" format — compare display part against xlsx
- Column matching is case-insensitive by header name
- `q=[email=X,listId=Y]` returns exactly 0 or 1 entry, no pagination needed
