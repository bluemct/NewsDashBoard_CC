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
# 加载 EWS DLL
Import-Module -Name "C:\path\to\Microsoft.Exchange.WebServices.dll"

# 使用默认域凭据（推荐内网环境）
$Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials

# 或使用用户名密码
# $Credentials = New-Object Microsoft.Exchange.WebServices.Data.WebCredentials("user", "password", "domain")

# 创建 ExchangeService 对象
$exchService = New-Object Microsoft.Exchange.WebServices.Data.ExchangeService
$exchService.Credentials = $Credentials
$exchService.url = 'https://mail.21vianet.com/EWS/Exchange.asmx'
```

## Output

返回 `$exchService` 对象（`ExchangeService` 类型），可传递给其他 EWS Skill 使用。

## Related Skills

- `ews-folder` — 查找邮箱文件夹
- `ews-email` — 获取邮件详情
- `ews-subscribe` — 订阅新邮件事件
