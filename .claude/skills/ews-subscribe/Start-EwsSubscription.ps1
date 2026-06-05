<#
.SYNOPSIS
    Create streaming subscription to listen for new mail events

.DESCRIPTION
    Subscribe to streaming notifications on specified folders. Registers event handlers and starts the connection.

    The event handler runs in a separate runspace, so all EWS operations are done inline.
    Skill functions (Convert-HtmlToText, Parse-TicketNumber, Track-Conversation) are used via the OnNewMail callback
    which runs in the main runspace.

.PARAMETER ExchangeService
    ExchangeService object (from Connect-Ews)

.PARAMETER Folders
    Array of Folder objects (from Get-EwsFolder) to subscribe to

.PARAMETER EventTypes
    EventType flags to listen for. Default: NewMail

.PARAMETER MaxConnections
    Max simultaneous streaming connections. Default: 30

.PARAMETER OnNewMail
    ScriptBlock to execute when a new mail event fires. Runs in the main runspace so it can call other Skills.
    Receives a hashtable with keys: EmailData (hashtable), ConversationId, Sender, Classification

.PARAMETER MyAddress
    Your email address (for conversation tracking in event handler)

.EXAMPLE
    $folders = @(Get-EwsFolder -Name "Inbox" -ExchangeService $exchService)
    Start-EwsSubscription -ExchangeService $exchService -Folders $folders -MyAddress "user@company.com"
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

    # Conversation tracking store (shared via AdditionalData)
    $conversationsData = @{
        InitiatedConversations = @{}
    }

    # ---- Event handler runs in separate runspace ----
    # Use AdditionalData to pass context that the separate runspace can access
    $eventAction = {
        foreach ($evt in $event.SourceEventArgs.Events) {
            # Fix: $null on left side of comparison
            if ($null -ne $evt.ItemId -and $evt.ItemId.UniqueId) {
                try {
                    # Inline EWS bind (can't cross runspace boundary)
                    $propSet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet(
                        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Subject,
                        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Body,
                        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::Sender,
                        [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]::ConversationId
                    )
                    $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind(
                        $event.SourceEventArgs.Data.ExchangeService,
                        $evt.ItemId,
                        $propSet
                    )

                    # Fix: renamed from $sender (automatic variable)
                    $emailSender = $email.Sender.Address.ToLower()
                    $conversationId = $email.ConversationId.UniqueId
                    $myAddr = $event.SourceEventArgs.Data.MyAddress.ToLower()

                    # Track conversation
                    $classification = "Other"
                    if ($emailSender -eq $myAddr) {
                        $event.SourceEventArgs.Data.InitiatedConversations[$conversationId] = $true
                        $classification = "Sent"
                    }
                    elseif ($event.SourceEventArgs.Data.InitiatedConversations.ContainsKey($conversationId)) {
                        $classification = "Reply"
                    }

                    # Convert HTML body to text inline
                    $plainText = ""
                    try {
                        $html = $email.Body.ToString()
                        if ($html -and $html.Trim().Length -gt 0) {
                            $doc = New-Object -ComObject "HTMLFile"
                            $doc.IHTMLDocument2_write($html)
                            $plainText = ($doc.body.innerText -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"
                        }
                    }
                    catch {
                        $plainText = $email.Body.ToString()
                    }

                    # Write result to a temp file for main runspace to pick up
                    $resultData = @{
                        EmailSender    = $emailSender
                        ConversationId = $conversationId
                        Subject        = $email.Subject
                        Classification = $classification
                        BodyText       = $plainText
                    }

                    # Output to event log for main loop to consume
                    $logEntry = @{
                        Timestamp  = [DateTime]::Now
                        Email      = $resultData
                        RawText    = $plainText
                    }

                    # Write to a shared temp file for main runspace
                    $tmpFile = [System.IO.Path]::GetTempFileName()
                    $logEntry | ConvertTo-Json -Depth 5 | Out-File $tmpFile -Encoding utf8
                    Write-Host "[$($resultData.Classification)] From: $emailSender | ConvId: $conversationId | Subject: $($email.Subject)"
                }
                catch {
                    Write-Warning "Failed to read email: $($_.Exception.Message)"
                }
            }
            else {
                Write-Warning "Event with no ItemId, skipping."
            }
        }
    }

    # Pass context via AdditionalData (crosses runspace boundary)
    Register-ObjectEvent -InputObject $conn `
        -EventName OnNotificationEvent `
        -Action $eventAction `
        -AdditionalData @{
            ExchangeService       = $ExchangeService
            MyAddress             = $MyAddress
            InitiatedConversations = $conversationsData.InitiatedConversations
        } | Out-Null

    # Register disconnect handler for auto-reconnect
    Register-ObjectEvent -InputObject $conn `
        -EventName OnDisconnect `
        -Action {
            Write-Warning "Connection lost, reconnecting in 5s..."
            Start-Sleep 5
            $event.SourceEventArgs.Connection.Open()
        } | Out-Null

    # Start listening
    $conn.Open()
    Write-Host "Streaming subscription started. Press Ctrl+C to stop."
    while ($conn.IsOpen) {
        Start-Sleep 1
    }
}