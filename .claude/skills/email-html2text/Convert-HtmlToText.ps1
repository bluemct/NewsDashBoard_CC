<#
.SYNOPSIS
    Convert HTML email body to plain text

.DESCRIPTION
    Uses Windows built-in HTMLFile COM object to parse HTML and extract readable plain text, removing empty lines.

.PARAMETER Html
    HTML string to convert

.EXAMPLE
    $text = Convert-HtmlToText -Html $email.Body.ToString()
#>
function Convert-HtmlToText {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Html
    )

    if ([string]::IsNullOrWhiteSpace($Html)) {
        return ""
    }

    try {
        $doc = New-Object -ComObject "HTMLFile"
        $doc.IHTMLDocument2_write($Html)
        $text = $doc.body.innerText

        # Clean up empty lines
        $text = ($text -split "`r`n" | Where-Object { $_.Trim() }) -join "`r`n"

        return $text
    }
    catch {
        Write-Warning "HTML conversion failed, returning raw body. Error: $($_.Exception.Message)"
        return $Html
    }
}