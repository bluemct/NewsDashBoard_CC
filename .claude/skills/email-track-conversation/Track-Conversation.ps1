<#
.SYNOPSIS
    Track email conversations by ConversationId to distinguish sent mail from replies

.DESCRIPTION
    Maintains a dictionary of ConversationIds initiated by the user.
    Returns whether an incoming email is a new mail, a reply to your sent mail, or unrelated.

.PARAMETER Email
    EmailMessage object (from Get-EwsEmail, must have Sender and ConversationId)

.PARAMETER MyAddress
    Your email address (for comparison)

.PARAMETER ConversationStore
    Hashtable to track initiated conversations (passed by reference)

.PARAMETER Action
    What to do on each classification: 'Log', 'Return', or 'Both'. Default: 'Both'

.EXAMPLE
    Track-Conversation -Email $email -MyAddress "user@company.com" -ConversationStore $global:Conversations
#>
function Track-Conversation {
    param(
        [Parameter(Mandatory=$true)]
        $Email,

        [Parameter(Mandatory=$true)]
        [string]$MyAddress,

        [Parameter(Mandatory=$true)]
        [hashtable]$ConversationStore,

        [Parameter(Mandatory=$false)]
        [ValidateSet('Log', 'Return', 'Both')]
        [string]$Action = 'Both'
    )

    $sender = $Email.Sender.Address.ToLower()
    $conversationId = $Email.ConversationId.UniqueId
    $myAddressLower = $MyAddress.ToLower()

    $result = @{
        Classification = "Unknown"
        ConversationId = $conversationId
        Sender         = $sender
        Subject        = $Email.Subject
    }

    if ($sender -eq $myAddressLower) {
        # Sent mail - record this conversation
        $ConversationStore[$conversationId] = $true
        $result.Classification = "Sent"

        if ($Action -ne 'Return') {
            Write-Host "[SENT] Conversation tracked: $conversationId"
        }
    }
    elseif ($ConversationStore.ContainsKey($conversationId)) {
        # Reply to a conversation we initiated
        $result.Classification = "Reply"

        if ($Action -ne 'Return') {
            Write-Host "[REPLY] Conversation: $conversationId | Sender: $sender"
        }
    }
    else {
        # Other mail - not a conversation we track
        $result.Classification = "Other"

        if ($Action -ne 'Return') {
            Write-Host "[OTHER] Conversation: $conversationId | Sender: $sender | Subject: $($Email.Subject)"
        }
    }

    if ($Action -ne 'Log') {
        return $result
    }
}

Export-ModuleFunction -Function Track-Conversation