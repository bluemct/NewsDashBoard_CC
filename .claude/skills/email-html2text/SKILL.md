---
name: email-html2text
description: Convert HTML email body to plain text using COM HTMLFile object
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: none
---

# Email HTML to Text Skill

将 HTML 格式的邮件正文转换为纯文本，清理多余空行。

## Prerequisites

无外部依赖，使用 Windows 内置 COM 对象。

## Usage

```powershell
function Convert-HtmlToText {
    param([string]$html)

    $doc = New-Object -ComObject "HTMLFile"
    $doc.IHTMLDocument2_write($html)
    $text = $doc.body.innerText

    # 清理空行
    $text = ($text -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"

    return $text
}

# 示例
$htmlBody = $email.Body.ToString()
$plainText = Convert-HtmlToText -html $htmlBody
```

## Related Skills

- `ews-email` — 获取邮件 Body
- `email-parse-ticket` — 从纯文本中提取工单号