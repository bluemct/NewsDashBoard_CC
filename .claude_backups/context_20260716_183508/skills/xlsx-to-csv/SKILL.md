---
name: xlsx-to-csv
description: "Convert .xlsx files to GB2312-encoded CSV files with full cell-by-cell verification"
---

# XLSX to CSV Converter

Convert Excel (.xlsx) files to comma-delimited CSV files with GB2312 encoding, and verify every cell value matches the original.

## Usage

```bash
python .claude/skills/xlsx-to-csv/xlsx_to_csv.py <input.xlsx> [output.csv]
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| input     | Yes      | Path to source .xlsx file |
| output    | No       | Path to output CSV file (default: same name, .csv extension) |

## Output

- CSV file encoded in **GB2312**, comma-delimited
- Verification report printed to console
- Exit code 0 = all cells match; exit code 1 = mismatches found

## Requirements

- Python 3.x
- `openpyxl` (install: `pip install openpyxl`)

## Example

```bash
python .claude/skills/xlsx-to-csv/xlsx_to_csv.py report.xlsx
python .claude/skills/xlsx-to-csv/xlsx_to_csv.py data.xlsx output.csv
```
