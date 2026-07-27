# Unimarketing Contact List Import — Generate CSV & Import

Generate a CSV from an xlsx file and import contacts into a new Unimarketing list via the contact import API.

## Modes

| Mode | Flag | CSV | List Name | Email |
|------|------|-----|-----------|-------|
| Test (default) | — | `test_*.csv` (2 rows, most tokens) | `test_{SN}_{xlsxName}_{datetime}` | Replaced with config test emails |
| Formal | `--formal` | `formal_*.csv` (all rows) | `formal_{SN}_{xlsxName}_{datetime}` | Original emails preserved |

## Usage

```bash
# Test import (default)
python .claude/skills/unimarketing-test-list/unimarketing_test_list.py \
  --xlsx "path/to/contacts.xlsx"

# Formal import (all rows)
python .claude/skills/unimarketing-test-list/unimarketing_test_list.py \
  --xlsx "path/to/contacts.xlsx" --formal

# With explicit SN
python .claude/skills/unimarketing-test-list/unimarketing_test_list.py \
  --xlsx "path/to/contacts.xlsx" --sn "SN-56230" --formal
```

## Flow
1. Read xlsx → generate CSV (test or formal)
2. Create Unimarketing list (`test_` or `formal_{SN}_{xlsxName}_{datetime}`) with Token/SubId attribute definitions
3. Create import task (building)
4. Submit contacts from CSV
5. Execute import task
6. Poll until import complete
