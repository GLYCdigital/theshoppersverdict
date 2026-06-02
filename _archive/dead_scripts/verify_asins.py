#!/usr/bin/env python3
"""Verify potential Amazon ASINs by checking Amazon product pages.
Uses iPhone mobile UA which has been less aggressively blocked."""
import urllib.request, re, json, sys

def check_asin(asin):
    """Fetch Amazon product page and extract title + image URL."""
    url = f'https://www.amazon.com/dp/{asin}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        import gzip
        html = gzip.decompress(resp.read()).decode('utf-8', errors='replace')
    except Exception as e:
        return None, str(e)
    
    # Get title
    m = re.search(r'<title[^>]*>([^<]+)</title>', html)
    title = m.group(1).strip() if m else 'UNKNOWN'
    # Clean up Amazon suffix
    title = re.sub(r'\s*:\s*Amazon\..*', '', title).strip()
    
    # Get image
    img = None
    m = re.search(r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9.%+-]+\._AC_SL1500_\.jpg)', html)
    if m:
        img = m.group(1)
    else:
        m = re.search(r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9.%+-]+\._AC_SL[0-9]+_\.jpg)', html)
        if m:
            img = m.group(1)
    
    return title, img

# ASIN candidates to check - search results from various sources
candidates = [
    # Aeropress Go - different ASINs to try
    ('B07ZDN3P5B', 'Aeropress Go candidate'),
    ('B07VL8SF3', 'Aeropress Go candidate'),
    ('B08Y24LPNP', 'Aeropress Go candidate'),
    
    # Ninja Specialty Coffee Maker CM401
    ('B07T5Q3ZK5', 'Ninja Specialty Coffee Maker'),
    ('B01M7TLC6B', 'Ninja Specialty Coffee Maker'),
    ('B01M0H2QK1', 'Ninja Specialty Coffee Maker'),
    
    # Autonomous ErgoChair 2
    ('B08D3Y5H3M', 'ErgoChair 2'),
    ('B081H3Y5NW', 'ErgoChair 2 (current)'),
    
    # FlexiSpot Standing Desk E1
    ('B07RG8G7CJ', 'FlexiSpot Desk E1'),
    ('B07RG8D1RS', 'FlexiSpot Desk E1'),
    
    # Vitamix E310 Explorian
    ('B07H2C3K7K', 'Vitamix E310'),
    ('B07VCKJR2K', 'Vitamix E310'),
]

results = []
for asin, label in candidates:
    print(f'Checking {asin} ({label})...', end=' ', flush=True)
    title, img = check_asin(asin)
    if title:
        print(f'✅ {title[:60]}')
        if img:
            print(f'   Image: {img[:70]}')
    else:
        print(f'❌ {img}')  # img slot has the error message
    
    results.append({'asin': asin, 'label': label, 'title': title, 'image': img})

print('\n' + '='*60)
print('SUMMARY:')
for r in results:
    if r['title']:
        print(f'✅ {r["asin"]} ({r["label"]}): {r["title"][:60]}')
        if r['image']:
            print(f'   {r["image"]}')
    else:
        print(f'❌ {r["asin"]} ({r["label"]}): {r.get("image", "ERROR")}')
