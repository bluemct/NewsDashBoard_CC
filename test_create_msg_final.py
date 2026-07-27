"""Check if EDM_template.html has the footer section."""
import re

with open("EDM/SN-56195/EDM_template.html", encoding="utf-8") as f:
    raw_html = f.read()

# Extract body
body_match = re.search(r"<body[^>]*>(.*?)</body>", raw_html, re.DOTALL)
body_content = body_match.group(1) if body_match else raw_html

# Check for footer elements
print("Body length:", len(body_content))
print("\nLast 1000 chars of body:")
print(body_content[-1000:])

# Check if footer is in the body
if "customersupport@mktedm" in body_content:
    print("\nHAS customersupport email in body")
elif "customersupport@" in body_content:
    print("\nHAS customersupport in body")
else:
    print("\nNO customersupport email in body")

# Check for unsubscribe
if "Unsubscribe" in body_content:
    print("HAS Unsubscribe in body")
else:
    print("NO Unsubscribe in body")
