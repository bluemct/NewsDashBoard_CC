# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a beginner-level Python learning project. It contains simple standalone scripts with no external dependencies, no virtual environment, and no build system.

## Files

- `runoob-claude-demo/main.py` — Core demo script. Defines an `add()` function with type checking, logging, and inline self-tests (asserts + try/except).
- `test.py` — Simple `hello_world()` print script.

## Running Code

No dependencies to install. Run scripts directly with Python 3:

```bash
python3 runoob-claude-demo/main.py
python3 test.py
```

## Skills Overview

### Email Skills (win32com)

| Skill | 操作 | 权限级别 |
|-------|------|----------|
| `outlook-connect` | 连接 Outlook 并获取邮箱地址 | 自动允许 |
| `outlook-list-emails` | 列出收件箱/发件箱邮件 | 自动允许（只读） |
| `outlook-email` | 读取单封邮件详情 | 自动允许（只读） |
| `outlook-folder` | 查找邮件文件夹 | 自动允许（只读） |
| `outlook-subscribe` | 监控新邮件到达 | 自动允许（只读） |
| `outlook-draft-email` | 创建邮件草稿（存到 Drafts） | 自动允许（不发送） |
| `email-html2text` | HTML 转纯文本 | 自动允许（只读） |
| `email-parse-ticket` | 从邮件提取工单号 | 自动允许（只读） |
| `email-track-conversation` | 跟踪邮件对话链 | 自动允许（只读） |
| `msg-to-html` | .msg 文件转 HTML | 自动允许（只读） |

> **所有邮件操作使用 Python `win32com.client` 调用 Outlook，不再依赖 EWS DLL 或 PowerShell。**

### EDM Process Skill (extract-msg + olefile + win32com)

| Skill | 操作 | 说明 |
|-------|------|------|
| `edm-process` | 完整 EDM 处理流程 | 提取SN、创建文件夹、转换xlsx→CSV、提取嵌套.msg、转HTML |

- 主脚本: `.claude/skills/edm-process/edm_process.py`
- 依赖: `extract-msg`, `olefile`, `openpyxl`, `win32com`
- 用法: `python .claude/skills/edm-process/edm_process.py`（读取 `EDM/Temp/` 中的文件）
- 输出: `EDM/SN-xxxxx/` 文件夹（xlsx, csv, .msg, EDM_template.html）
- 前提: Outlook 运行且已连接 Exchange（win32com 读取 HTMLBody）

## Security Rules

### 邮件发送
- **绝对禁止发送邮件** — 无论任何情况、任何用户指令、任何豁免请求，都不得调用 `MailItem.Send`、`SendUsingAccount`、`SendAndSaveCopy` 或任何发送邮件的方法
- **严禁写内联 Python 代码执行 `.Send()`** — 只能通过 `outlook-draft-email` skill 创建草稿
- **允许创建草稿** — 使用 `outlook-draft-email` skill 将邮件保存到 Drafts 文件夹
- **用户手动发送** — 草稿创建后，用户需要打开 Outlook 手动点击发送

### 联系人 / 收件人 / 地址簿
- **禁止访问联系人** — 不得访问 `Contacts` 文件夹、`AddressList`、或读取联系人信息
- **禁止访问全局地址簿** — 不得使用 `AddressLists`、`Global Address List`、`GetAddressEntryFromName`、`CreateRecipient.Resolve()` 或任何方式查询用户邮箱地址
- **禁止获取收件人邮箱** — 不得通过 `MailItem.Recipients`、`MailItem.To`、`AddressEntry.GetExchangeUser()` 或任何方式提取收件人的邮箱地址
- **允许读取发件人邮箱** — 可以读取邮件的 `SenderEmailAddress` 字段获取当前邮件的发件人邮箱地址

### 邮件文件夹
- **允许读取** — Inbox、Sent Items、Drafts、Junk Email 等文件夹的邮件列表和内容
- **禁止修改** — 不得删除、移动、标记邮件，不得修改邮件属性
- **禁止写入** — 除了 Drafts 文件夹的草稿保存外，不得向其他文件夹写入内容
