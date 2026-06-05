<#
.SYNOPSIS
    Get email details by ItemId

.DESCRIPTION
    Bind to an email message and retrieve specified properties (Subject, Body, Sender, ConversationId, etc.)

.PARAMETER ItemId
    The ItemId of the email (from EWS notification event)

.PARAMETER ExchangeService
    ExchangeService object (from Connect-Ews)

.PARAMETER Properties
    Array of properties to fetch. Default: Subject, Body, Sender, ConversationId

.EXAMPLE
    Get-EwsEmail -ItemId $evt.ItemId -ExchangeService $exchService
    Get-EwsEmail -ItemId $evt.ItemId -ExchangeService $exchService -Properties @('Subject','Sender')
#>
function Get-EwsEmail {
    param(
        [Parameter(Mandatory=$true)]
        $ItemId,

        [Parameter(Mandatory=$true)]
        $ExchangeService,

        [Parameter(Mandatory=$false)]
        [string[]]$Properties = @('Subject', 'Body', 'Sender', 'ConversationId')
    )

    # Build PropertySet from requested properties
    $schema = [Microsoft.Exchange.WebServices.Data.EmailMessageSchema]
    $propSet = New-Object Microsoft.Exchange.WebServices.Data.PropertySet

    foreach ($p in $Properties) {
        $propValue = $schema."$p"
        if ($propValue) {
            $propSet.Add($propValue)
        }
        else {
            Write-Warning "Unknown property: $p"
        }
    }

    # Bind to the email
    try {
        $email = [Microsoft.Exchange.WebServices.Data.EmailMessage]::Bind($ExchangeService, $ItemId, $propSet)
        return $email
    }
    catch {
        Write-Error "Failed to bind email: $($_.Exception.Message)"
        return $null
    }
}

Export-ModuleFunction -Function Get-EwsEmail