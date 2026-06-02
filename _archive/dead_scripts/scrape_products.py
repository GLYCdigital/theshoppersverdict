#!/usr/bin/env python3
"""Find product images from Amazon via Apify proxy."""
import sys, os, json, time, re
import urllib.request, urllib.parse, gzip

# CREDENTIALS REDACTED — use .apify_config.json instead
PROXY = 'http://auto:APIFY_PROXY_PASSWORD_REDACTED@proxy.apify.com:8000'
PROXY_HANDLER = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
OPENER = urllib.request.build_opener(PROXY_HANDLER)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip',
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = OPENER.open(req, timeout=20)
        return gzip.decompress(resp.read()).decode('utf-8', errors='replace')
    except Exception as e:
        return None

def get_title_and_image(asin):
    url = f'https://www.amazon.com/dp/{asin}'
    html = fetch(url)
    if not html:
        return None, None
    # Title
    m = re.search(r'<title[^>]*>(.*?)</title>', html)
    title = None
    if m:
        title = re.sub(r'\s*:\s*Amazon\..*', '', m.group(1)).strip()
        if len(title) < 5:
            title = None
    # Image
    imgs = re.findall(r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9.%+-]+\._AC_SL1500_\.jpg)', html)
    img = imgs[0] if imgs else None
    if not img:
        imgs = re.findall(r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9.%+-]+\._AC_SL[0-9]+_\.jpg)', html)
        img = imgs[0] if imgs else None
    return title, img

# Products with candidate ASINs to try
candidates = {
    'Aeropress Go': ['B07ZDN3P5B', 'B078NN17K3', 'B0B5124ZBN'],
    'Keurig K-Mini Plus': ['B08G17C5C1', 'B09JSKDWCK'],
    'Nespresso Vertuo Next': ['B086RBYNNB', 'B08DBVYJPZ', 'B09T3KBP6D'],
    'Ninja Specialty Coffee Maker': ['B07T5Q3ZK5', 'B07PFLM2LK', 'B09715G57M', 'B01M7TLC6B'],
    'Autonomous ErgoChair 2': ['B08D3Y5H3M', 'B081H3Y5NW', 'B07Q5VXNZJ'],
    'FlexiSpot Desk Converter': ['B0D45W2PHZ', 'B07QV3XQK4'],
    'FlexiSpot Standing Desk': ['B07RG8G7CJ', 'B074C9F45S', 'B07QV4BZ1L'],
    'Instant Pot Duo 7-in-1': ['B00FLYWNYQ', 'B09FMPXNMY', 'B08JL35RGT'],
    'Ninja Professional Plus Blender': ['B08HHDPJ7L', 'B09TTJ98CT'],
    'Vitamix E310 Explorian': ['B094R8QPB5', 'B07VCKJR2K', 'B086H42T3V'],
}

results = {}
for product, asins in candidates.items():
    print(f'{product}:', end=' ', flush=True)
    found = False
    for asin in asins:
        title, img = get_title_and_image(asin)
        if title and product.lower()[:5] in title.lower():
            print(f'✅ {asin} → {title[:40]}')
            if img:
                print(f'   Image: {img}')
            results[asin] = {'product': product, 'title': title, 'image': img}
            found = True
            break
        elif title:
            print(f'⚠️ {asin} → {title[:40]} (partial match)')
        else:
            print(f'❌ {asin}', end=' ')
    time.sleep(3)

print('\n\n=== FINAL RESULTS ===')
out = os.path.expanduser('~/.openclaw/workspace/ink/product_data.json')
with open(out, 'w') as f:
    json.dump(results, f, indent=2)
print(json.dumps(results, indent=2))
print(f'\nSaved to {out}')
