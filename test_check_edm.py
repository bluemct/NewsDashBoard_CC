"""Check what the EDM template HTML contains vs what we're sending."""
import re
import xml.sax.saxutils as sax

with open("EDM/SN-56195/EDM_template.html", encoding="utf-8") as f:
    raw_html = f.read()

# Extract body
body_match = re.search(r"<body[^>]*>(.*?)</body>", raw_html, re.DOTALL)
body_content = body_match.group(1) if body_match else raw_html

# Clean Word-specific XML (same as the create_message script)
clean = body_content
clean = re.sub(r"<span[^>]*mso-bookmark[^>]*>?\s*</span\s*>", "", clean)
clean = re.sub(r"<span[^>]*_MailOriginal[^>]*>?\s*</span\s*>", "", clean)
clean = re.sub(r"<!\[endif\]-->", "", clean)
clean = re.sub(r"<!\[if [^>]*-->", "", clean)
clean = re.sub(r"<(?:w|m|dt):[^>]*>.*?</(?:w|m|dt):[^>]*>", "", clean, flags=re.DOTALL)
clean = re.sub(r"<o:p>\s*</o:p>", "<br/>", clean)
clean = re.sub(r"<o:p[^>]*/?>", "", clean)

# Check what we're sending
print("Clean body length:", len(clean))
print("\nLast 500 chars of clean body:")
print(clean[-500:])

# Check if footer is present
if "customersupport@mktedm" in clean:
    print("\nHAS customersupport email in clean body")
elif "customersupport@" in clean:
    print("\nHAS customersupport in clean body")
else:
    print("\nNO customersupport email in clean body")

if "Unsubscribe" in clean:
    print("HAS Unsubscribe in clean body")
else:
    print("NO Unsubscribe in clean body")

# Now wrap in full HTML and escape
html_doc = '<html xmlns="http://www.w3.org/TR/REC-html40"><head><title>邮件主题已移到发送计划中定义！</title></head><body>' + clean + '</body></html>'
escaped_content = sax.escape(html_doc)

# Check final result
print(f"\nFinal HTML length: {len(escaped_content)}")
print(f"\nFinal HTML last 500 chars:")
print(escaped_content[-500:])
