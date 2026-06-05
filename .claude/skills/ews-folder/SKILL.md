---
name: ews-folder
description: Find Outlook email folders by name using EWS
metadata:
  type: skill
  version: "1.0"
  language: powershell
  dependency: Microsoft.Exchange.WebServices.dll
---

# EWS Folder Skill

按名称查找 Outlook 邮箱文件夹，支持系统文件夹和自定义文件夹。

## Prerequisites

- `$exchService` 对象（来自 `ews-connect`）

## Usage

```powershell
function Get-Folder {
    param([string]$Name, $exchService)

    # 系统文件夹（收件箱等）
    if ($Name -eq "Inbox") {
        return [Microsoft.Exchange.WebServices.Data.Folder]::Bind(
            $exchService,
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
        )
    }
    elseif ($Name -eq "Sent Items") {
        return [Microsoft.Exchange.WebServices.Data.Folder]::Bind(
            $exchService,
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::SentItems
        )
    }
    else {
        # 自定义文件夹 - 按显示名称搜索
        $folderView = New-Object Microsoft.Exchange.WebServices.Data.FolderView(1)
        $folderView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

        $searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsEqualTo(
            [Microsoft.Exchange.WebServices.Data.FolderSchema]::DisplayName,
            $Name
        )

        $folders = $exchService.FindFolders(
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::MsgFolderRoot,
            $searchFilter,
            $folderView
        )

        if ($folders.TotalCount -gt 0) {
            return $folders.Folders[0]
        }
        else {
            return $null
        }
    }
}

# 使用示例
$inbox = Get-Folder -Name "Inbox" -exchService $exchService
$customFolder = Get-Folder -Name "EDM" -exchService $exchService
$sent = Get-Folder -Name "Sent Items" -exchService $exchService
```

## Output

返回 `Folder` 对象，可用于订阅或遍历邮件。

## Common Well-Known Folders

| 名称 | WellKnownFolderName 枚举 |
|------|-------------------------|
| Inbox | `WellKnownFolderName::Inbox` |
| Sent Items | `WellKnownFolderName::SentItems` |
| Deleted Items | `WellKnownFolderName::DeletedItems` |
| Drafts | `WellKnownFolderName::Drafts` |
| Junk Email | `WellKnownFolderName::JunkEmail` |

## Related Skills

- `ews-connect` — 建立 EWS 连接
- `ews-subscribe` — 订阅文件夹新邮件事件
