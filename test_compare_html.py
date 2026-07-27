import pythoncom, win32com.client, ctypes, os, re

def get_short_path(path):
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(path, buf, 512)
    return buf.value

sn_dir = r"C:\Users\SI-Agent\AgentProject\EDM\SN-56262"
msg_path = None
for f in os.listdir(sn_dir):
    if f.endswith('.msg'):
        msg_path = os.path.join(sn_dir, f)
        break

pythoncom.CoInitialize()
outlook = win32com.client.Dispatch('Outlook.Application')
ns = outlook.GetNamespace('MAPI')
short = get_short_path(msg_path)
msg = ns.OpenSharedItem(short)
html_body = msg.HTMLBody or ''
subject = msg.Subject or ''
msg.Close(0)
pythoncom.CoUninitialize()

with open(os.path.join(sn_dir, 'EDM_template.html'), 'r', encoding='utf-8') as f:
    template = f.read()

raw_cr = html_body.count('\r')
raw_lf = html_body.count('\n')
tpl_cr = template.count('\r')
tpl_lf = template.count('\n')
print(f"Raw: CR={raw_cr} LF={raw_lf} len={len(html_body)}")
print(f"Template: CR={tpl_cr} LF={tpl_lf} len={len(template)}")

# Normalize to \n for comparison
raw_norm = html_body.replace('\r\n', '\n').replace('\r', '\n')
tpl_norm = template.replace('\r\n', '\n').replace('\r', '\n')

# Split into lines and compare
raw_lines = raw_norm.split('\n')
tpl_lines = tpl_norm.split('\n')

diff_count = 0
for i, (rl, tl) in enumerate(zip(raw_lines, tpl_lines)):
    if rl != tl:
        diff_count += 1

extra = abs(len(raw_lines) - len(tpl_lines))
print(f"Differing lines: {diff_count}")
print(f"Extra lines: {extra}")

if tpl_cr > 0:
    print("\\r\\n preserved!")
else:
    print("\\r\\n NOT preserved - win32com strips \\r")
