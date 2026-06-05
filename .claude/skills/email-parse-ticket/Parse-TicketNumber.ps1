<#
.SYNOPSIS
    Extract ticket/request number from email body text

.DESCRIPTION
    Search email text for ticket/request numbers using configurable regex patterns.

.PARAMETER Text
    Plain text to search (from email body)

.PARAMETER Pattern
    Regex pattern with capture group 1 for the ticket number.
    Default: 'Request\s*#\s*(\d+)'

.EXAMPLE
    # Default pattern: "Request #12345"
    Parse-TicketNumber -Text $emailBody

    # Custom pattern: "CASE-00123"
    Parse-TicketNumber -Text $emailBody -Pattern 'CASE[-:]?\s*(\d+)'
#>
function Parse-TicketNumber {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Text,

        [Parameter(Mandatory=$false)]
        [string]$Pattern = 'Request\s*#\s*(\d+)'
    )

    $commonPatterns = @{
        'Request #12345' = 'Request\s*#\s*(\d+)'
        'Ticket-12345'   = 'Ticket[-:]?\s*(\d+)'
        '工单 12345'     = '工单\s*(\d+)'
        'CASE-00123'     = 'CASE[-:]?\s*(\d+)'
        'Order #12345'   = 'Order\s*#\s*(\d+)'
        'Issue #12345'   = 'Issue\s*#\s*(\d+)'
    }

    # Try the specified pattern first
    if ($Text -match $Pattern) {
        return @{
            Found  = $true
            Number = $Matches[1]
            MatchedPattern = $Pattern
        }
    }

    # If not found and a custom pattern was given, try common patterns as fallback
    foreach ($name in $commonPatterns.Keys) {
        if ($Text -match $commonPatterns[$name]) {
            Write-Host "Matched pattern: $name"
            return @{
                Found  = $true
                Number = $Matches[1]
                MatchedPattern = $commonPatterns[$name]
            }
        }
    }

    return @{
        Found  = $false
        Number = $null
        MatchedPattern = $null
    }
}

Export-ModuleFunction -Function Parse-TicketNumber