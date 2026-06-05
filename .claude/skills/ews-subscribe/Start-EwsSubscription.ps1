<#
.SYNOPSIS
    Create streaming subscription to listen for new mail events

.DESCRIPTION
    Subscribe to streaming notifications on specified folders. Registers event handlers and starts the connection.

.PARAMETER ExchangeService
    ExchangeService object (from Connect-Ews)

.PARAMETER Folders
    Array of Folder objects (from Get-EwsFolder) to subscribe to

.PARAMETER EventTypes
    EventType flags to listen for. Default: NewMail

.PARAMETER MaxConnections
    Max simultaneous streaming connections. Default: 30

.PARAMETER OnNewMail
    ScriptBlock to execute when a new mail event fires. Receives $email object via pipeline.

.PARAMETER MyAddress
    Your email address (for conversation tracking in event handler)

.EXAMPLE
    $folders = @(Get-EwsFolder -Name "Inbox" -ExchangeService $exchService)
    Start-EwsSubscription -ExchangeService $exchService -Folders $folders
#>
function Start-EwsSubscription {
    param(
        [Parameter(Mandatory=$true)]
        $ExchangeService,

        [Parameter(Mandatory=$true)]
        [array]$Folders,

        [Parameter(Mandatory=$false)]
        $EventTypes = [Microsoft.Exchange.WebServices.Data.EventType]::NewMail,

        [Parameter(Mandatory=$false)]
        [int]$MaxConnections = 30,

        [Parameter(Mandatory=$false)]
        [scriptblock]$OnNewMail,

        [Parameter(Mandatory=$false)]
        [string]$MyAddress
    )

    if ($Folders.Count -eq 0) {
        throw "No valid folders to subscribe."
    }

    # Extract FolderId array
    $folderIds = [Microsoft.Exchange.WebServices.Data.FolderId[]]$Folders.Id

    # Create subscription
    $subscription = $ExchangeService.SubscribeToStreamingNotifications($folderIds, $EventTypes)
    Write-Host "Subscription created for $($folderIds.Count) folders."

    # Create connection
    $conn = New-Object Microsoft.Exchange.WebServices.Data.StreamingSubscriptionConnection($ExchangeService, $MaxConnections)
    $conn.AddSubscription($subscription)

    # Initialize conversation tracking
    $script:InitiatedConversations = @{}

    # Register notification event handler
    Register-ObjectEvent -InputObject $conn -EventName OnNotificationEvent -Action {
        foreach ($evt in $event.SourceEventArgs.Events) {
            if ($evt.ItemId -ne $null -and $evt.ItemId.UniqueId) {
                # Get email details via the email skill
                $propertySet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,
                    [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId
                )

                try {
                    $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($exchService, $evt.ItemId, $propertySet)
                    $sender = $email.Sender.Address.ToLower()
                    $conversationId = $email.ConversationId.UniqueId

                    # Track sent mail conversations
                    if ($MyAddress -and $sender -eq $MyAddress.ToLower()) {
                        $script:InitiatedConversations[$conversationId] = $true
                        Write-Host "[SENT] Conversation tracked: $conversationId"
                        continue
                    }
                    elseif ($script:InitiatedConversations.ContainsKey($conversationId)) {
                        Write-Host "[REPLY] Conversation: $conversationId | Sender: $sender"
                    }
                    else {
                        Write-Host "[NEW] Conversation: $conversationId | Sender: $sender"
                    }

                    # Execute custom handler if provided
                    if ($OnNewMail) {
                        & $OnNewMail -Email $email -ConversationId $conversationId -Sender $sender
                    }
                }
                catch {
                    Write-Warning "Failed to read email: $($_.Exception.Message)"
                }
            }
            else {
                Write-Warning "Event with no ItemId, skipping."
            }
        }
    } | Out-Null

    # Register disconnect handler for auto-reconnect
    Register-ObjectEvent -InputObject $conn -EventName OnDisconnect -Action {
        Write-Warning "Connection lost, reconnecting in 5s..."
        Start-Sleep 5
        $conn.Open()
    } | Out-Null

    # Start listening
    $conn.Open()
    Write-Host "Streaming subscription started. Press Ctrl+C to stop."
    while ($conn.IsOpen) {
        Start-Sleep 1
    }
}

Export-ModuleFunction -Function Start-EwsSubscription