---
name: generate-test-token
description: Generate a test xlsx from an EDM token file — picks two distinct rows with the most tokens filled, replaces Email column with test emails
---

# Generate Test Token XLSX

从 EDM 处理的 Token xlsx 文件中选取两个 Token 值不同的行（填充最多的行），替换第一列 Email 为指定测试邮箱，生成测试用 xlsx 文件。

## Usage

```bash
python .claude/skills/generate-test-token/generate_test_token.py <xlsx_path> [email1] [email2]
```

### 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `xlsx_path` | 是 | — | Token xlsx 文件路径 |
| `email1` | 否 | `microsoft.163163@163.com` | 第一行测试邮箱 |
| `email2` | 否 | `ma.chuntao@oe.21vianet.com` | 第二行测试邮箱 |

## Output

在原文件同目录下生成 `test_<原文件名>.xlsx`，包含：
- 第 1 行：表头（Email, Token1 ~ Token15）
- 第 2 行：测试邮箱 1 + 原数据填充最多的行的 Token 值
- 第 3 行：测试邮箱 2 + 原数据填充次多且 Token 值不同的行的 Token 值

## Requirements

- Python 3.x
- `openpyxl` (install: `pip install openpyxl`)