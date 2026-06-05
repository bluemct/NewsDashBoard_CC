<#
.SYNOPSIS
    Find an Outlook folder by name

.DESCRIPTION
    Returns a Folder object for a well-known folder (Inbox, Sent Items) or a custom folder by display name.

.PARAMETER Name
    Folder name. Use "Inbox" or "Sent Items" for well-known folders, or any custom folder name.

.PARAMETER ExchangeService
    ExchangeService object (from Connect-Ews)

.EXAMPLE
    Get-EwsFolder -Name "Inbox" -ExchangeService $exchService
    Get-EwsFolder -Name "MyCustomFolder" -ExchangeService $exchService
#>
function Get-EwsFolder {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Name,

        [Parameter(Mandatory=$true)]
        $ExchangeService
    )

    # Well-known folders
    $wellKnownMap = @{
        "Inbox"      = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Inbox
        "Sent Items" = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::SentItems
        "Deleted Items" = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::DeletedItems
        "Drafts"     = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Drafts
        "Junk Email" = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::JunkEmail
        "Archive"    = [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::Archive
    }

    if ($wellKnownMap.ContainsKey($Name)) {
        $folder = [Microsoft.Exchange.WebServices.Data.Folder]::Bind($ExchangeService, $wellKnownMap[$Name])
        Write-Host "Found well-known folder: $($folder.DisplayName) (Unread: $($folder.UnreadCount))"
        return $folder
    }
    else {
        # Search custom folder by display name
        $folderView = New-Object Microsoft.Exchange.WebServices.Data.FolderView(1)
        $folderView.PropertySet = [Microsoft.Exchange.WebServices.Data.BasePropertySet]::FirstClassProperties

        $searchFilter = New-Object Microsoft.Exchange.WebServices.Data.SearchFilter+IsEqualTo(
            [Microsoft.Exchange.WebServices.Data.FolderSchema]::DisplayName,
            $Name
        )

        $folders = $ExchangeService.FindFolders(
            [Microsoft.Exchange.WebServices.Data.WellKnownFolderName]::MsgFolderRoot,
            $searchFilter,
            $folderView
        )

        if ($folders.TotalCount -gt 0) {
            $folder = $folders.Folders[0]
            Write-Host "Found custom folder: $($folder.DisplayName)"
            return $folder
        }
        else {
            Write-Warning "Folder '$Name' not found."
            return $null
        }
    }
}