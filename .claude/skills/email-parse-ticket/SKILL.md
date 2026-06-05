---
name: email-parse-ticket
description: Extract ticket/request numbers from email body text using regex
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: none
---

# Email Parse Ticket Skill

从邮件正文中通过正则表达式提取工单号。

## Prerequisites

无外部依赖。

## Usage

```powershell
function Parse-TicketNumber {
    param([string]$text)

    if ($text -match 'Request\s*#\s*(\d+)') {
        return @{
            Found  = $true
            Number = $Matches[1]
        }
    }
    else {
        return @{
            Found  = $false
            Number = $null
        }
    }
}

# 示例
$result = Parse-TicketNumber -text $plainText
if ($result.Found) {
    Write-Host "Ticket Number: $($result.Number)"
}
```

## Custom Patterns

根据实际业务调整正则，常见模式：

| 格式 | 正则 |
|------|------|
| `Request #12345` | `Request\s*#\s*(\d+)` |
| `Ticket-12345` | `Ticket[-:]?\s*(\d+)` |
| `工单 12345` | `工单\s*(\d+)` |
| `CASE-00123` | `CASE[-:]?\s*(\d+)` |

## Related Skills

- `email-html2text` — 先转换为纯文本再提取