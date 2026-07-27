"""
Connect to Outlook via win32com and display current mailbox information.
"""
import win32com.client
import sys


def get_smtp_address(outlook, ns):
    """Get SMTP address from CurrentUser AddressEntry."""
    user = ns.CurrentUser
    addr_entry = user.AddressEntry

    # Try Exchange user PrimarySmtpAddress
    if addr_entry.AddressEntryUserType == 0:  # olExchangeUserEntity
        try:
            exch_user = addr_entry.GetExchangeUser()
            if exch_user:
                smtp = exch_user.PrimarySmtpAddress
                if smtp:
                    return smtp
        except Exception:
            pass

    # Fallback: check Sent Items for a sent email's SenderEmailAddress
    try:
        sent = ns.GetDefaultFolder(5)  # olFolderSentMail
        items = sent.Items
        items.Sort("[SentOn]", True)
        if items.Count > 0:
            mail = items[1]
            smtp = mail.SenderEmailAddress
            if smtp:
                return smtp
    except Exception:
        pass

    return user.Name


def main():
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")

        current_user = ns.CurrentUser
        smtp_addr = get_smtp_address(outlook, ns)

        print(f"Outlook connected: {outlook.Version}")
        print(f"Current user: {current_user.Name}")
        print(f"SMTP address: {smtp_addr}")

        return smtp_addr
    except Exception as e:
        print(f"Failed to connect to Outlook: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    addr = main()
    print(f"\nMailbox: {addr}")
