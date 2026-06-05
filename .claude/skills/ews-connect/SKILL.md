---
name: ews-connect
description: Establish Exchange Web Services (EWS) connection for Outlook email operations
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: Microsoft.Exchange.WebServices.dll
---

# EWS Connect Skill

建立 Exchange Web Services (EWS) 连接，为后续邮件操作提供基础服务对象。

## Prerequisites

- EWS Managed API DLL: `Microsoft.Exchange.WebServices.dll`
- 网络可达 Exchange 服务器

## Usage

```powershell
# 加载 Skill 脚本
. .claude/skills/ews-connect/Connect-Ews.ps1

# 连接（使用默认域凭据）
$exchService = Connect-Ews `
    -DllPath "C:\path\to\Microsoft.Exchange.WebServices.dll" `
    -EwsUrl "https://mail.21vianet.com/EWS/Exchange.asmx"

# 或指定用户名密码
$exchService = Connect-Ews `
    -DllPath "C:\path\to\Microsoft.Exchange.WebServices.dll" `
    -CredentialType "Custom" `
    -UserName "user" -Password "pass" -Domain "domain" `
    -EwsUrl "https://mail.21vianet.com/EWS/Exchange.asmx"
```

## Output

返回 `$exchService` 对象（`ExchangeService` 类型），可传递给其他 EWS Skill 使用。

## Related Skills

- `ews-folder` — 查找邮箱文件夹
- `ews-email` — 获取邮件详情
- `ews-subscribe` — 订阅新邮件事件
