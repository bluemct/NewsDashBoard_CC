"""Test SharePoint URL conversion and download attempt."""
import urllib.parse
import requests

url = 'https://microsoftapc.sharepoint.com/:x:/r/teams/AzureServiceNotificationsCollaboration/Shared Documents/2026/2026-06/811869714 - SN-56195/Token1-3 SN-56195.xlsx?d=w869c3cccb3f04c668616eedb1de70217&csf=1&web=1&e=jkt2sK'

# Correct URL conversion
if '/:x:/r/' in url:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    file_id = query.get('d', [''])[0]
    e_param = query.get('e', [''])[0]
    path = parsed.path.replace('/:x:/r/', '/:x:/g/')
    url_g = f'{parsed.scheme}://{parsed.netloc}{path}?e={file_id}'
    print('URL_G:', url_g)

# Try original URL with redirects
print('--- Original URL ---')
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get(url, allow_redirects=True, timeout=30, headers=h)
print('Status:', resp.status_code)
print('Final:', resp.url[:300])
print('CT:', resp.headers.get('Content-Type'))
print('Len:', len(resp.content))
if len(resp.content) < 500:
    print('Body:', resp.content[:500])
else:
    print('Hex:', resp.content[:10].hex())

# Try :x:/g/ URL
print('--- Direct Download URL ---')
resp2 = requests.get(url_g, allow_redirects=True, timeout=30, headers=h)
print('Status:', resp2.status_code)
print('Final:', resp2.url[:300])
print('CT:', resp2.headers.get('Content-Type'))
print('Len:', len(resp2.content))

# Try with :t:/t/ pattern
print('--- Try :t:/a/ pattern ---')
raw_path = parsed.path
path_a = raw_path.replace('/:x:/r/', '/:t:/a/')
url_a = f'{parsed.scheme}://{parsed.netloc}{path_a}?e={e_param}'
print('URL_A:', url_a)
resp3 = requests.get(url_a, allow_redirects=True, timeout=30, headers=h)
print('Status:', resp3.status_code)
