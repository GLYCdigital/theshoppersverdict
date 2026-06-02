#!/usr/bin/env python3
"""Find ASINs and images by searching Amazon through Apify proxy with session rotation."""
import sys, os, json, time, re, uuid
import urllib.request, urllib.parse, gzip

# CREDENTIALS REDACTED — use .apify_config.json instead
PASS = 'APIFY_PROXY_PASSWORD_REDACTED'
groups = ['BUYPROXIES94952'] * 27  # 27 proxy IPs

def make_opener(session_id):
    proxy_url = f'http://groups-BUYPROXIES94952-session-{session_id}:{PASS}@proxy.apify.com:8000'
    handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
    return urllib.request.build_opener(handler)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip',
}

def fetch(url, session_id=None):
    if not session_id:
        session_id = uuid.uuid4().hex[:12]
    opener = make_opener(session_id)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = opener.open(req, timeout=20)
        return gzip.decompress(resp.read()).decode('utf-8', errors='replace')
    except Exception as e:
        return None

def search_asin(product_name):
    """Search Amazon and return first ASIN + title."""
    query = urllib.parse.quote(f'"{product_name}"')
    url = f'https://www.amazon.com/s?k={query}&ref=nb_sb_noss'
    html = fetch(url, uuid.uuid4().hex[:12])
    if not html:
        return None, None
    # Find ASINs
    asins = re.findall(r'/dp/([A-Z0-9]{10})', html)
    if not asins:
        asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if asins:
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for a in asins:
            if a not in seen:
                seen.add(a)
                unique.append(a)
        if unique:
            return unique[0], None  # Return first ASIN, get title later
    return None, None

def get_product(asin):
    """Get title and image for an ASIN."""
    url = f'https://www.amazon.com/dp/{asin}'
    html = fetch(url, uuid.uuid4().hex[:12])
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

# Products to search for
products = [
    'Aeropress Go travel coffee press',
    'Keurig K-Mini Plus single serve',
    'Nespresso Vertuo Next',
    'Ninja Specialty Coffee Maker CM401',
    'Autonomous ErgoChair 2',
    'FlexiSpot standing desk converter M3B',
    'FlexiSpot standing desk E1 55 inch',
    'Instant Pot Duo 7-in-1 6 quart',
    'Ninja Professional Plus Blender Auto-iQ',
    'Vitamix E310 Explorian blender',
]

results = {}
for i, product in enumerate(products):
    print(f'[{i+1}/10] {product[:40]}...', end=' ', flush=True)
    
    # Search
    asin, _ = search_asin(product)
    if not asin:
        print('❌ not found')
        continue
    
    # Get product details
    time.sleep(2)  # Rate limit
    title, img = get_product(asin)
    if title:
        print(f'✅ {asin} → {title[:50]}')
        if img:
            print(f'   📷 {img}')
        results[asin] = {'product': product, 'title': title, 'image': img}
    else:
        print(f'⚠️ {asin} (no details)')
    time.sleep(2)

print('\n\n=== FINAL RESULTS ===')
for asin, data in results.items():
    print(f'{data["product"][:30]:30s} → {asin} | {"✅" if data["image"] else "❌ no img"}')
    if data.get('image'):
        print(f'  {data["image"]}')

out = os.path.expanduser('~/.openclaw/workspace/ink/product_data.json')
with open(out, 'w') as f:
    json.dump(results, f, indent=2)
print(f'\n💾 Saved to {out}')
